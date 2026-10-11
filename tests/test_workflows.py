"""Exercise real readers, evidence checks, decisions and artifacts; replace only Ollama."""
import copy
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pymupdf
import pytest

from approval.workflow import run_case
from tests.support import docx, fact, pdf


@pytest.fixture
def invoice_case(tmp_path):
    pdf(tmp_path / 'invoice.pdf', ['Invoice Number: INV-1001\nTotal amount: 850.00 USD\nVendor: Example Supplies Ltd.'])
    docx(tmp_path / 'receipt.docx', ['מספר חשבונית: INV-1001', 'הסחורה התקבלה במלואה.'])
    case = {"profile": "invoice_payment", "documents": [
        {"id": "invoice-1", "role": "invoice", "path": "invoice.pdf"},
        {"id": "receipt-1", "role": "receipt", "path": "receipt.docx"}]}
    path = tmp_path / 'case.json'
    path.write_text(json.dumps(case), encoding='utf-8')
    return path


def invoice_answers(role, text, model):
    if role == 'invoice':
        return {"invoice_number": fact('INV-1001', 'Invoice Number: INV-1001'),
                "total_amount": fact(850.0, 'Total amount: 850.00 USD'),
                "vendor": fact('Example Supplies Ltd.', 'Vendor: Example Supplies Ltd.')}
    return {"invoice_number": fact('INV-1001', 'מספר חשבונית: INV-1001'),
            "goods_received": fact(True, 'הסחורה התקבלה במלואה.')}


def test_different_workflow_reads_pdf_and_hebrew_docx(invoice_case, tmp_path):
    result = run_case(invoice_case, 'test', invoice_answers, language='en', output_dir=tmp_path / 'run')
    assert result['recommendation']['status'] == 'APPROVE'
    assert 'supported' in result['recommendation']['reason']
    assert result['workflow']['name'] == 'invoice_payment'
    assert result['facts']['invoice-1']['total_amount'][0]['value'] == 850
    evidence = result['facts']['receipt-1']['goods_received'][0]['sources'][0]
    assert evidence['paragraph'] == 2 and evidence['document_id'] == 'receipt-1'
    assert evidence['quote'] == 'הסחורה התקבלה במלואה.'
    assert result['facts']['invoice-1']['total_amount'][0]['sources'][0]['page'] == 1
    for name in ['result.json', 'facts.json', 'evidence.json', 'texts.json', 'profile.json', 'manifest.json', 'events.jsonl', 'model.jsonl']:
        assert (tmp_path / 'run' / name).exists()
    events = [json.loads(line) for line in (tmp_path / 'run' / 'events.jsonl').read_text().splitlines()]
    assert events[-1]['event'] == 'completed'
    assert json.loads((tmp_path / 'run' / 'manifest.json').read_text())['documents'][0]['sha256']


def test_language_changes_explanation_not_decision_or_facts(invoice_case):
    he = run_case(invoice_case, 'test', invoice_answers, language='he')
    en = run_case(invoice_case, 'test', invoice_answers, language='en')
    assert 'נתמכים' in he['recommendation']['reason']
    assert he['recommendation']['status'] == en['recommendation']['status'] == 'APPROVE'
    assert he['facts'] == en['facts']
    assert he['rules'][0]['label'] != en['rules'][0]['label']


def test_duplicate_roles_preserve_both_documents_and_negative_evidence(invoice_case):
    config = json.loads(invoice_case.read_text())
    docx(invoice_case.parent / 'no.docx', ['מספר חשבונית: INV-1001', 'Goods have not been received.'])
    config['documents'].append({'id': 'receipt-2', 'role': 'receipt', 'path': 'no.docx'})
    invoice_case.write_text(json.dumps(config))
    def extract(role, text, model):
        if 'not been received' in text:
            return {'invoice_number': fact('INV-1001', 'מספר חשבונית: INV-1001'),
                    'goods_received': fact(False, 'Goods have not been received.')}
        return invoice_answers(role, text, model)
    result = run_case(invoice_case, 'test', extract, language='en')
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert set(result['facts']) == {'invoice-1', 'receipt-1', 'receipt-2'}
    assert any(i['code'] == 'conflicting_values' for i in result['issues'])


