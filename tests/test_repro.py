import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from lab.evidence import check_case
from lab.repro.runner import ROOT, PYTHON, parse_metrics, run, export_case


class ReproTests(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(parse_metrics('fw', 'C tests: 40 passed; assertions: 404589\nCLI tests: 12 passed', 'x warning: demo'),
                         {'c_tests_passed': 40, 'assertions': 404589, 'cli_tests_passed': 12, 'warning_lines': 1})
        self.assertEqual(parse_metrics('pytest', '2 failed, 70 passed in 1.2s', ''), {'passed': 70, 'failed': 2, 'errors': 0})
        self.assertEqual(parse_metrics('pytest', '77 passed in 1.2s', ''), {'passed': 77, 'failed': 0, 'errors': 0})
        self.assertEqual(parse_metrics('pytest', '3 errors in 1.2s', ''), {'passed': 0, 'failed': 0, 'errors': 3})
        with self.assertRaises(ValueError):
            parse_metrics('fw', 'no summaries', '')

    def test_run_and_export_with_input_metrics(self):
        with TemporaryDirectory(dir=ROOT) as tmp:
            base = Path(tmp)
            input_file, metrics = base / 'input.txt', base / 'supplied.json'
            input_file.write_text('real input')
            metrics.write_text('{"supplied": 7}')
            rec = run('unittest', [PYTHON, '-c', 'import json; print(json.dumps({"value": 2}))'],
                      inputs=[input_file], metrics_from=metrics, parser='json')
            self.addCleanup(shutil.rmtree, ROOT / 'runs' / rec['run_id'])
            self.assertEqual(rec['exit_code'], 0)
            self.assertIn('dirty', rec)
            self.assertGreaterEqual(rec['peak_rss_mb'], 0)
            claims = [{'id': 'v', 'kind': 'metric', 'text': '实测', 'value': 2, 'unit': '',
                       'run_id': rec['run_id'], 'metric_key': 'value'}]
            (base / 'claims.json').write_text(json.dumps(claims))
            (base / 'report.md').write_text('## 结果\n2⟦c:v⟧')
            dest = export_case(base / 'case', [rec['run_id']], base / 'claims.json', base / 'report.md')
            self.assertEqual(check_case(dest)['verdict'], 'pass')
            measured = json.loads((dest / 'runs' / rec['run_id'] / 'metrics.json').read_text())
            self.assertEqual(measured['supplied'], 7)
            self.assertEqual(measured['repro']['exit_code'], 0)

    def test_missing_command_is_recorded(self):
        rec = run('missing-command-test', ['this-command-does-not-exist-ev10'])
        self.addCleanup(shutil.rmtree, ROOT / 'runs' / rec['run_id'])
        self.assertEqual(rec['exit_code'], 127)
        self.assertTrue((ROOT / 'runs' / rec['run_id'] / 'stderr.txt').is_file())

    def test_parser_failure_preserves_real_exit(self):
        rec = run('bad-parser-test', [PYTHON, '-c', 'print("not json")'], parser='json')
        self.addCleanup(shutil.rmtree, ROOT / 'runs' / rec['run_id'])
        self.assertEqual(rec['exit_code'], 0)
        self.assertIn('parse_error', rec)

    def test_cli_run_export_and_failure(self):
        with TemporaryDirectory(dir=ROOT) as tmp:
            base = Path(tmp)
            (base / 'input.txt').write_text('input')
            cmd = [PYTHON, '-m', 'lab.repro', 'run', '--name', 'cli-test', '--inputs', str(base / 'input.txt'),
                   '--parse', 'json', '--', PYTHON, '-c', 'import sys, json; print(json.dumps({"metric": 3})); print("stderr", file=sys.stderr)']
            process = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            rec = json.loads(process.stdout)
            self.addCleanup(shutil.rmtree, ROOT / 'runs' / rec['run_id'])
            self.assertEqual((ROOT / 'runs' / rec['run_id'] / 'stderr.txt').read_text(), 'stderr\n')
            (base / 'claims.json').write_text(json.dumps([{'id': 'v', 'kind': 'metric', 'text': '值', 'value': 3,
                   'unit': '', 'run_id': rec['run_id'], 'metric_key': 'metric'}]))
            (base / 'report.md').write_text('## 结果\n3⟦c:v⟧')
            result = subprocess.run([PYTHON, '-m', 'lab.repro', 'export-case', str(base / 'case'), '--runs', rec['run_id'],
                     '--claims', str(base / 'claims.json'), '--report', str(base / 'report.md')],
                     cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(check_case(base / 'case')['verdict'], 'pass')

    def test_export_keeps_declared_tmp_artifact(self):
        with TemporaryDirectory(dir=ROOT) as tmp:
            base = Path(tmp)
            rec = run('tmp-artifact-test', [PYTHON, '-c', 'print("ok")'])
            run_dir = ROOT / 'runs' / rec['run_id']
            self.addCleanup(shutil.rmtree, run_dir)
            from lab.evidence.checker import digest
            artifact = run_dir / 'tmp' / 'declared.txt'
            artifact.write_text('declared output')
            rec['outputs'].append({'path': 'tmp/declared.txt', 'sha256': digest(artifact)})
            (run_dir / 'record.json').write_text(json.dumps(rec))
            (base / 'claims.json').write_text('[]')
            (base / 'report.md').write_text('## 结果\n无数字')
            case = export_case(base / 'case', [rec['run_id']], base / 'claims.json', base / 'report.md')
            self.assertTrue((case / 'runs' / rec['run_id'] / 'tmp/declared.txt').is_file())
            self.assertEqual(check_case(case)['verdict'], 'pass')
