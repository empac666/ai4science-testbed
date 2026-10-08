"""Round-six tests use synthetic targets only."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import magnet6_model as model
from magnet6_design import H, digest, generate_split
from magnet6_arm import smoke_split, holdouts, validate_batch
from magnet6_evaluate import aggregate


def synthetic_features():
    ids = np.arange(40616)
    return pd.DataFrame(dict(sample_id=ids, corner=ids < 632)).set_index('sample_id', drop=False)


class Magnet6Tests(unittest.TestCase):
    def test_signflip_positive(self):
        self.assertEqual(model.signflip_p(np.ones(8)), 1/256)

    def test_signflip_ties(self):
        self.assertEqual(model.signflip_p(np.zeros(8)), 1)
        self.assertEqual(model.signflip_p([1, 0]), .5)
        self.assertEqual(model.signflip_p([1, -1]), .75)

    def test_fixed_sequence(self):
        values = dict(zip([f'H{i}' for i in range(1, 7)], [.01, .05, .001, .001, .1, .1]))
        self.assertEqual(list(model.fixed_sequence(values).values()), ['rejected', 'not_rejected'] + ['not_tested']*4)

    def test_metrics(self):
        m = model.metrics(np.array([-2., 0., 2.]), np.zeros(3), np.ones(3), 1)
        self.assertEqual(m['coverage'], 1)
        self.assertEqual(m['width'], 2)
        self.assertAlmostEqual(m['winkler'], 46/3)
        self.assertEqual(m['bias'], 0)
        self.assertAlmostEqual(m['mae'], 4/3)

    def test_conformal_rank(self):
        with patch.object(model, 'predict', return_value=(np.zeros(100), np.ones(100))):
            self.assertEqual(model.conformal_q(None, pd.DataFrame({'y': np.arange(1, 101)})), 91)

    def test_leak_before_io(self):
        with patch.object(model.pd, 'read_csv', side_effect=RuntimeError('must not read')):
            with self.assertRaises(AssertionError):
                model.load_y([7], {7})

    def test_load_y_filters_and_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.csv'
            path.write_text('sample_id,measured_W_m3\n4,100\n8,DO_NOT_PARSE\n2,10\n')
            with patch.object(model, 'SOURCE', path):
                np.testing.assert_array_equal(model.load_y([2, 4], {8}), [1, 2])

    def test_evaluation_boundary(self):
        with self.assertRaises(AssertionError):
            model.evaluation_frame(pd.DataFrame(), [4], {'C6': [1], 'T6': [2], 'CAL6': [3]})

    def test_split_and_r_order(self):
        df = synthetic_features()
        split = generate_split(df)
        self.assertEqual(split, generate_split(df.sample(frac=1, random_state=7)))
        self.assertEqual(H, 3634890171)
        self.assertEqual(len(holdouts(split)), 600)
        self.assertFalse(set(split['pool']) & holdouts(split))
        for k in range(1, 9):
            expected = np.random.default_rng(H+100+k).choice(sorted(set(split['pool'])-set(split[f'S0_{k}'])), 120, replace=False).tolist()
            self.assertEqual(split[f'R_{k}'], expected)
            self.assertFalse(set(split[f'S0_{k}']) & set(split[f'R_{k}']))
            self.assertFalse(set(split[f'S0_{k}']) & set(range(632)))

    def test_smoke_excludes_real_holdouts(self):
        df = synthetic_features()
        real = generate_split(df)
        smoke = smoke_split(df, real)
        self.assertEqual(smoke, smoke_split(df, real))
        self.assertFalse(set().union(*(set(v) for v in smoke.values())) & holdouts(real))
        self.assertEqual(len(smoke['pool']), 2030)
        self.assertEqual(len(holdouts(smoke)), 140)
        self.assertFalse(holdouts(smoke) & set(smoke['pool']))

    def gp(self):
        rng = np.random.default_rng(17)
        x = rng.normal(size=(14, 3))
        gp = GaussianProcessRegressor(kernel=ConstantKernel(1.3)*RBF([.7, 1.2, 2.])+WhiteKernel(.03),
                                      alpha=1e-10, normalize_y=True, optimizer=None).fit(x, rng.normal(size=14)*2)
        return gp, rng.normal(size=(43, 3))

    def direct(self, gp, z, count, cells=None, prior=(), ids=None):
        from collections import Counter
        counts = Counter(prior)
        condition = gp.X_train_.copy()
        available = np.ones(len(z), dtype=bool)
        selected, stats = [], []
        ids = np.arange(len(z)) if ids is None else np.asarray(ids)
        for _ in range(count):
            cov = gp.kernel_(condition) + np.eye(len(condition))*gp.alpha
            L = np.linalg.cholesky(cov)
            v = solve_triangular(L, gp.kernel_(condition, z), lower=True)
            sigma = np.sqrt(np.maximum(gp.kernel_.diag(z)-(v*v).sum(axis=0), 0))*float(gp._y_train_std)
            ac = np.array([counts[c] for c in cells]) if cells is not None else np.zeros(len(z))
            score = sigma / np.sqrt(1+ac)
            order = np.argsort(ids)
            j = order[np.argmax(np.where(available[order], score[order], -np.inf))]
            selected.append(int(j)); stats.append((sigma[j], score[j], ac[j]))
            available[j] = False
            condition = np.vstack([condition, z[j]])
            if cells is not None:
                counts[cells[j]] += 1
        return selected, stats

    def test_incremental_matches_direct(self):
        gp, z = self.gp()
        chosen, stats = model.believer(gp, z, 12)
        expected, direct = self.direct(gp, z, 12)
        self.assertEqual(chosen, expected)
        np.testing.assert_allclose([s['sigma'] for s in stats], [s[0] for s in direct], rtol=1e-8, atol=0)

    def test_mixed_matches_direct(self):
        gp, z = self.gp()
        cells = np.array(['a', 'b', 'c'])[np.arange(len(z)) % 3]
        ids = np.arange(len(z))[::-1] + 100
        chosen, stats = model.mixed_believer(gp, z, 12, cells, ['a', 'a', 'c'], ids)
        expected, direct = self.direct(gp, z, 12, cells, ['a', 'a', 'c'], ids)
        self.assertEqual(chosen, expected)
        np.testing.assert_allclose([[s['sigma'], s['score'], s['a_c']] for s in stats], direct, rtol=1e-8, atol=0)

    def test_tie_smallest_id(self):
        gp, z = self.gp()
        z = np.tile(z[0], (3, 1))
        chosen, _ = model.believer(gp, z, 3, [9, 2, 5])
        self.assertEqual(chosen, [1, 2, 0])

    def test_frozen_batch_tamper(self):
        record = {'fingerprint': {'a': 1}, 'points': [{'sample_id': 3}]}
        record['sha256'] = digest(record)
        self.assertEqual(validate_batch(record, {'a': 1}, [3, 4], 1), [3])
        with self.assertRaises(AssertionError):
            validate_batch(record, {'a': 2}, [3, 4], 1)
        record['points'][0]['sample_id'] = 4
        with self.assertRaises(AssertionError):
            validate_batch(record, {'a': 1}, [3, 4], 1)

    def test_conclusions_and_cv(self):
        results = {}
        for x in 'AMR':
            for k in range(1, 9):
                metrics = {s: dict(winkler={'A': 1., 'M': .9, 'R': 2.}[x], coverage=n,
                                  width=1., relative_error={'A': .2, 'M': .1, 'R': .3}[x], mae=.1, bias=0.)
                           for s, n in [('C6', 180), ('T6', 270)]}
                results[f'{x}{k}'] = dict(metrics=metrics, checkpoints=[dict(metrics=metrics) for _ in range(7)],
                                             sampling=dict(corner_count=5, cells={'triangle_T25': 120}))
        summary = aggregate(results)
        self.assertTrue(all(summary['conclusions'].values()))
        for k in (1, 2):
            results[f'A{k}']['metrics']['T6']['coverage'] = 239
        summary = aggregate(results)
        self.assertFalse(summary['CV']['A'])
        self.assertFalse(summary['conclusions']['A'])
        self.assertTrue(summary['conclusions']['M≈A'])


if __name__ == '__main__':
    unittest.main()