@pytest.mark.parametrize('change', ['quote', 'number', 'missing', 'identity', 'limit'])
def test_bad_evidence_and_failed_rules_cannot_approve(invoice_case, change):
    def extract(role, text, model):
        answers = invoice_answers(role, text, model)
        if role == 'invoice':
            if change == 'quote': answers['total_amount']['quote'] = 'Invented amount: 850.00'
            if change == 'number': answers['total_amount']['value'] = 999.0
            if change == 'missing': answers.pop('total_amount')
            if change == 'limit': answers['total_amount'] = fact(1850.0, 'Total amount: 1850.00 USD')
        elif change == 'identity': answers['invoice_number'] = fact('INV-1002', 'מספר חשבונית: INV-1002')
        return answers
    if change == 'limit': pdf(invoice_case.parent / 'invoice.pdf', ['Invoice Number: INV-1001\nTotal amount: 1850.00 USD\nVendor: Example Supplies Ltd.'])
    if change == 'identity': docx(invoice_case.parent / 'receipt.docx', ['מספר חשבונית: INV-1002', 'הסחורה התקבלה במלואה.'])
    assert run_case(invoice_case, 'test', extract, language='en')['recommendation']['status'] == 'MANUAL_REVIEW'


def test_failed_document_is_logged_and_other_documents_are_processed(invoice_case, tmp_path):
    (invoice_case.parent / 'invoice.pdf').unlink()
    result = run_case(invoice_case, 'test', invoice_answers, language='en', output_dir=tmp_path / 'run')
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert 'receipt-1' in result['facts']
    events = (tmp_path / 'run' / 'events.jsonl').read_text()
    assert 'document_failed' in events and 'FileNotFoundError' in events
    assert 'Unable to process' in result['issues'][0]['detail']


@pytest.mark.parametrize('change', ['duplicate_id', 'unknown_role', 'unknown_profile'])
def test_invalid_case_fails_before_processing(invoice_case, change):
    case = json.loads(invoice_case.read_text())
    if change == 'duplicate_id': case['documents'][1]['id'] = 'invoice-1'
    if change == 'unknown_role': case['documents'][1]['role'] = 'random'
    if change == 'unknown_profile': case['profile'] = 'missing-workflow'
    invoice_case.write_text(json.dumps(case))
    with pytest.raises(ValueError): run_case(invoice_case, 'test', invoice_answers)


def test_custom_profile_is_loaded_relative_to_case(invoice_case):
    from approval.profiles import load_profile
    profile = load_profile('invoice_payment').model_dump(mode='json')
    profile['name'] = 'custom_invoice'
    profile['rules'][0]['conditions'][0]['value'] = 500
    (invoice_case.parent / 'profile.json').write_text(json.dumps(profile))
    case = json.loads(invoice_case.read_text()); case['profile'] = 'profile.json'
    invoice_case.write_text(json.dumps(case))
    result = run_case(invoice_case, 'test', invoice_answers)
    assert result['workflow']['name'] == 'custom_invoice'
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'


def test_long_document_keeps_late_and_conflicting_evidence(tmp_path):
    from approval.read import read_document
    from approval.extract import extract_document
    from approval.profiles import load_profile
    pdf(tmp_path / 'long.pdf', ['Nothing relevant here.\n' * 20, 'Invoice Number: INV-1001\nTotal amount: 850.00 USD', 'Total amount: 1850.00 USD'])
    doc = read_document(tmp_path / 'long.pdf', 'invoice-1', 'invoice')
    def ask(field, text, model, spec):
        if field == 'total_amount' and '1850.00' in text: return fact(1850.0, 'Total amount: 1850.00 USD')
        if field == 'total_amount' and '850.00' in text: return fact(850.0, 'Total amount: 850.00 USD')
        if field == 'invoice_number' and 'INV-1001' in text: return fact('INV-1001', 'Invoice Number: INV-1001')
        return None
    answers, failures = extract_document(doc, load_profile('invoice_payment'), 'test', ask_fn=ask, chunk_size=180)
    assert not failures
    assert {a['value'] for a in answers['total_amount']} == {850.0, 1850.0}


def test_repeat_comparison_ignores_language_and_detects_fact_changes(invoice_case):
    from approval.workflow import compare_runs
    a = run_case(invoice_case, 'test', invoice_answers, language='he')
    b = run_case(invoice_case, 'test', invoice_answers, language='en')
    assert compare_runs([a, b])['stable'] is True
    b = copy.deepcopy(b); b['facts']['invoice-1']['total_amount'][0]['value'] = 851
    assert compare_runs([a, b])['stable'] is False


