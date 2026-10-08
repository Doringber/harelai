import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import pymupdf
from docx import Document as WordDocument
from approval.core.models import Document, Page, Evidence, Observation, Extraction, Issue
from approval.core.quality import text_quality
from approval.core.validation import validate_evidence, validate_case
from approval.core.decision import decide
from approval.extractors.local import LocalExtractor
from approval.extractors.claude import ClaudeExtractor
from approval.infrastructure.retry import retry, TransientFailure, PermanentFailure, InvalidModelOutput
from approval.infrastructure.store import Store
from approval.application import run
from approval.readers.pdf import PdfReader
from approval.readers.docx import DocxReader
from approval.readers.text import TextReader
from approval.presentation.report import render

ROOT = Path(__file__).resolve().parents[1]

def doc(text='Evidence text', role='ct'):
    return Document(id=role, filename='test.pdf', role=role, sha256='test', pages=[Page(number=1,text=text,method='native')])

def obs(field, value, document='ct', quote='Evidence text'):
    return Observation(field=field,value=value,evidence=Evidence(document_id=document,page=1,quote=quote))

class SampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.tmp.name)/'runs.sqlite')
        cls.result = run(ROOT/'examples/case.json',LocalExtractor(),cls.store)
    @classmethod
    def tearDownClass(cls):
        cls.store.close(); cls.tmp.cleanup()

    def test_sample_expected_values(self):
        r=self.result
        self.assertEqual(r.recommendation.status,'APPROVE')
        self.assertEqual(r.run_status,'completed')
        self.assertEqual(r.case_id,'PA-2025-847291')
        self.assertEqual(r.patient,{'name':'Margaret A. Johnson','date_of_birth':'1952-03-15','mrn':'847291'})
        self.assertEqual(r.request['cpt_codes'],['31629','31632','77012'])
        for field, expected in [('fev1_percent',62),('dlco_percent',58),('suv_max',4.2),('lung_rads','4B'),('nodule_size','18 x 15 mm')]:
            self.assertEqual(r.clinical_summary[field],expected)
        self.assertTrue({'age_discrepancy','pet_secondary_source'} <= {i.code for i in r.issues})
        self.assertTrue(all(r.request.values()))
        self.assertTrue(all(r.clinical_summary.values()))
        self.assertEqual(len(r.documents),5)

    def test_every_quote_grounded(self):
        accepted,issues=validate_evidence(self.result.observations,self.result.documents)
        self.assertFalse(issues)
        self.assertEqual(len(accepted),len(self.result.observations))

    def test_cache_resume(self):
        extractor=LocalExtractor()
        extractor.extract=Mock(side_effect=AssertionError('should use cache'))
        resumed=run(ROOT/'examples/case.json',extractor,self.store)
        self.assertEqual(resumed.recommendation.status,'APPROVE')
        self.assertTrue(all(t['cached'] for t in resumed.trace if t['stage']=='extract'))
        self.assertNotEqual(resumed.run_id,self.result.run_id)

    def test_all_four_conditions_required(self):
        for field in ['suspicious_nodule','tissue_sampling','procedure_supported','labs_acceptable','pulmonary_acceptable']:
            remaining=[o for o in self.result.observations if o.field!=field]
            self.assertEqual(decide(remaining,self.result.documents,[]).status,'MANUAL_REVIEW',field)

    def test_conflict_blocks(self):
        observations=self.result.observations+[obs('mrn','999','clinical')]
        issues=validate_case(self.result.documents,observations)
        self.assertIn('material_conflict',{i.code for i in issues})
        self.assertEqual(decide(observations,self.result.documents,issues).status,'MANUAL_REVIEW')

    def test_contraindication_blocks(self):
        o=self.result.observations+[obs('contraindication',True,'labs')]
        self.assertEqual(decide(o,self.result.documents,[]).status,'MANUAL_REVIEW')

    def test_missing_document_blocks(self):
        docs=[d for d in self.result.documents if d.role!='labs']
        observations=[o for o in self.result.observations if o.evidence.document_id!='labs']
        issues=validate_case(docs,observations)
        self.assertEqual(decide(observations,docs,issues).status,'MANUAL_REVIEW')

    def test_missing_file_partial_not_approval(self):
        entries=json.loads((ROOT/'examples/case.json').read_text())
        for e in entries['documents']: e['path']=str(ROOT/'examples'/e['path'])
        entries['documents'][2]['path']='/nonexistent.pdf'
        manifest=Path(self.tmp.name)/'missing.json'; manifest.write_text(json.dumps(entries))
        result=run(manifest,LocalExtractor(),self.store)
        self.assertEqual(result.run_status,'partial')
        self.assertEqual(result.recommendation.status,'MANUAL_REVIEW')
        self.assertIn('read_failed',{i.code for i in result.issues})

    def test_report_escapes_input(self):
        modified=self.result.model_copy(update={'extraction_mode':'<script>alert(1)</script>'})
        self.assertNotIn('<script>',render(modified))
        self.assertIn('&lt;script&gt;',render(modified))

