"""The lung-biopsy profile end to end: real PDFs, evidence checks and decisions; only Ollama is replaced."""
import copy
import json
from pathlib import Path

import pytest

from approval.check import number_supports_field
from approval.workflow import run_case
from tests.support import fact, pdf

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ['Patient: DOE, JANE', 'DOB: 03/15/1952', 'MRN: 847291']
APPROACH = 'Robotic bronchoscopic approach suits this peripheral lesion.'
PAIRED = 'FEV1 62% predicted and DLCO 58% predicted.'
PAGES = {
    'request': ['Beneficiary Name: DOE, JANE', 'Date of Birth: 03/15/1952', 'Tracking #: PA-TEST-1',
                'Procedure/Service: Robotic-Assisted Transbronchial Lung Biopsy', 'CPT Code(s): 31629, 31632',
                'Requested DOS: December 10, 2025', 'Chief complaint: incidental right upper lobe nodule.', APPROACH],
    'clinical': IDENTITY + ['Right upper lobe nodule, suspicious for malignancy.', 'Tissue diagnosis is warranted.', APPROACH],
    'ct': IDENTITY + ['18 x 15 mm nodule in the right upper lobe.', '4 mm nodule in the left lower lobe, likely benign.',
                      'Lung-RADS Category: 4B', 'Impression: Right upper lobe nodule, suspicious for malignancy.',
                      'Tissue sampling recommended.'],
    'labs': IDENTITY + ['No evidence of coagulopathy.', 'Patient is suitable for invasive procedures.'],
    'pft': IDENTITY + [PAIRED, 'FEV1 >60% predicted suggests adequate reserve.',
                       'The patient would tolerate bronchoscopic procedures.'],
}
PATIENT = {'patient_name': fact('DOE, JANE', 'DOE, JANE'), 'date_of_birth': fact('1952-03-15', 'DOB: 03/15/1952'),
           'mrn': fact('847291', 'MRN: 847291')}
ANSWERS = {
    'request': {'patient_name': fact('DOE, JANE', 'Beneficiary Name: DOE, JANE'),
                'date_of_birth': fact('03/15/1952', 'Date of Birth: 03/15/1952'),
                'case_id': fact('PA-TEST-1', 'Tracking #: PA-TEST-1'),
                'procedure': fact('Robotic-Assisted Transbronchial Lung Biopsy', 'Procedure/Service: Robotic-Assisted Transbronchial Lung Biopsy'),
                'cpt_codes': fact(['31629', '31632'], 'CPT Code(s): 31629, 31632'),
                'requested_date': fact('2025-12-10', 'Requested DOS: December 10, 2025'),
                'rationale': [fact('incidental right upper lobe nodule', 'Chief complaint: incidental right upper lobe nodule.'),
                              fact(APPROACH, APPROACH)],
                'procedure_supported': fact(True, APPROACH)},
    'clinical': {**PATIENT, 'suspicious_nodule': fact(True, 'Right upper lobe nodule, suspicious for malignancy.'),
                 'tissue_sampling': fact(True, 'Tissue diagnosis is warranted.'),
                 'procedure_supported': fact(True, APPROACH)},
    'ct': {**PATIENT,
           'finding': fact('Right upper lobe nodule, suspicious for malignancy', 'Impression: Right upper lobe nodule, suspicious for malignancy.'),
           'location': [fact('left lower lobe', '4 mm nodule in the left lower lobe, likely benign.'),
                        fact('right upper lobe', '18 x 15 mm nodule in the right upper lobe.')],
           'nodule_size': [fact('4 mm', '4 mm nodule in the left lower lobe, likely benign.'),
                           fact('18 x 15 mm', '18 x 15 mm nodule in the right upper lobe.')],
           'lung_rads': fact('4B', 'Lung-RADS Category: 4B'),
           'suspicious_nodule': fact(True, 'Impression: Right upper lobe nodule, suspicious for malignancy.'),
           'tissue_sampling': fact(True, 'Tissue sampling recommended.')},
    'labs': {**PATIENT, 'coagulation_status': fact('Normal', 'No evidence of coagulopathy.'),
             'labs_acceptable': fact(True, 'Patient is suitable for invasive procedures.')},
    'pft': {**PATIENT,
            'fev1_percent': [fact(60.0, 'FEV1 >60% predicted suggests adequate reserve.'), fact(62.0, PAIRED), fact(58.0, PAIRED)],
            'dlco_percent': [fact(58.0, PAIRED), fact(62.0, PAIRED)],
            'pulmonary_acceptable': fact(True, 'The patient would tolerate bronchoscopic procedures.')},
}


