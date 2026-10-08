"""EV-1.0 validation. All user-controlled JSON is treated as untrusted data."""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

NUMBER = r"[-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+−-]?\d+)?%?"
NUM_RE = re.compile(NUMBER)
MARK_RE = re.compile(r"⟦c:([^⟧\n]*)⟧")
NUM_MARK_RE = re.compile(r"(" + NUMBER + r")⟦c:([^⟧\n]*)⟧")


def numeric(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_path(base, value, root=None):
    if not isinstance(value, str) or not value:
        return None
    p = PurePosixPath(value)
    if p.is_absolute() or PureWindowsPath(value).is_absolute() or '..' in p.parts or '..' in PureWindowsPath(value).parts:
        return None
    target = Path(base) / value
    try:
        target.resolve().relative_to(Path(root or base).resolve())
    except (ValueError, OSError, RuntimeError):
        return None
    return target


def close(a, b, claim):
    return abs(a - b) <= max(claim.get('tol_abs', 0), claim.get('tol_rel', 1e-6) * abs(b))


def metric_at(metrics, key):
    cur = metrics
    for part in key.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def same_source(models, subject, reference):
    def ancestors(name):
        seen, todo = set(), list(models[name]['derived_from'])
        while todo:
            node = todo.pop()
            if node in seen:
                continue
            seen.add(node)
            if node in models:
                todo.extend(models[node]['derived_from'])
        return seen
    a, b = models[subject], models[reference]
    return (a['source'] == b['source'] or subject in ancestors(reference)
            or reference in ancestors(subject)
            or any(x.startswith('core:') for x in set(a['assumptions']) & set(b['assumptions'])))


def unclaimed_numbers(report):
    """Return (line, token) pairs in exact level-two 结果 sections."""
    active = False
    for line_no, line in enumerate(report.splitlines(), 1):
        heading = re.match(r'^ {0,3}##\s+(.+?)\s*#*\s*$', line)
        if heading:
            active = heading.group(1).strip() == '结果'
            continue
        if not active:
            continue
        # Mask exemptions without changing offsets.
        masked = line
        patterns = [r'(`+).*?\1', r'\b\d{4}-\d{2}-\d{2}\b',
                    r'\bSprint\s+\d+(?:\.\d+)?\b',
                    r'(?<!\w)(?=[\w.-]*[A-Za-z_])[A-Za-z_\d]+(?:[.-][A-Za-z_\d]+)*(?!\w)']
        for pattern in patterns:
            masked = re.sub(pattern, lambda m: m.group() if re.fullmatch(NUMBER, m.group()) else ' ' * len(m.group()), masked)
        masked = MARK_RE.sub(lambda m: ' ' * len(m.group()), masked)
        for match in NUM_RE.finditer(masked):
            if not MARK_RE.match(line, match.end()):
                yield line_no, match.group()


def check_case(case_dir):
    root = Path(case_dir)
    errors, warnings = [], []
    def error(code, where, detail):
        errors.append({'code': code, 'where': str(where), 'detail': detail})
    def path(base, value, where):
        if not isinstance(value, str):
            error('E_SCHEMA', where, 'path must be a string')
            return None
        result = safe_path(base, value, root)
        if result is None:
            error('E_PATH', where, 'absolute, parent, or escaping path')
        return result
    def read_json(file, required=True):
        if not file.exists() and not required:
            return None
        if safe_path(root, str(file.relative_to(root)), root) is None:
            error('E_PATH', file, 'file escapes case root')
            return None
        try:
            value = json.loads(file.read_text(encoding='utf-8'))
            if value is None:
                error('E_SCHEMA', file, 'JSON null is not a valid top-level document')
            return value
        except (OSError, ValueError, UnicodeError) as exc:
            error('E_SCHEMA', file, str(exc))
            return None
    claims = read_json(root / 'claims.json')
    if not isinstance(claims, list):
        if claims is not None:
            error('E_SCHEMA', 'claims.json', 'expected array')
        claims = []
    try:
        rp = path(root, 'report.md', 'report.md')
        report = rp.read_text(encoding='utf-8') if rp else ''
    except (OSError, UnicodeError) as exc:
        error('E_SCHEMA', 'report.md', str(exc))
        report = ''
    models = read_json(root / 'models.json', False)
    valid_models = {}
    if models is not None:
        if not isinstance(models, dict):
            error('E_SCHEMA', 'models.json', 'expected object')
        else:
            for name, model in models.items():
                if (isinstance(model, dict) and isinstance(model.get('source'), str)
                    and isinstance(model.get('derived_from'), list)
                    and all(isinstance(x, str) for x in model['derived_from'])
                    and isinstance(model.get('assumptions'), list)
                    and all(isinstance(x, str) for x in model['assumptions'])):
                    valid_models[name] = model
                else:
                    error('E_SCHEMA', 'models.json:' + name, 'invalid model registration')
            for name, model in valid_models.items():
                if any(x not in valid_models for x in model['derived_from']):
                    error('E_SCHEMA', 'models.json:' + name, 'unknown derived_from model')
    task = read_json(root / 'task.json', False)
    if task is not None:
        if (not isinstance(task, dict) or not isinstance(task.get('allowed_paths'), list)
            or not isinstance(task.get('changed_files'), list)):
            error('E_SCHEMA', 'task.json', 'expected allowed_paths and changed_files arrays')
        else:
            allowed = []
            for val in task['allowed_paths']:
                if path(root, val, 'task.json:allowed_paths'):
                    allowed.append(str(PurePosixPath(val)))
            for val in task['changed_files']:
                if not path(root, val, 'task.json:changed_files'):
                    continue
                normalized = str(PurePosixPath(val))
                if not any(a == '.' or normalized == a or normalized.startswith(a + '/') for a in allowed):
                    error('E_SCOPE', val, 'changed file outside allowed paths')
    records = {}
    runs_dir = root / 'runs'
    if runs_dir.is_dir() and safe_path(root, 'runs', root):
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            rec = read_json(run_dir / 'record.json')
            if not isinstance(rec, dict):
                if rec is not None:
                    error('E_SCHEMA', run_dir / 'record.json', 'expected object')
                continue
            where = 'runs/' + run_dir.name + '/record.json'
            validators = {
                'run_id': lambda x: isinstance(x, str) and x == run_dir.name,
                'cmd': lambda x: isinstance(x, str) and bool(x.strip()),
                'git_sha': lambda x: isinstance(x, str) and bool(re.fullmatch(r'[0-9a-fA-F]{7,40}', x)),
                'exit_code': lambda x: isinstance(x, int) and not isinstance(x, bool),
                'started_at': valid_timestamp,
                'duration_s': lambda x: numeric(x) and x >= 0,
                'inputs': lambda x: isinstance(x, list),
                'outputs': lambda x: isinstance(x, list),
                'metrics_file': lambda x: isinstance(x, str) and bool(x),
                'metrics_sha256': valid_hash,
            }
            for field, validator in validators.items():
                if field not in rec or not validator(rec[field]):
                    error('E_SCHEMA', where + ':' + field, 'missing or invalid field')
                    if field in ('cmd', 'git_sha', 'started_at', 'inputs'):
                        error('E_PROVENANCE', where + ':' + field, 'missing or invalid provenance')
            for field in ('inputs', 'outputs'):
                entries = rec.get(field)
                if not isinstance(entries, list):
                    continue
                for i, entry in enumerate(entries):
                    loc = where + ':' + field + ':' + str(i)
                    if (not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
                        or not valid_hash(entry.get('sha256'))
                        or ('external' in entry and not isinstance(entry['external'], bool))):
                        error('E_SCHEMA', loc, 'invalid artifact entry')
                        if field == 'inputs':
                            error('E_PROVENANCE', loc, 'invalid input provenance')
                        if isinstance(entry, dict) and isinstance(entry.get('path'), str):
                            path(run_dir, entry['path'], loc)
                        continue
                    target = path(run_dir, entry['path'], loc)
                    if target:
                        if not target.is_file():
                            if not entry.get('external', False):
                                error('E_SCHEMA', loc, 'artifact file missing')
                        else:
                            verify_hash(target, entry['sha256'], loc, error)
            metrics = None
            if isinstance(rec.get('metrics_file'), str):
                mp = path(run_dir, rec['metrics_file'], where + ':metrics_file')
                if mp:
                    metrics = read_json(mp)
                    if mp.is_file() and valid_hash(rec.get('metrics_sha256')):
                        verify_hash(mp, rec['metrics_sha256'], where + ':metrics_sha256', error)
                    if metrics is not None and not valid_metrics(metrics):
                        error('E_SCHEMA', mp, 'metrics must be an object with numeric leaves')
            records[run_dir.name] = (rec, metrics)
    elif runs_dir.exists():
        error('E_PATH' if not safe_path(root, 'runs', root) else 'E_SCHEMA', 'runs', 'invalid runs directory')
    by_id = {}
    for i, claim in enumerate(claims):
        where = 'claims.json:' + str(i)
        if not isinstance(claim, dict):
            error('E_SCHEMA', where, 'claim must be object')
            continue
        valid = True
        for field in ('id', 'kind', 'text', 'unit', 'run_id', 'metric_key'):
            if not isinstance(claim.get(field), str):
                error('E_SCHEMA', where + ':' + field, 'missing or invalid string')
                valid = False
        if claim.get('kind') not in ('metric', 'validation'):
            error('E_SCHEMA', where + ':kind', 'unknown claim kind')
            valid = False
        for field in ('value', 'tol_abs', 'tol_rel'):
            if field == 'value' or field in claim:
                if not numeric(claim.get(field)) or (field != 'value' and claim[field] < 0):
                    error('E_SCHEMA', where + ':' + field, 'invalid numeric field')
                    valid = False
        cid = claim.get('id')
        if isinstance(cid, str):
            if cid in by_id:
                error('E_SCHEMA', where + ':id', 'duplicate claim ID')
            elif valid:
                by_id[cid] = claim
        if not valid:
            continue
        run_id = claim['run_id']
        if safe_path(root / 'runs', run_id, root / 'runs') is None or '/' in run_id:
            error('E_PATH', where + ':run_id', 'invalid run ID path')
        if run_id not in records:
            error('E_RUN_MISSING', where, 'run does not exist: ' + run_id)
        else:
            rec, metrics = records[run_id]
            if isinstance(rec.get('exit_code'), int) and rec['exit_code'] != 0:
                error('E_RUN_FAILED', where, 'referenced run failed')
            metric = metric_at(metrics, claim['metric_key'])
            if not numeric(metric):
                error('E_METRIC_MISSING', where, 'metric absent or nonnumeric: ' + claim['metric_key'])
            elif not close(claim['value'], metric, claim):
                error('E_VALUE_MISMATCH', where, 'claim differs from run metric')
        if claim['kind'] == 'validation':
            s, r = claim.get('subject_model'), claim.get('reference_model')
            if not isinstance(s, str) or not isinstance(r, str) or s not in valid_models or r not in valid_models:
                error('E_SCHEMA', where, 'validation needs registered subject and reference models')
            elif same_source(valid_models, s, r):
                error('E_SAME_SOURCE', where, 'subject and reference share provenance or core assumptions')
    referenced = set()
    marked = {m.start(2): m for m in NUM_MARK_RE.finditer(report)}
    for match in MARK_RE.finditer(report):
        cid = match.group(1)
        referenced.add(cid)
        loc = 'report.md:' + str(report[:match.start()].count('\n') + 1)
        if cid not in by_id:
            error('E_CLAIM_UNKNOWN', loc, 'unknown claim: ' + cid)
            continue
        nm = marked.get(match.start(1))
        if nm is None:
            error('E_SCHEMA', loc, 'claim marker must immediately follow a number')
            continue
        value = float(nm.group(1).rstrip('%').replace(',', '').replace('−', '-'))
        if not numeric(value) or not close(value, by_id[cid]['value'], by_id[cid]):
            error('E_REPORT_MISMATCH', loc, 'report differs from claim value')
    for line_no, token in unclaimed_numbers(report):
        error('E_UNCLAIMED_NUMBER', 'report.md:' + str(line_no), 'unmarked number: ' + token)
    for cid in sorted(set(by_id) - referenced):
        warnings.append({'code': 'W_UNREFERENCED_CLAIM', 'where': 'claims.json:' + cid, 'detail': 'claim not referenced in report'})
    return {'verdict': 'fail' if errors else 'pass', 'errors': errors, 'warnings': warnings}


def valid_hash(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-fA-F]{64}', value))


def valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.tzinfo is not None and dt.utcoffset() is not None
    except ValueError:
        return False


def valid_metrics(value):
    return isinstance(value, dict) and all(valid_metrics(v) if isinstance(v, dict) else numeric(v) for v in value.values())


def verify_hash(target, expected, where, error):
    try:
        if digest(target).lower() != expected.lower():
            error('E_HASH', where, 'sha256 mismatch')
    except OSError as exc:
        error('E_SCHEMA', where, str(exc))


def batch(directory):
    return {p.name: check_case(p) for p in sorted(Path(directory).iterdir()) if p.is_dir()}


def evaluate(directory, labels):
    results = batch(directory)
    matrix = {'tp': 0, 'fn': 0, 'fp': 0, 'tn': 0}
    semantic = {'total': 0, 'pass': 0, 'fail': 0}
    cases = []
    if not isinstance(labels, dict):
        raise ValueError('labels.json must map case names to label objects or labels')
    for name, entry in labels.items():
        if isinstance(entry, str):
            entry = {'label': entry}
        if not isinstance(entry, dict) or entry.get('label') not in ('defect', 'normal', 'semantic'):
            raise ValueError('invalid label for ' + name)
        label = entry['label']
        if name not in results:
            raise ValueError('label references missing case: ' + name)
        result = results[name]
        failed = result['verdict'] == 'fail'
        if label == 'semantic':
            semantic['total'] += 1
            semantic[result['verdict']] += 1
        else:
            matrix[('tp' if failed else 'fn') if label == 'defect' else ('fp' if failed else 'tn')] += 1
        actual = sorted({e['code'] for e in result['errors']})
        expected = sorted(entry.get('expected_codes', []))
        cases.append({'case': name, 'label': label, 'verdict': result['verdict'],
                      'expected_codes': expected, 'actual_codes': actual, 'codes_match': actual == expected})
    unlabeled = sorted(set(results) - set(labels))
    tp, fn, fp, tn = (matrix[k] for k in ('tp', 'fn', 'fp', 'tn'))
    return {'confusion_matrix': matrix, 'semantic': semantic,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'cases': cases, 'unlabeled_cases': unlabeled}
