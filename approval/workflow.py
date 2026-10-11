"""Reusable read → extract → verify → decide workflow with local run records."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from approval import __version__
from approval.check import display_name, normalize, number_supports_field, same_name, to_iso
from approval.extract import GENERIC_PROMPT, extract_document
from approval.profiles import PLACEHOLDER, load_profile
from approval.read import read_document

MESSAGES = {
 'document_failed': ('Unable to process {name} as {role}.', 'לא ניתן לעבד את הקובץ {name} עבור {role}.'),
 'missing_document': ('Missing document: {role}.', 'חסר מסמך: {role}.'),
 'missing_field': ('{role}: required field {field} is missing.', '{role}: חסר השדה הנדרש {field}.'),
 'invalid_evidence': ('{role}: evidence for {field} could not be verified.', '{role}: לא ניתן לאמת את הציטוט עבור {field}.'),
 'unrelated_evidence': ('{role}: the quote does not identify the subject of {field}; the value was omitted.', '{role}: הציטוט אינו מציין את נושא השדה {field}; הערך הושמט.'),
 'invalid_value': ('{role}: {field} has an invalid value or date.', '{role}: הערך או התאריך עבור {field} אינו תקין.'),
 'identity_mismatch': ('Documents disagree on {field}.', 'המסמכים אינם תואמים בפרט {field}.'),
 'conflicting_values': ('Conflicting evidence for {field}.', 'קיימות ראיות סותרות עבור {field}.'),
 'summary_selected': ('Several values were found for {field}; the summary shows the first one in the documents.', 'נמצאו כמה ערכים עבור {field}; בסיכום מוצג הראשון שמופיע במסמכים.'),
 'extraction_failed': ('{role}: extraction failed for {field}. See model.jsonl.', '{role}: חילוץ השדה {field} נכשל. פרטים בקובץ model.jsonl.'),
 'blocker': ('A blocking condition was documented: {field}.', 'תועד תנאי המונע אישור: {field}.'),
 'rule_failed': ('Required criterion is not supported: {label}.', 'תנאי נדרש אינו נתמך: {label}.'),
 'approved': ('All required review criteria are supported by verified document evidence.', 'כל תנאי הבדיקה הנדרשים נתמכים בראיות מאומתות מהמסמכים.'),
 'manual': ('Manual review required: ', 'נדרשת בדיקה ידנית: '),
}


def message(code, language, **values):
    return MESSAGES[code][0 if language == 'en' else 1].format(**values)


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


class RunLog:
    def __init__(self, directory):
        self.directory = Path(directory) if directory is not None else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            if any(self.directory.iterdir()):
                raise ValueError(f'Run directory must be empty: {self.directory}')
            for name in ('events.jsonl', 'model.jsonl'):
                (self.directory / name).touch()

    def append(self, filename, event):
        if self.directory:
            event = {'timestamp': datetime.now(timezone.utc).isoformat(), **event}
            with (self.directory / filename).open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False)+'\n')

    def event(self, event, **data):
        self.append('events.jsonl', {'event': event, **data})

    def model(self, data):
        self.append('model.jsonl', data)

    def save(self, filename, data):
        if self.directory: dump(self.directory / filename, data)


def evidence_sources(document, quote):
    """Locate normalized quotes, including quotes spanning consecutive text units."""
    needle = normalize(quote)
    if not needle:
        return []
    parts = [normalize(u['text']) for u in document.units]
    joined = ' '.join(parts)
    spans, offset = [], 0
    for part in parts:
        spans.append((offset, offset + len(part)))
        offset += len(part) + 1
    sources = []
    start = joined.find(needle)
    while start >= 0:
        end = start + len(needle)
        for unit, (left, right) in zip(document.units, spans):
            if left < end and right > start:
                source = {'document_id': document.id, 'quote': quote,
                          **{key: value for key, value in unit.items() if key != 'text'}}
                if source not in sources: sources.append(source)
        start = joined.find(needle, start + 1)
    return sources


def quote_position(document, quote):
    """Where a verified quote first occurs, so summaries can follow document order."""
    joined = ' '.join(normalize(u['text']) for u in document.units)
    position = joined.find(normalize(quote))
    return position if position >= 0 else len(joined)


def valid_type(value, kind):
    if kind == 'flag': return type(value) is bool
    if kind == 'number':
        import math
        return type(value) in (int, float) and math.isfinite(value)
    if kind == 'text': return isinstance(value, str) and bool(value.strip())
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)


def evaluate(value, condition):
    expected = condition.value
    if condition.op == 'eq':
        if type(expected) is bool: return type(value) is bool and value is expected
        return value == expected
    if condition.op == 'gte': return type(value) in (int, float) and value >= expected
    if condition.op == 'lte': return type(value) in (int, float) and value <= expected
    if condition.op == 'contains': return isinstance(value, (str, list)) and expected in value
    raise ValueError(f'Unsupported operator {condition.op}')


def candidates_for(facts, documents, field, roles):
    return [candidate for doc in documents if doc.role in roles
            for candidate in facts.get(doc.id, {}).get(field, [])]


def validate_and_decide(profile, documents, answers, issues, model, language):
    def add(code, *, severity='blocking', **values):
        issues.append({'code': code, 'severity': severity, 'detail': message(code, language, **values)})

    critical_fields = {i.field for i in profile.identity}
    critical_fields.update(c.field for rule in profile.rules for c in rule.conditions)
    critical_fields.update(c.field for c in profile.blockers)
    critical_fields.update(f for role in profile.roles.values() for f in role.required_fields)

    facts = {}
    for document in documents:
        role_label = profile.roles[document.role].label.get(language)
        facts[document.id] = {}
        for field, supplied in answers.get(document.id, {}).items():
            if field not in profile.roles[document.role].fields:
                continue
            spec = profile.fields[field]
            field_label = spec.label.get(language)
            severity = 'blocking' if field in critical_fields or spec.format == 'date' else 'warning'
            values = supplied if isinstance(supplied, list) else [supplied]
            for candidate in values:
                if candidate is None: continue
                if not isinstance(candidate, dict) or 'value' not in candidate or not isinstance(candidate.get('quote'), str):
                    add('invalid_value', severity=severity, role=role_label, field=field_label); continue
                value, quote = candidate['value'], candidate['quote']
                if not valid_type(value, spec.type):
                    add('invalid_value', severity=severity, role=role_label, field=field_label); continue
                if spec.quote_terms and not any(normalize(term) in normalize(quote) for term in spec.quote_terms):
                    add('unrelated_evidence', severity='warning', role=role_label, field=field_label); continue
                sources = evidence_sources(document, quote)
                number_ok = spec.type != 'number' or number_supports_field(
                    value, quote, spec.quote_terms, percent=spec.format == 'percent')
                if not sources or not number_ok:
                    add('invalid_evidence', severity=severity, role=role_label, field=field_label); continue
                if spec.format == 'date':
                    value = to_iso(value)
                    if value is None:
                        add('invalid_value', role=role_label, field=field_label); continue
                fact = {'value': value, 'quote': quote, 'sources': sources}
                existing = facts[document.id].setdefault(field, [])
                if fact not in existing: existing.append(fact)
        required = set(profile.roles[document.role].required_fields)
        required.update(i.field for i in profile.identity if i.required)
        for field in sorted(required):
            if not facts[document.id].get(field):
                add('missing_field', role=role_label, field=profile.fields[field].label.get(language))

    for role, spec in profile.roles.items():
        if spec.required and not any(doc.role == role for doc in documents):
            add('missing_document', role=spec.label.get(language))
    for identity in profile.identity:
        values = [f['value'] for fields in facts.values() for f in fields.get(identity.field, [])]
        if identity.normalize == 'name':
            mismatch = any(not same_name(values[0], value) for value in values[1:])
        else:
            normalized = [(to_iso(v) if identity.normalize == 'date' else normalize(str(v))) for v in values]
            mismatch = len(set(normalized)) > 1 or (bool(normalized) and None in normalized)
        if mismatch: add('identity_mismatch', field=profile.fields[identity.field].label.get(language))

    rules = []
    conflicts = set()
    for rule in profile.rules:
        details, all_evidence = [], []
        for condition in rule.conditions:
            candidates = candidates_for(facts, documents, condition.field, condition.roles)
            values = [c['value'] for c in candidates]
            if len({json.dumps(value, sort_keys=True) for value in values}) > 1 and condition.field not in conflicts:
                conflicts.add(condition.field)
                add('conflicting_values', field=profile.fields[condition.field].label.get(language))
            passed = bool(values) and all(evaluate(value, condition) for value in values)
            details.append({'field': condition.field, 'roles': condition.roles, 'op': condition.op,
                            'expected': condition.value, 'values': values, 'met': passed})
            all_evidence.extend(source for candidate in candidates for source in candidate['sources'])
        rules.append({'id': rule.id, 'label': rule.label.get(language),
                      'met': all(c['met'] for c in details), 'conditions': details, 'evidence': all_evidence})
    for blocker in profile.blockers:
        if any(evaluate(c['value'], blocker) for c in candidates_for(facts, documents, blocker.field, blocker.roles)):
            add('blocker', field=profile.fields[blocker.field].label.get(language))
    passed = all(rule['met'] for rule in rules) and not any(i['severity'] == 'blocking' for i in issues)
    if passed:
        reason = message('approved', language)
    else:
        problems = [message('rule_failed', language, label=r['label']) for r in rules if not r['met']]
        problems += [i['detail'] for i in issues if i['severity'] == 'blocking']
        reason = message('manual', language) + ' '.join(dict.fromkeys(problems))
    result = {'schema_version': 2, 'workflow': {'name': profile.name, 'version': profile.version},
              'language': language, 'recommendation': {'status': 'APPROVE' if passed else 'MANUAL_REVIEW', 'reason': reason},
              'rules': rules, 'issues': issues, 'facts': facts,
              'evidence': {doc_id: {field: [source for fact in values for source in fact['sources']]
                                    for field, values in fields.items()} for doc_id, fields in facts.items()},
              'documents': [d.manifest() for d in documents], 'model': model}
    for output, selector in profile.output_fields.items():
        candidates = [candidate for role in selector.roles for doc in documents if doc.role == role
                      for candidate in sorted(facts.get(doc.id, {}).get(selector.field, []),
                                              key=lambda c, d=doc: quote_position(d, c['quote']))]
        values = [c['value'] for c in candidates]
        unique = {json.dumps(value, sort_keys=True, ensure_ascii=False) for value in values}
        equivalent = len(unique) == 1
        identity = next((i for i in profile.identity if i.field == selector.field), None)
        if identity and values:
            if identity.normalize == 'name': equivalent = all(same_name(values[0], v) for v in values[1:])
            elif identity.normalize == 'date': equivalent = len({to_iso(v) for v in values}) == 1
            else: equivalent = len({normalize(str(v)) for v in values}) == 1
        value = None
        if values and (equivalent or selector.select == 'first'):
            value = values[0]
            if not equivalent:
                add('summary_selected', severity='warning', field=profile.fields[selector.field].label.get(language))
        if isinstance(value, float) and value.is_integer(): value = int(value)
        if value is not None and selector.display == 'name': value = display_name(value)
        target = result
        parts = output.split('.')
        for part in parts[:-1]: target = target.setdefault(part, {})
        target[parts[-1]] = value
    if passed and profile.approval_reason:
        specific = fill_reason(profile.approval_reason.get(language), result)
        if specific: result['recommendation']['reason'] = specific
    return result


def fill_reason(template, result):
    """Fill {output.path} placeholders from verified summary values; None if any value is missing."""
    def lookup(path):
        value = result
        for part in path.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, list): value = ', '.join(map(str, value)) if value else None
        return None if value in (None, '') else str(value)
    values = {path: lookup(path) for path in PLACEHOLDER.findall(template)}
    if any(value is None for value in values.values()): return None
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def model_metadata(model):
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2) as response:
            tags = json.load(response)
        name = model if ':' in model else f'{model}:latest'
        found = next((item for item in tags['models'] if item['name'] == name), {})
        return {'name': model, 'digest': found.get('digest'), 'details': found.get('details')}
    except Exception as exc:
        return {'name': model, 'metadata_error': str(exc)}


def run_case(case_file: Path, model: str, extract_fn=None, *, profile=None,
             language='he', output_dir=None, ocr=False, tessdata=None,
             ocr_language='eng+heb', chunk_size=6000):
    """Run a configured case; extract_fn preserves the legacy three-argument test seam."""
    if language not in ('he', 'en'): raise ValueError('language must be he or en')
    if not 32 <= chunk_size <= 8000: raise ValueError('chunk_size must be between 32 and 8000')
    if model.endswith(':cloud'): raise ValueError('Use a local Ollama model; cloud models are not supported')
    case_file = Path(case_file)
    config = json.loads(case_file.read_text(encoding='utf-8'))
    if not isinstance(config, dict): raise ValueError('Case must be a JSON object')
    workflow = load_profile(profile or config.get('profile', 'lung_biopsy'),
                            None if profile else case_file.parent)
    listed = config.get('documents')
    if not isinstance(listed, list) or not listed: raise ValueError('Case must list documents')
    ids, entries, counts = set(), [], {}
    for entry in listed:
        if not isinstance(entry, dict) or not isinstance(entry.get('role'), str):
            raise ValueError('Each document must have a role and path')
        role = entry['role']
        if role not in workflow.roles: raise ValueError(f'Unknown document role: {role}')
        counts[role] = counts.get(role, 0) + 1
        doc_id = entry.get('id', role if counts[role] == 1 else f'{role}-{counts[role]}')
        if not isinstance(doc_id, str) or not doc_id or doc_id in ids: raise ValueError(f'Duplicate or invalid document ID: {doc_id}')
        if not isinstance(entry.get('path'), str) or not entry['path']: raise ValueError('Document path must be a nonempty string')
        ids.add(doc_id)
        entries.append((doc_id, role, case_file.parent / entry['path']))
    log = RunLog(output_dir)
    started = time.monotonic()
    metadata = model_metadata(model) if extract_fn is None else {'name': model, 'extractor': 'injected'}
    snapshot = workflow.model_dump(mode='json')
    profile_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    log.save('profile.json', snapshot)
    log.save('case.json', config)
    log.event('started', workflow=workflow.name, language=language, model=metadata)
    documents, answers, issues, manifest_docs = [], {}, [], []
    for doc_id, role, path in entries:
        label = workflow.roles[role].label.get(language)
        stage_start = time.monotonic()
        document_record = {'id': doc_id, 'role': role, 'path': str(path), 'status': 'started'}
        manifest_docs.append(document_record)
        log.event('document_started', document_id=doc_id, role=role, path=str(path))
        try:
            document = read_document(path, doc_id, role, ocr=ocr, tessdata=tessdata, ocr_language=ocr_language)
            documents.append(document)
            document_record.update(document.manifest())
            log.event('document_read', document_id=doc_id, reader=document.reader, units=len(document.units))
            log.save('texts.json', {d.id: d.units for d in documents})
            if extract_fn:
                raw = extract_fn(role, document.text, model)
                answers[doc_id] = raw
                failures = []
                log.model({'event': 'injected_extraction', 'document_id': doc_id, 'answers': raw})
            else:
                answers[doc_id], failures = extract_document(document, workflow, model, chunk_size=chunk_size, log=log.model)
            for failure in failures:
                issues.append({'code': 'extraction_failed', 'severity': 'blocking',
                    'detail': message('extraction_failed', language, role=label, field=workflow.fields[failure['field']].label.get(language))})
            document_record.update(status='extraction_failed' if failures else 'processed', extraction_failures=len(failures))
            log.event('document_completed', document_id=doc_id, extraction_failures=len(failures),
                      elapsed_seconds=round(time.monotonic()-stage_start,3))
            print(f'  {label}: ' + ('completed' if language == 'en' else 'הושלם'))
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            if len(error) > 300: error = error[:300] + '...'
            detail = message('document_failed', language, name=path.name, role=label) + f' ({error})'
            issues.append({'code':'document_failed','severity':'blocking','detail':detail})
            document_record.update(status='failed', error=str(exc), error_type=type(exc).__name__)
            log.event('document_failed', document_id=doc_id, error=str(exc), error_type=type(exc).__name__)
            print(('  העיבוד נכשל: ' if language == 'he' else '  processing failed: ') + error)
    result = validate_and_decide(workflow, documents, answers, issues, model, language)
    manifest = {'case_file': str(case_file.resolve()), 'case_sha256': hashlib.sha256(case_file.read_bytes()).hexdigest(),
                'framework_version': __version__, 'extractor_system_prompt': GENERIC_PROMPT,
                'workflow': result['workflow'], 'profile_sha256': profile_hash, 'model': metadata,
                'language': language, 'ocr': ocr, 'ocr_language': ocr_language, 'chunk_size_bytes': chunk_size,
                'model_options': {'temperature': 0, 'seed': 42, 'num_ctx': 16384, 'num_predict': 1024},
                'documents': manifest_docs, 'elapsed_seconds': round(time.monotonic()-started,3)}
    log.save('manifest.json', manifest)
    log.save('facts.json', result['facts'])
    log.save('evidence.json', result['evidence'])
    log.save('texts.json', {d.id: d.units for d in documents})
    log.save('result.json', result)
    log.event('completed', status=result['recommendation']['status'], rules={r['id']:r['met'] for r in result['rules']},
              issues=len(result['issues']), elapsed_seconds=manifest['elapsed_seconds'])
    return result


def compare_runs(results):
    """Compare stable decisions and values; presentation and run timings are excluded."""
    if not results: raise ValueError('No runs to compare')
    def signature(result):
        return {'workflow': result['workflow'], 'status': result['recommendation']['status'],
                'rules': {r['id']: r['met'] for r in result['rules']},
                'facts': {doc_id: {field: sorted({json.dumps(fact['value'], sort_keys=True, ensure_ascii=False) for fact in facts})
                                   for field, facts in fields.items()} for doc_id, fields in result['facts'].items()},
                'issues': sorted((issue['code'], issue['severity']) for issue in result['issues'])}
    signatures = [signature(result) for result in results]
    same_decision = all(s['status'] == signatures[0]['status'] and s['rules'] == signatures[0]['rules'] for s in signatures)
    same_facts = all(s['facts'] == signatures[0]['facts'] for s in signatures)
    return {'runs': len(results), 'same_decision_and_rules': same_decision, 'same_verified_values': same_facts,
            'stable': all(s == signatures[0] for s in signatures), 'signatures': signatures}
