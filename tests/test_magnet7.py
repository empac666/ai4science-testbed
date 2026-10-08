"""Round-seven input-only and synthetic-label tests; never read real holdout y."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import sys
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import magnet7_arm as arm
import magnet7_design as design
import magnet7_evaluate as evaluate
import magnet6_model as model


def synthetic_results():
    results = {}
    for x in 'AMR':
        for k in range(1, 21):
            metrics = {s: dict(n=n, winkler={'A': 1., 'M': .9, 'R': 2.}[x], coverage=n,
                              width=1., relative_error={'A': .2, 'M': .1, 'R': .3}[x], mae=.1, bias=0.)
                       for s, n in [('X7', 632), ('G7', 301)]}
            results[f'{x}{k}'] = dict(metrics=metrics, checkpoints=[dict(metrics=metrics) for _ in range(7)],
                                      sampling=dict(frontier_count=k, dBdt_bin={'0': 120}, fset={'50': 120}), selected_ids=[2, 3])
    return results


class Magnet7Tests(unittest.TestCase):
    def test_signflip_matches_legacy(self):
        rng = np.random.default_rng(37)
        for k in range(1, 13):
            for d in (rng.normal(size=k), rng.integers(-2, 3, k), np.zeros(k), np.ones(k)*1e-12):
                self.assertEqual(evaluate.signflip_p(d, chunk_size=127), model.signflip_p(d))

    def test_signflip_k20(self):
        self.assertEqual(evaluate.signflip_p(np.ones(20)), 2**-20)
        self.assertEqual(evaluate.signflip_p(np.zeros(20)), 1)

    def test_signflip_invalid(self):
        for d in ([], [np.nan], np.ones(21)):
            with self.assertRaises(AssertionError):
                evaluate.signflip_p(d)

    def test_gating_every_stop(self):
        for stop in range(5):
            ps = {f'H{i+1}': .05 if i == stop else .001 for i in range(5)}
            self.assertEqual(list(evaluate.fixed_sequence(ps).values()), ['rejected']*stop + ['not_rejected'] + ['not_tested']*(4-stop))

    def test_family_setpoints(self):
        f = pd.DataFrame(dict(frequency_Hz=[50000., 50100., 100000., 100100., 50000.],
                              amplitude_T=[.05]*5, waveform=['tri']*5, duty=[.5, .5, .5, .6, .5], plateau=[.1]*5))
        x = design.family_features(f)
        self.assertEqual(x.fset.tolist(), [50, 50, 100, 100, 50])
        self.assertEqual(x.family.tolist(), ['50_tri_5_2', '50_tri_5_2', '100_tri_5_2', '100_tri_6_2', '50_tri_5_2'])
        np.testing.assert_allclose(x.dBdt, np.log10(4*f.frequency_Hz*f.amplitude_T))
        # Median uses unique frequencies, not sample multiplicity.
        self.assertEqual(design.family_features(pd.concat([f]*3)).fset.unique().tolist(), [50, 100])

    def test_bin_boundaries(self):
        bins, edges = design.equal_bins([-1, 0, .999999, 1, 7, 8, 9], [0, 8])
        self.assertEqual(bins.tolist(), [0, 0, 0, 1, 7, 7, 7])
        self.assertEqual(edges, list(range(9)))
        with self.assertRaises(AssertionError):
            design.equal_bins([1], [1, 1])

    @unittest.skipUnless((design.OUT/'split.json').exists() and design.FEATURE_PATH.exists(), 'MagNet input features/split not distributed')
    def test_design_determinism_and_disjointness(self):
        df, split = design.load_design()
        self.assertEqual(design.H, 1869701181)
        self.assertEqual(split, design.generate_split(df.sample(frac=1, random_state=7)))
        design.validate_split(df, split)
        self.assertFalse(arm.holdouts(split) & set(split['pool']))
        for k in range(1, 21):
            expected = np.random.default_rng(design.H+100+k).choice(sorted(set(split['pool'])-set(split[f'S0_{k}'])), 120, replace=False).tolist()
            self.assertEqual(split[f'R_{k}'], expected)
        self.assertEqual(df.fset.nunique(), 20)
        self.assertEqual(df.family.nunique(), 291)

    @unittest.skipUnless((design.OUT/'split.json').exists() and design.FEATURE_PATH.exists(), 'MagNet input features/split not distributed')
    def test_smoke_safety(self):
        df, real = design.load_design()
        s = arm.smoke_split(df, real)
        self.assertEqual(s, arm.smoke_split(df, real))
        self.assertFalse(set().union(*(set(v) for v in s.values())) & arm.holdouts(real))
        self.assertEqual(len(s['X7']), 80)
        self.assertLessEqual(len(s['G7']), 150)
        self.assertEqual(df.loc[s['G7'], 'family'].nunique(), 3)
        self.assertEqual(df.loc[s['CAL7'], 'family'].nunique(), 2)
        self.assertEqual(len(s['pool']), 2030)
        self.assertGreaterEqual(df.loc[s['X7'], 'dBdt'].min(), df.loc[sorted(set(real['pool'])-set(s['X7'])), 'dBdt'].max())

    def test_leak_before_io(self):
        with patch.object(model.pd, 'read_csv', side_effect=RuntimeError('must not read')):
            with self.assertRaises(AssertionError):
                model.load_y([7], {7})
        s = dict(X7=[1], G7=[2], CAL7=[3])
        with patch.object(arm, 'load_y', side_effect=RuntimeError('must not read')):
            for ids, forbidden in [([4], set()), ([1], {1})]:
                with self.assertRaises(AssertionError):
                    arm.evaluation_frame(pd.DataFrame(), ids, s, forbidden)

    def test_evaluation_routes_through_reader(self):
        df = pd.DataFrame({'sample_id': [1, 2, 3]}).set_index('sample_id', drop=False)
        with patch.object(arm, 'load_y', return_value=np.array([2.])) as reader:
            result = arm.evaluation_frame(df, [2], dict(X7=[1], G7=[2], CAL7=[3]), {9})
            reader.assert_called_once_with([2], {9})
            self.assertEqual(result.y.tolist(), [2.])

    def test_mixed_bin_counts(self):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, WhiteKernel
        rng = np.random.default_rng(5)
        gp = GaussianProcessRegressor(kernel=RBF()+WhiteKernel(.1), optimizer=None, normalize_y=True).fit(rng.normal(size=(10, 2)), rng.normal(size=10))
        z = rng.normal(size=(40, 2))
        cells = np.array([str(i % 8) for i in range(40)])
        _, points = model.mixed_believer(gp, z, 12, cells, ['0', '0', '3'], np.arange(40))
        from collections import Counter
        counts = Counter(['0', '0', '3'])
        for p in points:
            self.assertEqual(p['a_c'], counts[p['cell']])
            self.assertAlmostEqual(p['score'], p['sigma']/np.sqrt(1+counts[p['cell']]))
            counts[p['cell']] += 1

    def test_batch_tamper(self):
        r = dict(fingerprint={'a': 1}, points=[{'sample_id': 3}])
        r['sha256'] = design.digest(r)
        self.assertEqual(arm.validate_batch(r, {'a': 1}, [3, 4], 1), [3])
        with self.assertRaises(AssertionError):
            arm.validate_batch(r, {'a': 2}, [3, 4], 1)
        r['points'][0]['sample_id'] = 4
        with self.assertRaises(AssertionError):
            arm.validate_batch(r, {'a': 1}, [3, 4], 1)

    def test_cv_and_conclusions(self):
        r = synthetic_results()
        self.assertTrue(all(evaluate.aggregate(r)['conclusions'].values()))
        for k in range(1, 4):
            r[f'A{k}']['metrics']['G7']['coverage'] = 240  # ceil(.8*301)=241
        self.assertTrue(evaluate.aggregate(r)['CV']['A'])
        r['A4']['metrics']['X7']['coverage'] = 505
        summary = evaluate.aggregate(r)
        self.assertFalse(summary['CV']['A'])
        self.assertFalse(summary['conclusions']['A-X'])
        self.assertFalse(summary['conclusions']['A-G'])
        self.assertTrue(summary['conclusions']['A-RE'])
        self.assertTrue(summary['conclusions']['M≈A'])
        for k in range(1, 5):
            r[f'M{k}']['metrics']['X7']['width'] = 3.00001
        self.assertFalse(evaluate.aggregate(r)['conclusions']['M-X'])

    def test_hypothesis_mapping(self):
        r = synthetic_results()
        s = evaluate.aggregate(r)
        for h, expected in zip(range(1, 6), [1, 1, .1, 1.1, .2]):
            np.testing.assert_allclose(s['hypotheses'][f'H{h}']['d_k'], expected)
        for k in range(1, 21):
            r[f'A{k}']['metrics']['X7']['winkler'] = 3.
        s = evaluate.aggregate(r)
        self.assertFalse(any(s['conclusions'].values()))
        self.assertEqual(s['hypotheses']['H5']['status'], 'not_tested')

    def test_missing_results_before_label_access(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys, 'argv', ['evaluate', '--source', tmp, '--out', tmp+'/first']), patch.object(evaluate, 'load_design', side_effect=RuntimeError('too early')):
            with self.assertRaises(FileNotFoundError):
                evaluate.main()

    def test_sealed_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys, 'argv', ['evaluate', '--out', tmp]):
            with self.assertRaises(FileExistsError):
                evaluate.main()

    def test_synthetic_figures(self):
        from magnet7_figures import render
        r = evaluate.aggregate(synthetic_results())
        df = pd.DataFrame(dict(sample_id=range(4), log10_f=[4.7, 5.1, 5.2, 5.5], log10_Bpk=[-1.5, -1.2, -.9, -1.3])).set_index('sample_id', drop=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'metrics.json').write_text(json.dumps(r))
            render(path/'metrics.json', path, (df, {'pool': [0, 1, 2, 3], 'S0_1': [0, 1]}))
            for name in ('pairs', 'learning_curves', 'sampling'):
                self.assertGreater((path/f'r7_{name}.png').stat().st_size, 1000)


if __name__ == '__main__':
    unittest.main()
