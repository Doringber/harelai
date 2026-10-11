"""Real local-LLM checks. Every scenario is run in both languages and compared."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from approval.workflow import compare_runs, dump

CASES = {
    'medical': ('case.json', 'APPROVE'),
    'medical_hebrew': ('examples/hebrew_medical/case.json', 'APPROVE'),
    'medical_alternate': ('ai/alternate_case/case.json', 'MANUAL_REVIEW'),
    'invoice': ('examples/invoice/case.json', 'APPROVE'),
    'over_limit': ('examples/invoice/over_limit_case.json', 'MANUAL_REVIEW'),
    'missing_goods': ('examples/invoice/missing_goods_case.json', 'MANUAL_REVIEW'),
    'conflict': ('examples/invoice/conflict_case.json', 'MANUAL_REVIEW'),
    'custom_profile': ('examples/invoice/custom_case.json', 'MANUAL_REVIEW'),
    'long': ('examples/invoice/long_case.json', 'APPROVE'),
    'scanned': ('examples/invoice/scanned_case.json', 'APPROVE'),
}


def fact_checks(name, result):
    """A negative status must be supported by the expected facts, not an unrelated failure."""
    facts = result['facts']
    def values(doc_id, field):
        return [candidate['value'] for candidate in facts.get(doc_id, {}).get(field, [])]
    checks = {'critical_evidence_verified': not any(issue['severity'] == 'blocking' and
        issue['code'] not in ('conflicting_values',) for issue in result['issues'])}
    rules = {rule['id']: rule['met'] for rule in result['rules']}
    if name.startswith('medical'):
        checks['patient_identity_extracted'] = len(facts) == 5 and all(
            fields.get('patient_name') and fields.get('date_of_birth') for fields in facts.values())
        if name in ('medical', 'medical_hebrew'):
            checks['all_medical_rules_met'] = all(rules.values())
            request, summary = result.get('request', {}), result.get('clinical_summary', {})
            required = [result.get('case_id'), *result.get('patient', {}).values(), request.get('procedure'),
                        request.get('cpt_codes'), request.get('requested_date'), summary.get('finding'),
                        summary.get('nodule_size'), summary.get('lung_rads'), summary.get('coagulation_status')]
            checks['assignment_summary_complete'] = all(value not in (None, '', []) for value in required)
            checks['pulmonary_values_bound'] = summary.get('fev1_percent') == 62 and summary.get('dlco_percent') == 58
            if name == 'medical':
                checks['supplied_case_values'] = (result.get('case_id') == 'PA-2025-847291' and summary.get('lung_rads') == '4B'
                                                  and request.get('cpt_codes') == ['31629', '31632', '77012']
                                                  and request.get('requested_date') == '2025-12-10')
        else: checks['suspicion_and_sampling_not_supported'] = rules.get('rule_1') is False and rules.get('rule_2') is False
    else:
        amount = 1850 if name == 'over_limit' else 850
        checks['amount_extracted'] = bool(values('invoice-1','total_amount')) and all(value == amount for value in values('invoice-1','total_amount'))
        checks['invoice_identity_extracted'] = all(values(doc['id'], 'invoice_number') == ['INV-1001'] for doc in result['documents'])
        receipt = 'receipt-2' if name == 'conflict' else 'receipt-1'
        if name in ('missing_goods','conflict'):
            checks['negative_receipt_retained'] = values(receipt, 'goods_received') == [False]
            checks['receipt_rule_failed'] = rules.get('received') is False
        else: checks['positive_receipt_retained'] = values('receipt-1', 'goods_received') == [True]
        if name == 'conflict':
            checks['positive_receipt_retained'] = values('receipt-1', 'goods_received') == [True]
            checks['contradiction_reported'] = any(issue['code'] == 'conflicting_values' for issue in result['issues'])
        if name in ('over_limit','custom_profile'): checks['amount_rule_failed'] = rules.get('amount_limit') is False
        if name == 'custom_profile': checks['custom_profile_selected'] = result['workflow']['name'] == 'invoice_small_limit'
        if name == 'long':
            checks['late_page_evidence_retained'] = any(source.get('page') == 3 for fact in facts.get('invoice-1',{}).get('total_amount',[]) for source in fact['sources'])
        if name == 'scanned':
            checks['ocr_evidence_retained'] = any(source.get('ocr') is True for fact in facts.get('invoice-1',{}).get('total_amount',[]) for source in fact['sources'])
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='gemma4')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--tessdata', type=Path, required=True, help='eng/heb traineddata directory for scanned case')
    parser.add_argument('--case', choices=list(CASES), action='append', help='run only selected scenarios')
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if any(args.output_dir.iterdir()): parser.error('Choose a new/empty output directory')
    report = {'model': args.model, 'cases': [], 'passed': True}
    for name in args.case or CASES:
        case, expected = CASES[name]
        results, runs = [], []
        for language in ('he', 'en'):
            directory = args.output_dir / name / language
            command = [sys.executable, '-u', '-m', 'approval', str(ROOT / case),
                       '--model', args.model, '--language', language, '--output-dir', str(directory)]
            if name == 'scanned': command += ['--ocr', '--tessdata', str(args.tessdata.resolve())]
            print(f'Running {name} ({language}); expected {expected}', flush=True)
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'terminal.log').write_text(process.stdout + process.stderr, encoding='utf-8')
            print(process.stdout, flush=True)
            if process.stderr: print(process.stderr, flush=True)
            path = directory / 'result.json'
            result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
            status = result['recommendation']['status'] if result else None
            checks = fact_checks(name, result) if result else {'result_available': False}
            runs.append({'language': language, 'exit_code': process.returncode, 'status': status,
                         'expected': expected, 'fact_checks': checks,
                         'passed': process.returncode == 0 and status == expected and all(checks.values())})
            if result: results.append(result)
        comparison = compare_runs(results) if len(results) == 2 else {'stable': False}
        check = {'case': name, 'runs': runs, 'comparison': comparison,
                 'passed': all(run['passed'] for run in runs) and comparison['stable']}
        report['cases'].append(check)
        report['passed'] = report['passed'] and check['passed']
        dump(args.output_dir / 'report.json', report)
        print(f'{name}: passed={check["passed"]}, stable={comparison["stable"]}', flush=True)
    print(f'Report: {args.output_dir / "report.json"}', flush=True)
    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__': main()
