import json
import os
import unittest
from unittest.mock import Mock, patch
from approval.ui.service import saved_case,execute_case,evidence_rows,live_ready,LiveBudget
from approval.ui.views import source_view,overview
from approval.extractors.groq import GroqExtractor
from approval.core.models import Document,Page
from approval.infrastructure.retry import InvalidModelOutput,PermanentFailure

class UITests(unittest.TestCase):
    def test_saved_scenarios(self):
        self.assertEqual(saved_case('Complete case').recommendation.status,'APPROVE')
        self.assertEqual(saved_case('Missing laboratory report').recommendation.status,'MANUAL_REVIEW')
    def test_synthetic_case_runs_core(self):
        result=execute_case('Complete case')
        self.assertEqual(result.recommendation.status,'APPROVE')
        self.assertEqual(result.patient['name'],'Alex T. Example')
    def test_live_disabled_server_side(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(live_ready())
            with self.assertRaises(ValueError): execute_case('Complete case',live=True)
    def test_live_requires_auth(self):
        with patch.dict(os.environ,{'GROQ_API_KEY':'test','ENABLE_LIVE':'1'},clear=True):
            self.assertFalse(live_ready())
    def test_live_groq_enabled(self):
        with patch.dict(os.environ,{'GROQ_API_KEY':'test','ENABLE_LIVE':'1','APP_USERNAME':'test','APP_PASSWORD':'test'},clear=True):
            self.assertTrue(live_ready())
    def test_run_cap(self):
        budget=LiveBudget(1);budget.reserve()
        with self.assertRaises(ValueError):budget.reserve()
    def test_filter(self):
        rows=evidence_rows(saved_case('Complete case'),'fev1_percent')
        self.assertTrue(rows)
        self.assertTrue(all('fev1_percent' in str(row) for row in rows))
    def test_source_highlight(self):
        self.assertIn('<mark>',source_view(saved_case('Complete case'),0))
    def test_baseline_label(self):
        self.assertIn('no model call',overview(saved_case('Complete case')))
    def test_no_original_patient_in_demo(self):
        text=saved_case('Complete case').model_dump_json()
        self.assertNotIn('847291',text)
        self.assertNotIn('JOHNSON',text)

class NormalizationTests(unittest.TestCase):
    def test_lung_rads_equivalent_labels(self):
        from approval.core.validation import canonical
        self.assertEqual(canonical("lung_rads","Category 4B"),canonical("lung_rads","4B"))
        self.assertNotEqual(canonical("lung_rads","4A"),canonical("lung_rads","4B"))

class GroqTests(unittest.TestCase):
    def document(self):
        return Document(id='ct',filename='ct.txt',role='ct',sha256='test',pages=[Page(number=1,text='A fictional lung nodule report.',method='text')])
    def test_request_contract(self):
        transport=Mock(return_value={'choices':[{'finish_reason':'stop','message':{'content':'{"observations":[]}'}}], 'usage':{'total_tokens':100}})
        client=GroqExtractor('test',transport=transport)
        self.assertEqual(client.extract(self.document()).observations,[])
        body=transport.call_args.args[0]
        self.assertEqual(body['model'],'openai/gpt-oss-120b')
        self.assertFalse(body['stream'])
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertEqual(body['temperature'],0)
        self.assertNotIn('submit_extraction',body['messages'][0]['content'])
        self.assertEqual(client.last_usage['total_tokens'],100)
    def test_truncated_response_rejected(self):
        transport=Mock(return_value={'choices':[{'finish_reason':'length','message':{'content':'{"observations":[]}'}}]})
        with self.assertRaises(InvalidModelOutput):GroqExtractor('test',transport=transport).extract(self.document())
        self.assertEqual(transport.call_count,2)
    def test_refusal_rejected(self):
        transport=Mock(return_value={'choices':[{'finish_reason':'stop','message':{'refusal':'test'}}]})
        with self.assertRaises(InvalidModelOutput):GroqExtractor('test',transport=transport).extract(self.document())
    def test_permanent_error_not_retried(self):
        transport=Mock(side_effect=PermanentFailure('provider_http_403'))
        with self.assertRaises(PermanentFailure):GroqExtractor('test',transport=transport).extract(self.document())
        self.assertEqual(transport.call_count,1)

if __name__=='__main__':unittest.main()