def test_unknown_format_and_scanned_pdf_fail_explicitly(tmp_path):
    from approval.read import read_document
    (tmp_path / 'data.xyz').write_text('unsupported')
    with pytest.raises(ValueError, match='Unsupported'): read_document(tmp_path / 'data.xyz', 'd', 'invoice')
    doc = pymupdf.open(); doc.new_page(); doc.save(tmp_path / 'scan.pdf'); doc.close()
    with pytest.raises(ValueError, match='OCR'): read_document(tmp_path / 'scan.pdf', 'd', 'invoice')


def test_cli_invalid_language_and_profile_have_nonzero_exit(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for args in [['--language', 'fr'], ['--profile', 'does-not-exist']]:
        p = subprocess.run([sys.executable, '-m', 'approval', *args], cwd=root, capture_output=True, text=True)
        assert p.returncode != 0


def test_multiple_candidates_in_one_excerpt_are_kept(tmp_path):
    from approval.read import read_document
    from approval.extract import extract_document
    from approval.profiles import load_profile
    pdf(tmp_path / 'invoice.pdf', ['Total amount: 850.00 USD\nRevised total amount: 1850.00 USD'])
    document = read_document(tmp_path / 'invoice.pdf', 'invoice', 'invoice')
    def ask(field, text, model, spec):
        return [fact(850.0, 'Total amount: 850.00 USD'), fact(1850.0, 'Revised total amount: 1850.00 USD')] if field == 'total_amount' else None
    answers, failures = extract_document(document, load_profile('invoice_payment'), 'test', ask_fn=ask)
    assert not failures
    assert [a['value'] for a in answers['total_amount']] == [850.0, 1850.0]


def test_profile_cannot_override_computed_decision():
    from approval.profiles import load_profile, Profile
    profile = load_profile('invoice_payment').model_dump(mode='json')
    profile['output_fields']['recommendation.status'] = {'field': 'vendor', 'roles': ['invoice']}
    with pytest.raises(ValueError, match='reserved'): Profile.model_validate(profile)


def test_bounded_chunks_preserve_every_hebrew_character():
    from approval.read import text_chunks
    text = 'שלום עולם ' * 100
    chunks = list(text_chunks(text, 80))
    assert all(len(chunk.encode('utf-8')) <= 80 for chunk in chunks)
    assert chunks[0].startswith('שלום') and chunks[-1].endswith('עולם ')
    # Every original eight-character window must survive in some chunk.
    assert all(any(text[index:index+8] in chunk for chunk in chunks) for index in range(len(text)-8))


@pytest.mark.parametrize('change', ['date_type', 'numeric_threshold', 'unknown_field', 'empty_rules'])
def test_invalid_profile_is_rejected(change):
    from approval.profiles import load_profile, Profile
    profile = load_profile('invoice_payment').model_dump(mode='json')
    if change == 'date_type': profile['fields']['goods_received']['format'] = 'date'
    if change == 'numeric_threshold': profile['rules'][0]['conditions'][0]['value'] = 'many'
    if change == 'unknown_field': profile['rules'][0]['conditions'][0]['field'] = 'undefined'
    if change == 'empty_rules': profile['rules'] = []
    with pytest.raises(ValueError): Profile.model_validate(profile)


def test_ocr_reads_english_and_hebrew_from_real_pixels():
    from approval.read import read_document
    root = Path(__file__).resolve().parents[1]
    if not (root / '.ocr-data/heb.traineddata').exists():
        pytest.skip('Optional OCR test requires eng/heb data; see README')
    document = read_document(root / 'examples/invoice/scanned_invoice.pdf', 'scan', 'invoice',
                             ocr=True, tessdata=str(root / '.ocr-data'))
    assert 'INV-1001' in document.text and '850.00' in document.text
    assert 'מסמך בדיקה לדוגמה בעברית' in document.text
    assert document.units[0]['ocr'] is True


def test_docx_table_keeps_label_and_value_together(tmp_path):
    from approval.read import read_document
    from approval.extract import extract_document
    from approval.profiles import load_profile
    path = tmp_path / 'table.docx'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Total amount:</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>850.00 USD</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    document = read_document(path, 'invoice', 'invoice')
    def ask(field, text, model, spec):
        return fact(850, 'Total amount:\t850.00 USD') if field == 'total_amount' and 'Total amount:' in text and '850.00' in text else None
    answers, failures = extract_document(document, load_profile('invoice_payment'), 'test', ask_fn=ask)
    assert not failures and answers['total_amount'][0]['value'] == 850


def test_unverified_optional_summary_is_dropped_without_changing_valid_decision(invoice_case):
    def extract(role, text, model):
        answers = invoice_answers(role, text, model)
        if role == 'invoice': answers['vendor']['quote'] = 'Invented vendor label: Example Supplies Ltd.'
        return answers
    result = run_case(invoice_case, 'test', extract, language='en')
    assert result['recommendation']['status'] == 'APPROVE'
    assert 'vendor' not in result['facts']['invoice-1']
    assert result['invoice']['vendor'] is None
    assert any(issue['code'] == 'invalid_evidence' and issue['severity'] == 'warning' for issue in result['issues'])


def test_mixed_text_and_scanned_page_does_not_hide_image_text(tmp_path):
    from approval.read import read_document
    root = Path(__file__).resolve().parents[1]
    if not (root / '.ocr-data/heb.traineddata').exists():
        pytest.skip('Optional OCR test requires eng/heb data; see README')
    with pymupdf.open(root / 'examples/invoice/scanned_invoice.pdf') as source:
        source[0].insert_text((50, 800), 'Scanned packet - page 1')
        source.save(tmp_path / 'mixed.pdf')
    with pytest.raises(ValueError, match='OCR'):
        read_document(tmp_path / 'mixed.pdf', 'mixed', 'invoice')
    document = read_document(tmp_path / 'mixed.pdf', 'mixed', 'invoice', ocr=True, tessdata=str(root / '.ocr-data'))
    assert 'INV-1001' in document.text and 'Scanned packet' in document.text
    assert document.units[0]['ocr'] is True


def test_one_failed_model_field_does_not_stop_other_extractions(invoice_case, monkeypatch, tmp_path):
    import approval.extract as extractor
    def ask(field, text, model, spec, **kwargs):
        if field == 'total_amount': raise RuntimeError('bad structured model output')
        if field == 'invoice_number':
            quote = 'מספר חשבונית: INV-1001' if 'מספר חשבונית' in text else 'Invoice Number: INV-1001'
            return [fact('INV-1001', quote)] if 'INV-1001' in text else []
        if field == 'goods_received' and 'הסחורה התקבלה' in text: return [fact(True, 'הסחורה התקבלה במלואה.')]
        return []
    monkeypatch.setattr(extractor, 'ask_configured', ask)
    result = run_case(invoice_case, 'test', language='en', output_dir=tmp_path / 'run')
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert result['facts']['receipt-1']['goods_received'][0]['value'] is True
    assert any(issue['code'] == 'extraction_failed' for issue in result['issues'])
    assert 'bad structured model output' in (tmp_path / 'run/model.jsonl').read_text()


def test_structured_response_validation_logs_raw_bad_answer(monkeypatch):
    import approval.extract as extractor
    from approval.profiles import load_profile
    import io
    def response(request, **kwargs):
        return io.BytesIO(json.dumps({'message':{'content':'{"total_amount": [{"found": true, "value": "not a number", "quote": "amount unknown"}]}'}}).encode())
    monkeypatch.setattr(extractor.urllib.request, 'urlopen', response)
    records = []
    with pytest.raises(ValueError):
        extractor.ask_configured('total_amount', 'amount unknown', 'test', load_profile('invoice_payment').fields['total_amount'], log=records.append)
    assert 'not a number' in records[0]['raw_response']


def test_missing_required_role_prevents_approval(invoice_case):
    case = json.loads(invoice_case.read_text()); case['documents'] = case['documents'][:1]
    invoice_case.write_text(json.dumps(case))
    result = run_case(invoice_case, 'test', invoice_answers, language='en')
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert any(i['code'] == 'missing_document' for i in result['issues'])


def test_existing_run_logs_are_not_overwritten(invoice_case, tmp_path):
    output = tmp_path / 'run'; output.mkdir(); (output / 'keep.txt').write_text('original evidence')
    with pytest.raises(ValueError, match='empty'): run_case(invoice_case, 'test', invoice_answers, output_dir=output)
    assert (output / 'keep.txt').read_text() == 'original evidence'


def test_failed_model_document_has_one_manifest_entry(invoice_case, tmp_path):
    def fail_invoice(role, text, model):
        if role == 'invoice': raise RuntimeError('Model unavailable')
        return invoice_answers(role, text, model)
    run_case(invoice_case, 'test', fail_invoice, output_dir=tmp_path / 'run')
    docs = json.loads((tmp_path / 'run/manifest.json').read_text())['documents']
    assert [doc['id'] for doc in docs] == ['invoice-1', 'receipt-1']
    assert docs[0]['sha256'] and docs[0]['error'] == 'Model unavailable'


def test_empty_required_list_is_not_verified_information(invoice_case):
    from approval.profiles import load_profile
    profile = load_profile('invoice_payment').model_dump(mode='json')
    profile['fields']['vendor']['type'] = 'text_list'
    profile['roles']['invoice']['required_fields'].append('vendor')
    (invoice_case.parent / 'profile.json').write_text(json.dumps(profile))
    def extract(role, text, model):
        answers = invoice_answers(role, text, model)
        if role == 'invoice': answers['vendor']['value'] = []
        return answers
    assert run_case(invoice_case, 'test', extract, profile=str(invoice_case.parent / 'profile.json'))['recommendation']['status'] == 'MANUAL_REVIEW'


def test_case_requires_json_object(tmp_path):
    path = tmp_path / 'case.json'; path.write_text('[]')
    with pytest.raises(ValueError, match='object'): run_case(path, 'test', invoice_answers)


def test_false_structured_value_is_present_evidence_without_a_found_flag(monkeypatch):
    import approval.extract as extractor
    from approval.profiles import load_profile
    import io
    def response(request, **kwargs):
        return io.BytesIO(json.dumps({'message': {'content': '{"goods_received": [{"mentioned": true, "quote": "הסחורה לא התקבלה.", "value": false}]}'}}).encode())
    monkeypatch.setattr(extractor.urllib.request, 'urlopen', response)
    result = extractor.ask_configured('goods_received', 'הסחורה לא התקבלה.', 'test', load_profile('invoice_payment').fields['goods_received'])
    assert result == [{'value': False, 'quote': 'הסחורה לא התקבלה.'}]


def test_live_check_cannot_pass_negative_case_only_because_evidence_is_missing(invoice_case):
    from scripts.verify_live import fact_checks
    def extract(role, text, model):
        answers = invoice_answers(role, text, model)
        if role == 'receipt': answers['goods_received'] = fact(False, 'Invented denial')
        return answers
    result = run_case(invoice_case, 'test', extract)
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    checks = fact_checks('missing_goods', result)
    assert checks['negative_receipt_retained'] is False
    assert checks['critical_evidence_verified'] is False


def test_equivalent_identity_spellings_do_not_erase_output_summary(invoice_case):
    docx(invoice_case.parent / 'receipt.docx', ['מספר חשבונית: inv-1001', 'הסחורה התקבלה במלואה.'])
    def extract(role, text, model):
        answers = invoice_answers(role, text, model)
        if role == 'receipt': answers['invoice_number'] = fact('inv-1001', 'מספר חשבונית: inv-1001')
        return answers
    result = run_case(invoice_case, 'test', extract)
    assert result['recommendation']['status'] == 'APPROVE'
    assert result['invoice']['number'] == 'INV-1001'


def test_unrelated_quote_cannot_prove_a_boolean_condition(invoice_case):
    def extract(role, text, model):
        answers = invoice_answers(role, text, model)
        if role == 'receipt': answers['goods_received'] = fact(True, 'מספר חשבונית: INV-1001')
        return answers
    result = run_case(invoice_case, 'test', extract)
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert not result['facts']['receipt-1'].get('goods_received')


def test_cli_exits_nonzero_when_a_document_cannot_be_read(tmp_path):
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'profile': 'invoice_payment', 'documents': [
        {'id': 'invoice-1', 'role': 'invoice', 'path': 'missing.pdf'},
        {'id': 'receipt-1', 'role': 'receipt', 'path': 'missing.docx'}]}), encoding='utf-8')
    out = tmp_path / 'run'
    process = subprocess.run([sys.executable, '-m', 'approval', str(case), '--language', 'en', '--output-dir', str(out)],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert process.returncode == 1
    assert 'FileNotFoundError' in process.stdout
    result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert any(issue['code'] == 'document_failed' and 'FileNotFoundError' in issue['detail'] for issue in result['issues'])


def test_unmentioned_boolean_is_not_a_false_contradiction(monkeypatch):
    import approval.extract as extractor
    from approval.profiles import load_profile
    import io
    def response(request, **kwargs):
        return io.BytesIO(json.dumps({'message': {'content': '{"tissue_sampling": [{"mentioned": false, "quote": "No family history.", "value": false}]}'}}).encode())
    monkeypatch.setattr(extractor.urllib.request, 'urlopen', response)
    assert extractor.ask_configured('tissue_sampling', 'No family history.', 'test', load_profile('lung_biopsy').fields['tissue_sampling']) == []
