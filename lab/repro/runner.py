import json
import os
import re
import resource
import shlex
import shutil
import sys
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from lab.evidence.checker import digest, safe_path, valid_metrics

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def parse_metrics(parser, stdout, stderr):
    text = stdout + '\n' + stderr
    if parser == 'fw':
        c = re.search(r'C tests:\s*(\d+) passed; assertions:\s*(\d+)', text)
        cli = re.search(r'CLI tests:\s*(\d+) passed', text)
        if not c or not cli:
            raise ValueError('firmware test summaries not found')
        return {'c_tests_passed': int(c[1]), 'assertions': int(c[2]),
                'cli_tests_passed': int(cli[1]),
                'warning_lines': sum(bool(re.search(r'\bwarning\b', line, re.I)) for line in text.splitlines())}
    if parser == 'pytest':
        # Use the final summary only; collection errors are preserved as an additional metric.
        summaries = [line for line in text.splitlines() if re.search(r'\d+ (?:passed|failed|error)', line)]
        summary = summaries[-1] if summaries else ''
        if not summary:
            raise ValueError('pytest summary not found')
        def count(word):
            match = re.search(r'(\d+) ' + word + r'\b', summary)
            return int(match[1]) if match else 0
        return {'passed': count('passed'), 'failed': count('failed'), 'errors': count('errors?')}
    if parser == 'json':
        metrics = json.loads(stdout)
        if not valid_metrics(metrics):
            raise ValueError('stdout JSON must contain numeric metrics')
        return metrics
    raise ValueError('unknown parser: ' + parser)


def _limits():
    # Linux address space cap is inherited by descendants. DC-link jobs are serial and BLAS is single-threaded.
    resource.setrlimit(resource.RLIMIT_AS, (2500 * 1024 * 1024, 2500 * 1024 * 1024))


def _rss_tree(pid):
    """Sample aggregate RSS for a process and descendants via Linux procfs."""
    total, pending, seen = 0, [pid], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            status = Path('/proc/' + str(current) + '/status').read_text()
            match = re.search(r'^VmRSS:\s+(\d+)', status, re.M)
            if match:
                total += int(match[1]) * 1024
            for task in Path('/proc/' + str(current) + '/task').iterdir():
                children = (task / 'children').read_text().split()
                pending.extend(int(child) for child in children)
        except (OSError, ValueError):
            pass
    return total