class EvidenceTests(unittest.TestCase):
    def test_fabricated_quote_rejected(self):
        valid,issues=validate_evidence([obs('finding','nodule',quote='Never existed')],[doc()])
        self.assertFalse(valid);self.assertEqual(issues[0].code,'invalid_evidence')
    def test_wrong_page_rejected(self):
        o=obs('finding','nodule').model_copy(update={'evidence':Evidence(document_id='ct',page=3,quote='Evidence text')})
        self.assertTrue(validate_evidence([o],[doc()])[1])
    def test_number_not_in_quote_rejected(self):
        self.assertTrue(validate_evidence([obs('fev1_percent',99,quote='FEV1 62% predicted')],[doc('FEV1 62% predicted')])[1])
    def test_unicode_valid(self):
        self.assertTrue(text_quality('שלום עולם مرحبا بالعالم µL ≥8mm 62%')[0])
    def test_corruption_detected(self):
        self.assertFalse(text_quality('Bad \ufffd\ufffd\ufffd text')[0])
    def test_typed_schema_rejects_boolean_string(self):
        with self.assertRaises(ValueError): obs('tissue_sampling','true')

class ProviderTests(unittest.TestCase):
    def test_transient_retry_bounded(self):
        call=Mock(side_effect=TransientFailure());sleep=Mock()
        with self.assertRaises(TransientFailure): retry(call,sleep=sleep,jitter=lambda:0)
        self.assertEqual(call.call_count,3);self.assertEqual(sleep.call_count,2)
    def test_permanent_not_retried(self):
        call=Mock(side_effect=PermanentFailure())
        with self.assertRaises(PermanentFailure): retry(call,sleep=Mock())
        self.assertEqual(call.call_count,1)
    def test_claude_structured_transport(self):
        transport=Mock(return_value={'stop_reason':'tool_use','content':[{'type':'tool_use','name':'submit_extraction','input':{'observations':[]}}]})
        client=ClaudeExtractor('test','test-model',transport)
        self.assertEqual(client.extract(doc()).observations,[])
        body=transport.call_args.args[0]
        self.assertEqual(body['tool_choice']['name'],'submit_extraction')
        self.assertIn('untrusted',body['system'])
    def test_schema_repair_once(self):
        transport=Mock(return_value={'content':[]})
        with self.assertRaises(InvalidModelOutput): ClaudeExtractor('test','test-model',transport).extract(doc())
        self.assertEqual(transport.call_count,2)
    def test_truncation_never_silently_accepted(self):
        transport=Mock(return_value={'stop_reason':'max_tokens','content':[]})
        with self.assertRaises(InvalidModelOutput): ClaudeExtractor('test','test-model',transport).extract(doc())
    def test_changed_identity_misses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'runs.sqlite')
            store.put('model-A',Extraction(observations=[]))
            self.assertIsNone(store.get('model-B'));store.close()

class ReaderTests(unittest.TestCase):
    def test_text_bom_and_unicode(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'text.txt';p.write_text('שלום עולם مرحبا بالعالم µL ≥8mm',encoding='utf-16')
            self.assertTrue(TextReader().read(p)[0].usable)
    def test_docx_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'file.docx';d=WordDocument();d.add_paragraph('Clinical document')
            t=d.add_table(rows=1,cols=2);t.cell(0,0).text='FEV1';t.cell(0,1).text='62%';d.save(p)
            self.assertIn('FEV1 | 62%',DocxReader().read(p)[0].text)
    def test_blank_pdf_not_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'blank.pdf';d=pymupdf.open();d.new_page();d.save(p);d.close()
            self.assertFalse(PdfReader().read(p)[0].usable)
    def test_ocr_fallback_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'blank.pdf';d=pymupdf.open();d.new_page();d.save(p);d.close()
            with patch('approval.readers.pdf.subprocess.run') as call:
                call.return_value.stdout=b'Scanned clinical evidence with FEV1 62% predicted'
                page=PdfReader(ocr=True).read(p)[0]
                self.assertTrue(page.usable);self.assertEqual(page.method,'ocr');call.assert_called_once()
    def test_failed_ocr_stays_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'blank.pdf';d=pymupdf.open();d.new_page();d.save(p);d.close()
            with patch('approval.readers.pdf.subprocess.run',side_effect=OSError()):
                self.assertFalse(PdfReader(ocr=True).read(p)[0].usable)

class ScopedConflictTests(unittest.TestCase):
    def test_procedure_from_non_request_document_is_not_a_conflict(self):
        docs=[Document(id=i,filename=i,role=i,sha256=i,pages=[Page(number=1,text='x'*20,method='text')]) for i in ('request','ct')]
        def obs(doc,value): return Observation(field='procedure',value=value,evidence=Evidence(document_id=doc,page=1,quote='xxx'))
        issues=validate_case(docs,[obs('request','Robotic Biopsy'),obs('ct','CT Chest Screening')])
        self.assertNotIn('Conflicting procedure; all observations retained',[i.detail for i in issues])
        issues=validate_case(docs,[obs('request','Robotic Biopsy'),obs('request','Other Procedure')])
        self.assertIn('Conflicting procedure; all observations retained',[i.detail for i in issues])

if __name__=='__main__': unittest.main()