@pytest.fixture
def lung_packet(tmp_path):
    """Build the five-document packet; pages can be overridden and roles omitted."""
    def build(pages=None, omit=()):
        texts = {**PAGES, **(pages or {})}
        for role, lines in texts.items():
            pdf(tmp_path / f'{role}.pdf', ['\n'.join(lines)])
        documents = [{'id': role, 'role': role, 'path': f'{role}.pdf'} for role in texts if role not in omit]
        path = tmp_path / 'case.json'
        path.write_text(json.dumps({'profile': 'lung_biopsy', 'documents': documents}), encoding='utf-8')
        return path
    return build


def answers_with(change=None):
    def extract(role, _text, _model):
        answers = copy.deepcopy(ANSWERS[role])
        if change: change(role, answers)
        return answers
    return extract


def test_complete_packet_is_approved_with_the_assignment_summary(lung_packet):
    result = run_case(lung_packet(), 'test', answers_with(), language='en')
    assert result['recommendation']['status'] == 'APPROVE'
    assert all(rule['met'] for rule in result['rules'])
    assert result['case_id'] == 'PA-TEST-1'
    assert result['patient'] == {'name': 'Jane Doe', 'date_of_birth': '1952-03-15', 'mrn': '847291'}
    assert result['request']['procedure'] == 'Robotic-Assisted Transbronchial Lung Biopsy'
    assert result['request']['cpt_codes'] == ['31629', '31632']
    assert result['request']['requested_date'] == '2025-12-10'
    summary = result['clinical_summary']
    assert summary['finding'] == 'Right upper lobe nodule, suspicious for malignancy'
    assert summary['location'] == 'right upper lobe' and summary['nodule_size'] == '18 x 15 mm'
    assert summary['lung_rads'] == '4B' and summary['coagulation_status'] == 'Normal'
    assert summary['fev1_percent'] == 62 and summary['dlco_percent'] == 58
    assert summary['rationale'] == APPROACH
    assert not any(issue['severity'] == 'blocking' for issue in result['issues'])
    assert any(issue['code'] == 'summary_selected' for issue in result['issues'])


@pytest.mark.parametrize(('language', 'expected'), [
    ('en', 'suspicious nodule in the right upper lobe (18 x 15 mm, Lung-RADS 4B)'),
    ('he', 'FEV1 62% מהצפוי, DLCO 58% מהצפוי'),
])
def test_approval_reason_is_filled_from_verified_values(lung_packet, language, expected):
    result = run_case(lung_packet(), 'test', answers_with(), language=language)
    assert expected in result['recommendation']['reason']
    assert '{' not in result['recommendation']['reason']


def test_approval_reason_falls_back_when_a_summary_value_is_missing(lung_packet):
    result = run_case(lung_packet(), 'test', answers_with(_drop({'ct': ['lung_rads']})), language='en')
    assert result['recommendation']['status'] == 'APPROVE'
    assert result['recommendation']['reason'] == 'All required review criteria are supported by verified document evidence.'


def test_approval_reason_cannot_reference_unmapped_values():
    from approval.profiles import Profile, load_profile
    profile = load_profile('lung_biopsy').model_dump(mode='json')
    profile['approval_reason']['en'] += ' {facts.secret}'
    with pytest.raises(ValueError, match='unmapped'): Profile.model_validate(profile)


