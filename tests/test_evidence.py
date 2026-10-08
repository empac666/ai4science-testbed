import copy
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from lab.evidence.checker import check_case, digest, evaluate, unclaimed_numbers

ROOT = Path(__file__).resolve().parents[1]
import sys
PYTHON = sys.executable
CODES = ['E_SCHEMA', 'E_PATH', 'E_RUN_MISSING', 'E_PROVENANCE', 'E_HASH', 'E_RUN_FAILED',
         'E_METRIC_MISSING', 'E_VALUE_MISMATCH', 'E_REPORT_MISMATCH', 'E_CLAIM_UNKNOWN',
         'E_UNCLAIMED_NUMBER', 'E_SAME_SOURCE', 'E_SCOPE']


def dump(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture(root):
    run = root / 'runs/r1'
    run.mkdir(parents=True)
    dump(run / 'metrics.json', {'score': 10, 'nested': {'value': 10}})
    (run / 'input.txt').write_text('input')
    (run / 'output.txt').write_text('output')
    record = {'run_id': 'r1', 'cmd': 'python experiment.py', 'git_sha': 'abcdef0', 'exit_code': 0,
              'started_at': '2026-10-02T00:00:00+00:00', 'duration_s': 1,
              'inputs': [{'path': 'input.txt', 'sha256': digest(run / 'input.txt')}],
              'outputs': [{'path': 'output.txt', 'sha256': digest(run / 'output.txt')}],
              'metrics_file': 'metrics.json', 'metrics_sha256': digest(run / 'metrics.json')}
    dump(run / 'record.json', record)
    claims = [{'id': 'score', 'kind': 'metric', 'text': '分数', 'value': 10, 'unit': '',
               'run_id': 'r1', 'metric_key': 'score'}]
    dump(root / 'claims.json', claims)
    (root / 'report.md').write_text('## 结果\n分数 10⟦c:score⟧\n', encoding='utf-8')
    dump(root / 'models.json', {'a': {'source': 'a', 'derived_from': [], 'assumptions': []},
                                'b': {'source': 'b', 'derived_from': [], 'assumptions': []}})
    dump(root / 'task.json', {'allowed_paths': ['lab/'], 'changed_files': ['lab/file.py']})
    return record, claims


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rec, self.claims = fixture(self.root)
        self.run = self.root / 'runs/r1'

    def codes(self):
        return {x['code'] for x in check_case(self.root)['errors']}

    def save_rec(self):
        dump(self.run / 'record.json', self.rec)

    def save_claims(self):
        dump(self.root / 'claims.json', self.claims)

    def report(self, text):
        (self.root / 'report.md').write_text(text, encoding='utf-8')

    def validation(self, models):
        self.claims[0].update(kind='validation', subject_model='a', reference_model='b')
        self.save_claims()
        dump(self.root / 'models.json', models)

    def test_all_codes_do_not_trigger_on_valid_case(self):
        for code in CODES:
            with self.subTest(code=code):
                self.assertNotIn(code, self.codes())
        self.assertEqual(check_case(self.root)['verdict'], 'pass')

    def test_E_SCHEMA(self):
        del self.claims[0]['text']
        self.save_claims()
        self.assertIn('E_SCHEMA', self.codes())

    def test_E_PATH(self):
        self.rec['metrics_file'] = '../metrics.json'
        self.save_rec()
        self.assertIn('E_PATH', self.codes())

    def test_E_RUN_MISSING(self):
        self.claims[0]['run_id'] = 'absent'
        self.save_claims()
        self.assertIn('E_RUN_MISSING', self.codes())

    def test_E_PROVENANCE(self):
        del self.rec['git_sha']
        self.save_rec()
        self.assertIn('E_PROVENANCE', self.codes())

    def test_E_HASH(self):
        self.rec['metrics_sha256'] = '0' * 64
        self.save_rec()
        self.assertIn('E_HASH', self.codes())

    def test_E_RUN_FAILED(self):
        self.rec['exit_code'] = 1
        self.save_rec()
        self.assertIn('E_RUN_FAILED', self.codes())

    def test_E_METRIC_MISSING(self):
        self.claims[0]['metric_key'] = 'not.present'
        self.save_claims()
        self.assertIn('E_METRIC_MISSING', self.codes())

    def test_E_VALUE_MISMATCH(self):
        self.claims[0]['value'] = 11
        self.save_claims()
        self.assertIn('E_VALUE_MISMATCH', self.codes())

    def test_E_REPORT_MISMATCH(self):
        self.report('## 结果\n11⟦c:score⟧')
        self.assertIn('E_REPORT_MISMATCH', self.codes())

    def test_E_CLAIM_UNKNOWN(self):
        self.report('## 结果\n10⟦c:unknown⟧')
        self.assertIn('E_CLAIM_UNKNOWN', self.codes())

    def test_E_UNCLAIMED_NUMBER(self):
        self.report('## 结果\n10')
        self.assertIn('E_UNCLAIMED_NUMBER', self.codes())

    def test_E_SAME_SOURCE(self):
        models = json.loads((self.root / 'models.json').read_text())
        models['b']['source'] = 'a'
        self.validation(models)
        self.assertIn('E_SAME_SOURCE', self.codes())

    def test_E_SCOPE(self):
        dump(self.root / 'task.json', {'allowed_paths': ['lab/'], 'changed_files': ['tests/a.py']})
        self.assertIn('E_SCOPE', self.codes())

    def test_scope_prefix_boundary(self):
        dump(self.root / 'task.json', {'allowed_paths': ['lab'], 'changed_files': ['laboratory/a']})
        self.assertIn('E_SCOPE', self.codes())

    def test_scope_relative_dot_normalization(self):
        dump(self.root / 'task.json', {'allowed_paths': ['./lab/./'], 'changed_files': ['lab/file.py']})
        self.assertNotIn('E_SCOPE', self.codes())

    def test_empty_id_is_still_a_string_id(self):
        self.claims[0]['id'] = ''
        self.save_claims()
        self.report('## 结果\n10⟦c:⟧')
        self.assertEqual(self.codes(), set())

    def test_nested_metric(self):
        self.claims[0]['metric_key'] = 'nested.value'
        self.save_claims()
        self.assertEqual(self.codes(), set())

    def test_numeric_marker_formats(self):
        for token, value, unit in [('-10', -10, ''), ('−10', -10, ''), ('.5', .5, ''), ('-1.2e-3', -0.0012, ''),
                                   ('1E+3', 1000, ''), ('10%', 10, '%'),
                                   ('1,234.5', 1234.5, ''), ('-1,234.5%', -1234.5, '%')]:
            with self.subTest(token=token):
                dump(self.run / 'metrics.json', {'score': value})
                self.rec['metrics_sha256'] = digest(self.run / 'metrics.json')
                self.save_rec()
                self.claims[0].update(value=value, unit=unit)
                self.save_claims()
                self.report('## 结果\n' + token + '⟦c:score⟧')
                self.assertEqual(self.codes(), set())

    def test_unmarked_numeric_formats(self):
        for token in ['-10', '−10', '-1.2e-3', '1E+3', '10%', '1,234.5']:
            with self.subTest(token=token):
                self.report('## 结果\n' + token)
                self.assertIn('E_UNCLAIMED_NUMBER', self.codes())

    def test_exemptions(self):
        self.report('数字 999\n## 结果\nW1 Sprint 2 IF-1.3 C99 k00\n2026-10-02\n`123 -5 1e3`\n``code 123``\n| ---: | :--- |\n10⟦c:score⟧\n## 讨论\n123')
        self.assertEqual(self.codes(), set())

    def test_separate_number_after_identifier(self):
        self.report('## 结果\nW1 值为 123')
        self.assertIn('E_UNCLAIMED_NUMBER', self.codes())

    def test_results_multiple_sections_and_subheading(self):
        self.report('## 结果\n### 子节\n2\n## 讨论\n3\n## 结果\n4')
        self.assertEqual(list(unclaimed_numbers((self.root / 'report.md').read_text())), [(3, '2'), (7, '4')])

    def test_markers_outside_results_still_checked(self):
        self.report('## 讨论\n11⟦c:score⟧')
        self.assertIn('E_REPORT_MISMATCH', self.codes())
        self.assertNotIn('E_UNCLAIMED_NUMBER', self.codes())

    def test_transitive_source_both_directions_and_cycle(self):
        for direction in ('a', 'b'):
            with self.subTest(direction=direction):
                models = {name: {'source': name, 'derived_from': [], 'assumptions': []} for name in ('a', 'b', 'mid')}
                other = 'b' if direction == 'a' else 'a'
                models[direction]['derived_from'] = ['mid']
                models['mid']['derived_from'] = [other, direction]
                self.validation(models)
                self.assertIn('E_SAME_SOURCE', self.codes())

    def test_core_assumptions(self):
        models = json.loads((self.root / 'models.json').read_text())
        for m in models.values():
            m['assumptions'] = ['core:ideal']
        self.validation(models)
        self.assertIn('E_SAME_SOURCE', self.codes())

    def test_shared_noncore_is_independent(self):
        models = json.loads((self.root / 'models.json').read_text())
        for m in models.values():
            m['assumptions'] = ['shared-noncore']
        self.validation(models)
        self.assertNotIn('E_SAME_SOURCE', self.codes())
        self.assertEqual(self.codes(), set())

    def test_external_missing_allowed_existing_still_hashed(self):
        self.rec['inputs'][0].update(path='external.txt', external=True)
        self.save_rec()
        self.assertEqual(self.codes(), set())
        (self.run / 'external.txt').write_text('wrong')
        self.assertIn('E_HASH', self.codes())

    def test_missing_internal_artifact(self):
        (self.run / 'input.txt').unlink()
        self.assertIn('E_SCHEMA', self.codes())

    def test_all_artifact_hashes(self):
        for name in ('input.txt', 'output.txt', 'metrics.json'):
            with self.subTest(name=name):
                old = (self.run / name).read_text()
                (self.run / name).write_text(old + ' ')
                self.assertIn('E_HASH', self.codes())
                (self.run / name).write_text(old)

    def test_external_cannot_escape(self):
        for val in ('../input.txt', '/absolute', 'a/../input.txt', 'C:/windows', '..\\evil'):
            with self.subTest(val=val):
                self.rec['inputs'][0].update(path=val, external=True)
                self.save_rec()
                self.assertIn('E_PATH', self.codes())

    def test_symlink_escape(self):
        (self.run / 'input.txt').unlink()
        (self.run / 'input.txt').symlink_to('/outside-case')
        self.assertIn('E_PATH', self.codes())

    def test_corrupt_json(self):
        for filename in ('claims.json', 'models.json', 'task.json', 'runs/r1/record.json', 'runs/r1/metrics.json'):
            with self.subTest(filename=filename):
                path = self.root / filename
                old = path.read_text()
                path.write_text('{broken')
                self.assertIn('E_SCHEMA', self.codes())
                path.write_text(old)

    def test_missing_report_claims_record_metrics(self):
        for filename in ('report.md', 'claims.json', 'runs/r1/record.json', 'runs/r1/metrics.json'):
            with self.subTest(filename=filename):
                path = self.root / filename
                old = path.read_text()
                path.unlink()
                self.assertIn('E_SCHEMA', self.codes())
                path.write_text(old)

    def test_record_missing_and_wrong_types(self):
        for field in self.rec:
            for value in (None, [], {}, True):
                with self.subTest(field=field, value=value):
                    rec = copy.deepcopy(self.rec)
                    rec[field] = value
                    dump(self.run / 'record.json', rec)
                    check_case(self.root)
            rec = copy.deepcopy(self.rec)
            del rec[field]
            dump(self.run / 'record.json', rec)
            self.assertIn('E_SCHEMA', self.codes())
        self.save_rec()

    def test_claim_wrong_types(self):
        for field in self.claims[0]:
            for value in (None, [], {}, True):
                with self.subTest(field=field, value=value):
                    claim = copy.deepcopy(self.claims)
                    claim[0][field] = value
                    dump(self.root / 'claims.json', claim)
                    self.assertIn('E_SCHEMA', self.codes())
        self.save_claims()

    def test_models_task_wrong_types_no_crash(self):
        for filename in ('models.json', 'task.json'):
            for value in ([], 3, 'text', {'a': []}, {'allowed_paths': [None], 'changed_files': [{}]}):
                with self.subTest(filename=filename, value=value):
                    dump(self.root / filename, value)
                    self.assertIn('E_SCHEMA', self.codes())

    def test_non_numeric_metrics(self):
        for value in ('10', True, None, [], float('nan'), float('inf')):
            with self.subTest(value=value):
                dump(self.run / 'metrics.json', {'score': value})
                self.rec['metrics_sha256'] = digest(self.run / 'metrics.json')
                self.save_rec()
                self.assertIn('E_METRIC_MISSING', self.codes())

    def test_tolerance(self):
        self.claims[0].update(value=10.01, tol_abs=0.02, tol_rel=0)
        self.save_claims()
        self.report('## 结果\n10.02⟦c:score⟧')
        self.assertEqual(self.codes(), set())
        self.claims[0]['value'] = 10.03
        self.save_claims()
        self.assertIn('E_VALUE_MISMATCH', self.codes())

    def test_duplicate_id_and_invalid_tolerance(self):
        self.claims.append(copy.deepcopy(self.claims[0]))
        self.save_claims()
        self.assertIn('E_SCHEMA', self.codes())
        self.claims.pop()
        self.claims[0]['tol_abs'] = -1
        self.save_claims()
        self.assertIn('E_SCHEMA', self.codes())

    def test_missing_models_for_validation(self):
        self.claims[0].update(kind='validation', subject_model='a', reference_model='b')
        self.save_claims()
        (self.root / 'models.json').unlink()
        self.assertIn('E_SCHEMA', self.codes())

    def test_warning_does_not_fail(self):
        self.report('## 结果\n无数字')
        result = check_case(self.root)
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(result['warnings'][0]['code'], 'W_UNREFERENCED_CLAIM')

    def test_common_ancestor_alone_is_not_same_source(self):
        models = {name: {'source': name, 'derived_from': [], 'assumptions': []} for name in ('a', 'b', 'parent')}
        models['a']['derived_from'] = ['parent']
        models['b']['derived_from'] = ['parent']
        self.validation(models)
        self.assertNotIn('E_SAME_SOURCE', self.codes())

    def test_null_top_level_documents_are_schema_errors(self):
        for filename in ('claims.json', 'models.json', 'task.json', 'runs/r1/record.json', 'runs/r1/metrics.json'):
            with self.subTest(filename=filename):
                path = self.root / filename
                old = path.read_text()
                path.write_text('null')
                self.assertIn('E_SCHEMA', self.codes())
                path.write_text(old)

    def test_numeric_bool_huge_int_and_nonfinite_claims(self):
        for value in (True, float('inf'), float('nan'), 10 ** 500):
            with self.subTest(value=str(value)[:30]):
                self.claims[0]['value'] = value
                self.save_claims()
                self.assertIn('E_SCHEMA', self.codes())

    def test_timestamp_and_sha_formats(self):
        for field, bad_values in [('started_at', ['2026-10-02T12:00:00', 'bad date', '2026-13-90T12:00:00+00:00']),
                                  ('git_sha', ['abc', 'ggggggg', 'a' * 41]), ('cmd', ['', '  '])]:
            for value in bad_values:
                with self.subTest(field=field, value=value):
                    rec = copy.deepcopy(self.rec)
                    rec[field] = value
                    dump(self.run / 'record.json', rec)
                    self.assertIn('E_PROVENANCE', self.codes())
        self.save_rec()
        self.rec['started_at'] = '2026-10-02T12:00:00Z'
        self.save_rec()
        self.assertNotIn('E_PROVENANCE', self.codes())

    def test_invalid_input_items_are_schema_and_provenance(self):
        for entry in (None, [], {}, {'path': 'input.txt'}, {'path': 'input.txt', 'sha256': 'bad'},
                      {'path': 'input.txt', 'sha256': '0' * 64, 'external': 'yes'}):
            with self.subTest(entry=entry):
                self.rec['inputs'] = [entry]
                self.save_rec()
                self.assertIn('E_SCHEMA', self.codes())
                self.assertIn('E_PROVENANCE', self.codes())

    def test_marker_requires_adjacent_number(self):
        self.report('## 结果\n10 ⟦c:score⟧')
        self.assertIn('E_SCHEMA', self.codes())
        self.assertIn('E_UNCLAIMED_NUMBER', self.codes())

    def test_table_header_separator_and_percent_scale(self):
        self.claims[0]['unit'] = '%'
        self.save_claims()
        self.report('## 结果\n| 数值 |\n| ---: |\n| 10%⟦c:score⟧ |')
        self.assertEqual(self.codes(), set())
        self.report('## 结果\n0.1%⟦c:score⟧')
        self.assertIn('E_REPORT_MISMATCH', self.codes())

    def test_cli_exit_codes(self):
        def cli(*args):
            return subprocess.run([PYTHON, '-m', 'lab.evidence', *args], cwd=ROOT, capture_output=True, text=True)
        result = cli('check', str(self.root), '--json')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['verdict'], 'pass')
        self.report('## 结果\n10')
        self.assertEqual(cli('check', str(self.root), '--json').returncode, 1)
        self.assertEqual(cli('batch', str(self.root / 'absent'), '--out', str(self.root / 'out.json')).returncode, 2)

    def test_batch_and_evaluate_cli(self):
        parent = self.root / 'cli_cases'
        fixture(parent / 'normal')
        fixture(parent / 'defect')
        (parent / 'defect' / 'report.md').write_text('## 结果\n123')
        labels = parent / 'labels.json'
        dump(labels, {'normal': {'label': 'normal', 'expected_codes': []},
                      'defect': {'label': 'defect', 'expected_codes': ['E_UNCLAIMED_NUMBER']}})
        output = self.root / 'batch.json'
        result = subprocess.run([PYTHON, '-m', 'lab.evidence', 'batch', str(parent), '--out', str(output)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(set(json.loads(output.read_text())), {'normal', 'defect'})
        result = subprocess.run([PYTHON, '-m', 'lab.evidence', 'evaluate', str(parent), '--labels', str(labels),
                                 '--out', str(output)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(output.read_text())['confusion_matrix'], {'tp': 1, 'fn': 0, 'fp': 0, 'tn': 1})

    def test_evaluate_semantic_excluded(self):
        parent = self.root / 'eval'
        for name in ('tp', 'fn', 'fp', 'tn', 'sem'):
            fixture(parent / name)
        for name in ('tp', 'fp', 'sem'):
            (parent / name / 'report.md').write_text('## 结果\n123')
        labels = {name: {'label': 'defect' if name in ('tp', 'fn') else 'semantic' if name == 'sem' else 'normal',
                         'expected_codes': ['E_UNCLAIMED_NUMBER'] if name in ('tp', 'fp', 'sem') else []}
                  for name in ('tp', 'fn', 'fp', 'tn', 'sem')}
        result = evaluate(parent, labels)
        self.assertEqual(result['confusion_matrix'], {'tp': 1, 'fn': 1, 'fp': 1, 'tn': 1})
        self.assertEqual(result['semantic'], {'total': 1, 'pass': 0, 'fail': 1})
        self.assertTrue(all(c['codes_match'] for c in result['cases']))


if __name__ == '__main__':
    unittest.main()
