"""Synthetic and input-only tests. Never open real calibration/evaluation labels."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import contextlib
import copy
import importlib.util
import io
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import magnet8_common as common
import magnet8_design as design
import magnet8_arm as arm
import magnet8_audit as audit
import magnet8_calibrate as calibrate
import magnet8_evaluate as evaluate
import magnet8_sweep as sweep
import magnet6_model as legacy


def synthetic_results():
    sample = dict(n=120, fset={'50': 120}, T={'25': 120}, dBdt_bin={'0': 120}, fset_T={'50|25': 120},
                  boundary_282=0, boundary_70=0, boundary_either=0, boundary_both=0)
    results = {}
    for exp, sets in [('E1', {'X7': 632, 'G7r': 301}), ('E2', {'XF': 5361, 'XT': 8345, 'XFT': 1788, 'G8': 301})]:
        results[exp] = {}
        for a in common.ARMS:
            metrics = {name: dict(n=n, coverage=n, coverage_fraction=1., nominal90_shortfall=0., width=1.,
                       winkler={'A': 1., 'M': .9, 'R': 2.}[a[0]], relative_error=.1, mae=.1, bias=0.) for name, n in sets.items()}
            results[exp][a] = dict(metrics=metrics, checkpoints=[dict(batch=b, added=20*b, q=1., metrics=metrics) for b in range(7)],
                                  sampling_counts=dict(S0=copy.deepcopy(sample), additions=copy.deepcopy(sample)))
    return results


class Magnet8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = None
        # Tiny synthetic IDs preserve permission-guard coverage without real features.
        cls.splits = {exp: dict(pool=[10, 11, 12], S=[10, 11, 12], S0_1=[10],
                     **{key: [i] for i, key in enumerate((*common.EVAL[exp], common.CAL[exp]))})
                     for exp in common.CAL}
        if common.FEATURE_PATH.exists() and (common.OUT/'split.json').exists():
            cls.df, cls.splits = design.load_design(allow_missing_sources=True)

    def test_signflip_brute_and_legacy(self):
        rng = np.random.default_rng(81)
        for k in range(1, 15):
            for d in [rng.normal(size=k), rng.integers(-3, 4, k), np.zeros(k)]:
                expected = sum(np.mean(np.asarray(s)*d) >= np.mean(d)-1e-12 for s in itertools.product((-1, 1), repeat=k))/2**k
                self.assertEqual(evaluate.signflip_p(d), expected)
                self.assertEqual(evaluate.signflip_p(d), legacy.signflip_p(d))

    def test_signflip_k30(self):
        self.assertEqual(evaluate.signflip(np.ones(30)), dict(numerator=1, denominator=2**30, p=2**-30))
        self.assertEqual(evaluate.signflip_p(np.zeros(30)), 1.)

    def test_signflip_ties_tolerance(self):
        for d in ([1., 1., 0., -1.], [1., -1.]*7, [0., 1e-12, -1e-12], [1e-12]*14,
                  [1.01e-12]*8, [.99e-12]*8, [0., 4e-13, -2e-13], [1., -1., 2e-12]):
            self.assertEqual(evaluate.signflip_p(d), legacy.signflip_p(d))

    def test_signflip_invalid(self):
        for d in ([], [np.nan], [np.inf], np.ones(31), [[1, 2]]):
            with self.assertRaises(AssertionError):
                evaluate.signflip_p(d)

    def test_seeds(self):
        seeds = [common.seed(e, 0, 0) for e in (1, 2)] + [common.seed(e, r, k) for e in (1, 2) for r in (1, 2) for k in range(1, 31)]
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertTrue(min(seeds) > 2**64)
        self.assertEqual(common.H, 511081239)
        self.assertEqual(common.PREREG_SHA, '1e767b17c6195e01bceb5bf20dcd4189df3b9571')
        gp = [common.gp_seed(e) for e in (1, 2)]
        self.assertNotEqual(*gp)
        self.assertTrue(all(2**31 <= v <= 2**31+2**30-1 for v in gp))
        old = {20261004, 1869701181, *range(1869701182, 1869701202), *range(1869701282, 1869701302)}
        self.assertFalse(set(seeds+gp) & old)
        for args in [(0, 0, 0), (1, 0, 1), (1, 3, 1), (2, 1, 31)]:
            with self.assertRaises(AssertionError):
                common.seed(*args)

    def test_design_deterministic_and_counts(self):
        if self.df is None: self.skipTest('MagNet input features/split not distributed')
        frame = self.df.reset_index(drop=True)
        self.assertEqual(design.generate_split(frame.sample(frac=1, random_state=9)), self.splits)
        design.validate_split(frame, self.splits)
        for e, exp in enumerate(common.CAL, 1):
            s = self.splits[exp]
            self.assertFalse(set(s['pool']) & common.holdouts(exp, s))
            for k in range(1, 31):
                self.assertEqual(s[f'S0_{k}'], np.random.default_rng(common.seed(e, 1, k)).choice(s['pool'], 100, replace=False).tolist())
                self.assertEqual(s[f'R_{k}'], np.random.default_rng(common.seed(e, 2, k)).choice(sorted(set(s['pool'])-set(s[f'S0_{k}'])), 120, replace=False).tolist())

    def test_family_unique_frequency_and_rounding(self):
        f = pd.DataFrame(dict(frequency_Hz=[50000, 50100, 100000, 50000], amplitude_T=[.05]*4,
                              waveform=['tri']*4, duty=[.25]*4, plateau=[.125]*4))
        d = design.family_features(f)
        self.assertEqual(d.fset.tolist(), [50, 50, 100, 50])
        self.assertEqual(d.family.tolist(), ['50_tri_2_2', '50_tri_2_2', '100_tri_2_2', '50_tri_2_2'])

    def test_equal_bins(self):
        bins, edges = design.equal_bins([-1, 0, .999999, 1, 7, 8, 9], [0, 8])
        self.assertEqual(bins.tolist(), [0, 0, 0, 1, 7, 7, 7])
        self.assertEqual(edges, list(range(9)))
        with self.assertRaises(AssertionError):
            design.equal_bins([1], [1, 1])
        if self.df is None: return  # Synthetic bin boundaries above still run.
        for exp in common.CAL:
            _, expected = design.equal_bins(self.df.dBdt, self.df.loc[self.splits[exp]['pool'], 'dBdt'])
            self.assertEqual(common.read_json(common.STAGE/'split_summary.json')['experiments'][exp]['dBdt_edges'], expected)

    def test_smoke_isolation(self):
        if self.df is None: self.skipTest('MagNet input features/split not distributed')
        for exp in common.CAL:
            real = self.splits[exp]
            s = arm.smoke_split(self.df, real, exp)
            self.assertEqual(s, arm.smoke_split(self.df, real, exp))
            self.assertEqual(len(s['pool']), 2030)
            self.assertEqual(len(s['S0_1']), 30)
            self.assertEqual(len(s['R_1']), 10)
            self.assertFalse(common.holdouts(exp, s) & set(s['pool']))
            self.assertTrue(common.holdouts(exp, s) | set(s['pool']) <= set(real['pool']))
            high = s['X7' if exp == 'E1' else 'XF']
            self.assertEqual(len(high), 80)
            self.assertGreaterEqual(self.df.loc[high, 'dBdt'].min(), self.df.loc[sorted(set(real['pool'])-set(high)), 'dBdt'].max())

    def test_guard_before_io(self):
        with patch.object(common.pd, 'read_csv', side_effect=RuntimeError('No IO allowed')):
            for exp in common.CAL:
                r = common.PoolReader(exp, 'A1', self.splits[exp])
                for name in (*common.EVAL[exp], common.CAL[exp]):
                    with self.assertRaises(AssertionError):
                        r.read(self.splits[exp][name][:1])
                unknown = next(i for i in r.pool if i not in r.authorized)
                with self.assertRaises(AssertionError):
                    r.read([unknown])
            # Explicitly exercise support assertion even with a corrupted pool permission.
            r = common.PoolReader('E2', 'A1', self.splits['E2'])
            outside = self.splits['E2']['XF'][0]
            r.pool.add(outside)
            r.forbidden.discard(outside)
            r.authorized.add(outside)
            with self.assertRaisesRegex(AssertionError, 'support'):
                r.read([outside])

    def test_no_cross_arm_authorization(self):
        s = self.splits['E1']
        a, m = common.PoolReader('E1', 'A1', s), common.PoolReader('E1', 'M1', s)
        new = next(i for i in a.pool if i not in a.authorized)
        a.authorize([new])
        with patch.object(common, 'read_targets', return_value=np.array([1.])):
            self.assertEqual(a.read([new]).tolist(), [1.])
            with self.assertRaises(AssertionError):
                m.read([new])

    def test_adapter_bitwise_equivalence_and_isolation(self):
        rng = np.random.default_rng(73)
        frame = pd.DataFrame(rng.normal(size=(18, 6)), columns=legacy.FEATURES)
        frame['y'] = rng.normal(size=18)
        original = copy.deepcopy(legacy.CONFIG)
        adapted = common.adapter(1, random_state=20261004)
        self.assertEqual(adapted.CONFIG, legacy.CONFIG)
        first, second = legacy.fit_m2(frame), adapted.fit_m2(frame)
        for a, b in zip(legacy.predict(first, frame), adapted.predict(second, frame)):
            np.testing.assert_array_equal(a, b)
        e1, e2 = common.adapter(1), common.adapter(2)
        self.assertEqual(legacy.CONFIG, original)
        self.assertNotEqual(e1.CONFIG['model']['gp_random_state'], e2.CONFIG['model']['gp_random_state'])
        e1.CONFIG['features']['gp_inputs'].append('private')
        self.assertNotIn('private', e2.CONFIG['features']['gp_inputs'])
        self.assertEqual(legacy.CONFIG, original)

    def test_batch_tamper(self):
        record = dict(fingerprint={'a': 1}, points=[dict(sample_id=3)])
        record['sha256'] = common.digest(record)
        self.assertEqual(arm.validate_batch(record, {'a': 1}, [3, 4], 1), [3])
        with self.assertRaises(AssertionError):
            arm.validate_batch(record, {'a': 2}, [3, 4], 1)
        record['points'][0]['sample_id'] = 4
        with self.assertRaises(AssertionError):
            arm.validate_batch(record, {'a': 1}, [3, 4], 1)

    def test_gate_every_stop(self):
        for stop in range(6):
            p = {f'H{i+1}': .05 if i == stop else .001 for i in range(6)}
            self.assertEqual(list(evaluate.fixed_sequence(p).values()), ['rejected']*stop+['not_rejected']+['not_tested']*(5-stop))

    def test_conclusion_all_combinations(self):
        status = {f'H{i}': 'rejected' for i in range(1, 7)}
        for cv_a, cv_m, v, h, process in itertools.product((False, True), repeat=5):
            cv = dict(A=cv_a, M=cv_m, R=True)
            v80 = {m: dict(F=v, T=v) for m in 'AMR'}
            honest = {m: dict(F=h, T=h) for m in 'AMR'}
            result = evaluate.conclusion_map(status, cv, v80, honest, process)
            self.assertEqual(result['M-X7'], process and cv_m)
            self.assertEqual(result['M-NI10-X7'], process and cv_a and cv_m)
            self.assertEqual(result['A-F'], process and v and h)
            self.assertEqual(result['M-T'], process and v and h)

    def test_hypothesis_mapping_and_counts(self):
        result = evaluate.aggregate(synthetic_results())
        self.assertTrue(all(result['conclusions'].values()))
        for h, value in enumerate([1.1, .2, 1., 1.1, 1., 1.1], 1):
            np.testing.assert_allclose(result['hypotheses'][f'H{h}']['d_k'], value)
        self.assertEqual(result['validity_pass_counts']['E1']['M']['CV'], 30)
        self.assertEqual(result['sampling_counts']['E1']['M']['additions']['fset'], {'50': 3600})
        self.assertEqual(result['validity_pass_counts']['E2']['M']['HONEST90_F'], 30)
        self.assertNotIn('XFT', result['HONEST90']['M'])

    def test_coverage_thresholds_and_26_of_30(self):
        r = synthetic_results()
        for k in range(1, 5):
            r['E1'][f'M{k}']['metrics']['X7']['coverage'] = 505
        self.assertTrue(evaluate.aggregate(r)['CV']['M'])
        r['E1']['M5']['metrics']['G7r']['coverage'] = 240
        self.assertFalse(evaluate.aggregate(r)['CV']['M'])
        for k in range(1, 6):
            r['E2'][f'A{k}']['metrics']['XF']['coverage'] = 4824
        summary = evaluate.aggregate(r)
        self.assertTrue(summary['V80']['A']['F'])
        self.assertFalse(summary['HONEST90']['A']['F'])
        self.assertFalse(summary['conclusions']['A-F'])
        self.assertEqual(summary['hypotheses']['H3']['status'], 'rejected')
        for k in range(1, 6):
            r['E2'][f'M{k}']['metrics']['XT']['width'] = 3.00001
        summary = evaluate.aggregate(r)
        self.assertTrue(summary['HONEST90']['M']['T'])
        self.assertFalse(summary['V80']['M']['T'])

    def test_width_zero_and_exact_boundary(self):
        r = synthetic_results()
        for exp in common.CAL:
            for a in common.ARMS:
                for metric in r[exp][a]['metrics'].values():
                    metric['width'] = 0.
        self.assertTrue(all(evaluate.aggregate(r)['CV'].values()))
        for k in range(1, 6):
            r['E1'][f'A{k}']['metrics']['X7']['width'] = 1e-15
        self.assertFalse(evaluate.aggregate(r)['CV']['A'])

    def test_missing_or_nonfinite_pairs(self):
        r = synthetic_results()
        del r['E1']['A30']
        with self.assertRaises(AssertionError):
            evaluate.aggregate(r)
        r = synthetic_results()
        r['E2']['A1']['metrics']['XF']['winkler'] = np.nan
        with self.assertRaises(AssertionError):
            evaluate.aggregate(r)

    def test_conformal_quantile(self):
        y = np.arange(20.)
        self.assertEqual(calibrate.quantile(y, np.zeros(20), np.ones(20)), 18.)
        for args in [(np.zeros(3), np.zeros(3), np.ones(3)), ([np.nan]*20, np.zeros(20), np.ones(20)),
                     (np.zeros(20), np.zeros(20), np.zeros(20))]:
            with self.assertRaises(AssertionError):
                calibrate.quantile(*args)

    def test_stage_completeness_before_labels(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(common, 'read_targets', side_effect=RuntimeError('forbidden')):
            with self.assertRaises(FileNotFoundError):
                calibrate.calibrate(Path(tmp), Path(tmp)/'first')
            with self.assertRaises(FileNotFoundError):
                evaluate.evaluate(Path(tmp), Path(tmp)/'first')

    def test_seal_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common.freeze(root/'calibration.json', b'{}\n')
            with self.assertRaises(FileExistsError):
                calibrate.calibrate(root, root)
            common.freeze(root/'metrics.json', b'{}\n')
            with self.assertRaises(FileExistsError):
                evaluate.evaluate(root, root)
            with self.assertRaises(AssertionError):
                common.freeze(root/'metrics.json', b'changed\n')

    def test_synthetic_three_stage_sealing(self):
        # Exercise actual calibration/evaluation orchestration with entirely
        # synthetic predictions and labels. No fitting, no real target reader.
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            source, out = Path(tmp)/'source', Path(tmp)/'first'
            splits, seals, label_calls = {}, {}, []
            for e, exp in enumerate(common.CAL):
                splits[exp] = {'pool': [e*1000]}
                for j, name in enumerate((common.CAL[exp], *common.EVAL[exp])):
                    splits[exp][name] = list(range(e*1000+1+j*20, e*1000+21+j*20))
                seals[exp] = {}
                for a in common.ARMS:
                    folder = source/'arms'/exp/a
                    common.freeze(folder/'result.json', b'{}\n')
                    seals[exp][a] = common.sha(folder/'result.json')
                    common.freeze(folder/'DONE', (seals[exp][a]+'\n').encode('utf-8'))
            def predictions(folder, b, exp, split):
                return pd.DataFrame([dict(set=name, sample_id=i, mu=0., sigma=1.)
                                     for name in (common.CAL[exp], *common.EVAL[exp]) for i in split[name]])
            def targets(ids, allowed, forbidden=()):
                self.assertTrue(set(ids) <= set(allowed))
                self.assertFalse(set(ids) & set(forbidden))
                label_calls.append(list(ids))
                return np.zeros(len(ids))
            for module in (calibrate, evaluate):
                stack.enter_context(patch.object(module, 'require_box'))
                stack.enter_context(patch.object(module, 'load_design', return_value=(pd.DataFrame(), splits)))
                stack.enter_context(patch.object(module, 'audit_results', side_effect=lambda *a, **k: (synthetic_results(), seals, ['synthetic replay fixture'])))
                stack.enter_context(patch.object(module, 'read_predictions', side_effect=predictions))
                stack.enter_context(patch.object(module, 'read_targets', side_effect=targets))
            calibrate.calibrate(source, out)
            self.assertEqual(label_calls, [splits[exp][common.CAL[exp]] for exp in common.CAL])
            c = common.read_json(out/'calibration.json')
            evaluate.validate_calibration(c, splits, seals)
            bad = copy.deepcopy(c)
            bad['calibration']['E1']['A1'][0] = 9.
            with self.assertRaises(AssertionError):
                evaluate.validate_calibration(bad, splits, seals)
            def baseline(*args, **kwargs):
                self.assertTrue((out/'primary_evaluation.json').exists(), 'iGSE must follow evaluation seal')
                ids = [i for exp in common.CAL for name in common.EVAL[exp] for i in splits[exp][name]]
                return pd.DataFrame(dict(sample_id=ids, predicted_W_m3=np.ones(len(ids))))
            with patch.object(evaluate.pd, 'read_csv', side_effect=baseline):
                evaluate.evaluate(source, out)
            self.assertTrue((out/'EVALUATED').is_file())
            saved = common.read_json(out/'metrics.json')
            self.assertEqual(len(saved['arms']['E1']), 90)
            self.assertEqual(set(saved['igse_baseline']), {'X7', 'G7r', 'G8', 'XF', 'XT', 'XFT'})
            self.assertEqual(set(saved['validity_pass_counts']), {'E1', 'E2'})
            self.assertNotEqual(saved['validity_pass_counts'], saved['sampling_counts'])
            with self.assertRaises(FileExistsError):
                calibrate.calibrate(source, out)
            with self.assertRaises(FileExistsError):
                evaluate.evaluate(source, out)

    def test_prediction_order_and_finite_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            split = {'CAL7r': [1, 2], 'X7': [3], 'G7r': [4]}
            data = pd.DataFrame(dict(set=['CAL7r', 'CAL7r', 'X7', 'G7r'], sample_id=[1, 2, 3, 4], mu=[0.]*4, sigma=[1.]*4))
            common.atomic(folder/'predictions_0.csv', data.to_csv(index=False, lineterminator='\n').encode())
            self.assertEqual(len(audit.read_predictions(folder, 0, 'E1', split)), 4)
            data.loc[0, 'sample_id'] = 2
            common.atomic(folder/'predictions_0.csv', data.to_csv(index=False, lineterminator='\n').encode())
            with self.assertRaises(AssertionError):
                audit.read_predictions(folder, 0, 'E1', split)

    def test_source_waiver_and_hashes(self):
        if self.df is None: self.skipTest('MagNet input features/split not distributed')
        common.verify_sources(True)
        if not (common.ROOT/'data/magnet/N87/B.npy').exists():
            with self.assertRaises(FileNotFoundError):
                common.verify_sources(False)

    def test_text_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'text.txt'
            common.append(p, '中文')
            self.assertEqual(p.read_bytes(), '中文\n'.encode('utf-8'))
        for p in (common.ROOT/'scripts').glob('magnet8_*.py'):
            self.assertNotIn(b'\r', p.read_bytes())

    def test_schedule_and_dry_run(self):
        jobs = sweep.schedule()
        self.assertEqual(len(jobs), 180)
        self.assertEqual(len(set(jobs)), 180)
        self.assertEqual(jobs[:6], [('E1', 'A1'), ('E1', 'M1'), ('E1', 'R1'), ('E2', 'A1'), ('E2', 'M1'), ('E2', 'R1')])
        with tempfile.TemporaryDirectory() as tmp, patch.object(sweep.subprocess, 'Popen', side_effect=RuntimeError('must not start')):
            folder = Path(tmp)/'arms/E1/A1'
            common.freeze(folder/'result.json', b'{}\n')
            common.freeze(folder/'DONE', (common.sha(folder/'result.json')+'\n').encode())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(sweep.run(Path(tmp), dry_run=True), 0)
            self.assertIn('Pending: 179/180', output.getvalue())
            self.assertNotIn('E1/A1\n', output.getvalue())

    def test_watchdog_hysteresis(self):
        self.assertTrue(sweep.paused_state(False, 3.7*2**30))
        self.assertFalse(sweep.paused_state(False, 4.*2**30))
        self.assertTrue(sweep.paused_state(True, 4.*2**30))
        self.assertFalse(sweep.paused_state(True, 4.4*2**30))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'meminfo'
            common.freeze(p, b'MemTotal: 99999 kB\nMemAvailable: 12345 kB\n')
            self.assertEqual(sweep.available(p), 12345*1024)

    def test_formal_windows_blocked(self):
        with patch.object(common.platform, 'system', return_value='Windows'):
            with self.assertRaises(RuntimeError):
                common.require_box()

    @unittest.skipUnless(importlib.util.find_spec('matplotlib'), 'matplotlib unavailable on local_machine')
    def test_synthetic_figures(self):
        from magnet8_figures import render
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common.write_json(root/'input/metrics.json', evaluate.aggregate(synthetic_results()))
            render(root/'input/metrics.json', root/'figures', require_seal=False)
            for name in ('pairs', 'coverage', 'learning_sampling'):
                self.assertGreater((root/'figures'/f'r8_{name}.png').stat().st_size, 1000)


class WatchdogThresholdTests(unittest.TestCase):
    def test_watchdog_threshold_parsing(self):
        defaults = sweep.parse_args([])
        self.assertEqual((defaults.pause_gib, defaults.resume_gib), (3.8, 4.3))
        custom = sweep.parse_args(['--pause-gib', '2.5', '--resume-gib', '3.0'])
        self.assertEqual((custom.pause_gib, custom.resume_gib), (2.5, 3.0))
        with patch.object(sys, 'argv', ['magnet8_sweep.py', '--pause-gib', '2.5', '--resume-gib', '3.0']), \
                patch.object(sweep, 'run', return_value=0) as run:
            with self.assertRaises(SystemExit) as caught:
                sweep.main()
            self.assertEqual(caught.exception.code, 0)
            run.assert_called_once_with(jobs=2, dry_run=False, low_memory_timeout=900,
                                        pause_gib=2.5, resume_gib=3.0)

    def test_watchdog_invalid_thresholds(self):
        for pause, resume in [('0', '4.3'), ('-1', '4.3'), ('3', '3'), ('4', '3'),
                              ('2', '0'), ('nan', '4'), ('2', 'nan'), ('2', 'inf'),
                              ('-inf', '4'), ('bad', '4')]:
            with self.subTest(pause=pause, resume=resume), contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as caught:
                    sweep.parse_args(['--pause-gib', pause, '--resume-gib', resume])
                self.assertEqual(caught.exception.code, 2)
                self.assertIn('error:', error.getvalue())

    def test_watchdog_custom_hysteresis(self):
        for memory, unpaused, paused in [(2.4, True, True), (2.5, False, True),
                                         (2.7, False, True), (3.0, False, True),
                                         (3.1, False, False)]:
            with self.subTest(memory=memory):
                self.assertEqual(sweep.paused_state(False, memory*2**30, 2.5, 3.0), unpaused)
                self.assertEqual(sweep.paused_state(True, memory*2**30, 2.5, 3.0), paused)


if __name__ == '__main__':
    unittest.main()