def test_numbers_are_bound_to_their_measurement_and_thresholds_are_rejected(lung_packet):
    result = run_case(lung_packet(), 'test', answers_with(), language='en')
    assert [c['value'] for c in result['facts']['pft']['fev1_percent']] == [62.0]
    assert [c['value'] for c in result['facts']['pft']['dlco_percent']] == [58.0]


@pytest.mark.parametrize(('value', 'quote', 'terms', 'expected'), [
    (62.0, PAIRED, ['fev1'], True),
    (58.0, PAIRED, ['fev1'], False),
    (58.0, PAIRED, ['dlco'], True),
    (62.0, 'FEV1 (L) 1.52 2.45 62%', ['fev1'], True),
    (1.52, 'FEV1 (L) 1.52 2.45 62%', ['fev1'], False),
    (64.0, 'FEV1/FVC 64%', ['fev1'], False),
    (60.0, 'FEV1 >60% predicted', ['fev1'], False),
    (62.0, 'FEV1 טרום מרחיב סימפונות: 62% מהצפוי', ['fev1'], True),
])
def test_percent_binding(value, quote, terms, expected):
    assert number_supports_field(value, quote, terms, percent=True) is expected


def _drop(role_fields):
    def change(role, answers):
        for field in role_fields.get(role, ()): answers.pop(field, None)
    return change


def _set(role, field, value):
    def change(current, answers):
        if current == role: answers[field] = value
    return change


@pytest.mark.parametrize(('pages', 'omit', 'change', 'expected'), [
    pytest.param(None, (), _drop({'ct': ['suspicious_nodule'], 'clinical': ['suspicious_nodule']}), 'rule_1', id='no-suspicion'),
    pytest.param(None, (), _set('ct', 'tissue_sampling', fact(True, 'Biopsy is strongly recommended.')), 'invalid_evidence', id='invented-quote'),
    pytest.param(None, (), _set('labs', 'contraindication', fact(True, 'No evidence of coagulopathy.')), 'blocker', id='contraindication'),
    pytest.param({'labs': ['Patient: DOE, JANE', 'DOB: 01/01/1960', 'MRN: 847291', 'Patient is suitable for invasive procedures.']}, (),
                 _set('labs', 'date_of_birth', fact('1960-01-01', 'DOB: 01/01/1960')), 'identity_mismatch', id='different-patient'),
    pytest.param(None, ('labs',), None, 'missing_document', id='missing-document'),
    pytest.param(None, (), _drop({'request': ['procedure']}), 'missing_field', id='missing-procedure'),
    pytest.param(None, (), _drop({'pft': ['mrn']}), 'missing_field', id='missing-mrn'),
])
def test_unsupported_packet_needs_manual_review(lung_packet, pages, omit, change, expected):
    result = run_case(lung_packet(pages, omit), 'test', answers_with(change), language='en')
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    failed_rules = {rule['id'] for rule in result['rules'] if not rule['met']}
    assert expected in failed_rules or any(issue['code'] == expected for issue in result['issues'])


def test_hebrew_reason_names_the_mismatched_identity_field(lung_packet):
    pages = {'labs': ['Patient: DOE, JANE', 'DOB: 01/01/1960', 'MRN: 847291', 'Patient is suitable for invasive procedures.']}
    change = _set('labs', 'date_of_birth', fact('1960-01-01', 'DOB: 01/01/1960'))
    result = run_case(lung_packet(pages), 'test', answers_with(change), language='he')
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert 'תאריך הלידה' in result['recommendation']['reason']


def test_supplied_pdfs_are_read_and_one_failure_does_not_stop_the_rest():
    seen = []

    def fake_model(role, text, model):
        seen.append(role)
        if role == 'labs': raise RuntimeError('model crashed')
        assert 'JOHNSON' in text
        return {}

    result = run_case(ROOT / 'case.json', 'fake', fake_model)
    assert seen == ['request', 'clinical', 'ct', 'labs', 'pft']
    assert result['recommendation']['status'] == 'MANUAL_REVIEW'
    assert any(issue['code'] == 'document_failed' and 'RuntimeError' in issue['detail'] for issue in result['issues'])