def run(name, cmd, inputs=(), metrics_from=None, parser=None, cwd=None, env=None, git_sha=None):
    if not cmd:
        raise ValueError('command is empty')
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', name)[:60] or 'run'
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + safe_name + '-' + uuid.uuid4().hex[:8]
    run_dir = ROOT / 'runs' / run_id
    run_dir.mkdir(parents=True)
    working = Path(cwd or ROOT).resolve()
    working.relative_to(ROOT)
    revision = subprocess.run(['git', '-C', str(working), 'rev-parse', '--verify', 'HEAD'],
                              capture_output=True, text=True)
    # An all-zero revision explicitly denotes a new, uncommitted repository.
    sha = git_sha or (revision.stdout.strip() if revision.returncode == 0 else '0' * 40)
    dirty = bool(subprocess.check_output(['git', '-C', str(working), 'status', '--porcelain'], text=True).strip())
    entries = []
    for index, filename in enumerate(inputs):
        source = Path(filename).resolve()
        source.relative_to(ROOT)
        destination = run_dir / 'inputs' / (str(index) + '-' + source.name)
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(source, destination)
        entries.append({'path': str(destination.relative_to(run_dir)), 'sha256': digest(destination)})
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    run_env = os.environ.copy()
    run_env.update({'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                    'NUMEXPR_NUM_THREADS': '1', 'MAKEFLAGS': '-j1', 'PYTHONDONTWRITEBYTECODE': '1'})
    temp_dir = run_dir / 'tmp'
    temp_dir.mkdir()
    run_env.update({'TMPDIR': str(temp_dir), 'MPLCONFIGDIR': str(temp_dir / 'matplotlib'),
                    'XDG_CACHE_HOME': str(temp_dir / 'cache')})
    run_env.update(env or {})
    peak = [0]
    stop = threading.Event()
    with (run_dir / 'stdout.txt').open('wb') as out, (run_dir / 'stderr.txt').open('wb') as err:
        try:
            process = subprocess.Popen(cmd, cwd=working, env=run_env, stdout=out, stderr=err,
                                       preexec_fn=_limits)
        except OSError as exc:
            err.write((str(exc) + '\n').encode())
            exit_code = 127
        else:
            def monitor():
                while not stop.is_set():
                    peak[0] = max(peak[0], _rss_tree(process.pid))
                    stop.wait(0.02)
            thread = threading.Thread(target=monitor, daemon=True)
            thread.start()
            _, status, usage = os.wait4(process.pid, 0)
            exit_code = os.waitstatus_to_exitcode(status)
            process.returncode = exit_code
            peak[0] = max(peak[0], int(usage.ru_maxrss * 1024))
            stop.set()
            thread.join()
    duration = time.monotonic() - start
    metrics, parse_error, extra_outputs = {}, None, []
    try:
        if parser:
            metrics.update(parse_metrics(parser, (run_dir / 'stdout.txt').read_text(errors='replace'),
                                         (run_dir / 'stderr.txt').read_text(errors='replace')))
        if metrics_from:
            source = Path(metrics_from).resolve()
            source.relative_to(ROOT)
            supplied = json.loads(source.read_text())
            metric_copy = run_dir / 'metrics-source.json'
            shutil.copy2(source, metric_copy)
            extra_outputs.append({'path': metric_copy.name, 'sha256': digest(metric_copy)})
            if not valid_metrics(supplied):
                raise ValueError('metrics-from must contain numeric metrics')
            metrics.update(supplied)
    except (ValueError, OSError) as exc:
        parse_error = str(exc)
    if 'repro' in metrics:
        parse_error = 'metric namespace repro is reserved by the recorder'
        metrics.pop('repro')
    metrics['repro'] = {'exit_code': exit_code, 'duration_s': duration, 'peak_rss_mb': peak[0] / (1024 * 1024)}
    write_json(run_dir / 'metrics.json', metrics)
    record = {'run_id': run_id, 'cmd': shlex.join(cmd), 'git_sha': sha,
              'exit_code': exit_code, 'started_at': started_at, 'duration_s': duration,
              'inputs': entries, 'outputs': [{'path': file, 'sha256': digest(run_dir / file)}
                                           for file in ('stdout.txt', 'stderr.txt')] + extra_outputs,
              'metrics_file': 'metrics.json', 'metrics_sha256': digest(run_dir / 'metrics.json'),
              'dirty': dirty, 'peak_rss_mb': peak[0] / (1024 * 1024), 'hostname': 'local_machine',
              'cwd': str(working.relative_to(ROOT)), 'rss_measurement': 'max of process-tree RSS sampled every 20 ms and kernel ru_maxrss (KiB on Linux)'}
    if parse_error:
        record['parse_error'] = parse_error
    write_json(run_dir / 'record.json', record)
    return record


def export_case(case_dir, run_ids, claims, report):
    destination = Path(case_dir).resolve()
    destination.relative_to(ROOT)
    destination.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        source = safe_path(ROOT / 'runs', run_id)
        if source is None or '/' in run_id or not source.is_dir():
            raise ValueError('invalid or missing run ID: ' + run_id)
        target = destination / 'runs' / run_id
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            raise ValueError('case already contains run: ' + run_id)
        rec = json.loads((source / 'record.json').read_text())
        references = [rec.get('metrics_file', '')] + [
            item.get('path', '') for group in ('inputs', 'outputs')
            for item in rec.get(group, []) if isinstance(item, dict)]
        keep_tmp = any(value == 'tmp' or value.startswith('tmp/') for value in references if isinstance(value, str))
        def ignore(directory, names):
            return ['tmp'] if Path(directory) == source and 'tmp' in names and not keep_tmp else []
        shutil.copytree(source, target, ignore=ignore)
    for source, name in ((claims, 'claims.json'), (report, 'report.md')):
        p = Path(source).resolve()
        p.relative_to(ROOT)
        if p != destination / name:
            shutil.copy2(p, destination / name)
    return destination
