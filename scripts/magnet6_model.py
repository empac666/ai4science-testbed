#!/usr/bin/env python3
"""M2, a single guarded label reader, and fixed-normalization GP acquisition."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
from collections import Counter
import itertools
import math
import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
from sklearn.preprocessing import StandardScaler
from magnet6_design import SOURCE, config

CONFIG = config()
FEATURES = CONFIG['features']['gp_inputs']
FLOOR = 2.220446049250313e-16


def load_y(ids, forbidden):
    """Assert before target parsing; skip unrequested physical CSV rows entirely."""
    ids = list(map(int, ids))
    assert not set(ids) & set(forbidden), 'Holdout targets forbidden'
    assert len(ids) == len(set(ids)), 'Duplicate query'
    header = pd.read_csv(SOURCE, usecols=['sample_id'])
    mask = header.sample_id.isin(ids)
    assert int(mask.sum()) == len(ids), 'Unknown sample id'
    selected = pd.read_csv(SOURCE, skiprows=(np.flatnonzero(~mask.to_numpy()) + 1).tolist(),
                           usecols=['sample_id', 'measured_W_m3']).set_index('sample_id')
    p = selected.loc[ids, 'measured_W_m3'].to_numpy()
    assert np.all(np.isfinite(p)) and np.all(p > 0)
    return np.log10(p)


def evaluation_frame(df, ids, split, forbidden=()):
    """Separate evaluation-only route, restricted to the declared holdout sets."""
    assert set(ids) <= set().union(*(set(split[k]) for k in ('C6', 'T6', 'CAL6')))
    result = df.loc[ids].copy()
    result['y'] = load_y(ids, forbidden)
    return result


def linear(df):
    columns = {'1': np.ones(len(df)), 'T_C^2': df.T_C.to_numpy() ** 2}
    return np.column_stack([columns[k] if k in columns else df[k].to_numpy()
                            for k in CONFIG['features']['linear_mean_features']])


def make_kernel():
    return ConstantKernel(1., (.01, 100)) * RBF([1.] * len(FEATURES), (.01, 100)) + WhiteKernel(.01, (1e-8, 10))


def fit_m2(train_df):
    x = train_df[FEATURES].to_numpy()
    y = train_df.y.to_numpy()
    coef = np.linalg.lstsq(linear(train_df), y, rcond=None)[0]
    scaler = StandardScaler().fit(x)
    c = CONFIG['model']
    gp = GaussianProcessRegressor(kernel=make_kernel(), alpha=c['gp_alpha'], normalize_y=c['gp_normalize_y'],
                                  n_restarts_optimizer=c['gp_restarts'], random_state=c['gp_random_state'])
    gp.fit(scaler.transform(x), y - linear(train_df) @ coef)
    return scaler, coef, gp


def predict(model, df):
    scaler, coef, gp = model
    mu, sigma = gp.predict(scaler.transform(df[FEATURES].to_numpy()), return_std=True)
    return linear(df) @ coef + mu, np.maximum(sigma, FLOOR)


def conformal_q(model, cal_df):
    mu, sigma = predict(model, cal_df)
    scores = np.abs(cal_df.y.to_numpy() - mu) / sigma
    rank = math.ceil((len(scores) + 1) * (1 - CONFIG['model']['alpha']))
    if rank > len(scores):
        raise ValueError('Calibration set too small for finite conformal quantile')
    return float(np.partition(scores, rank - 1)[rank - 1])


def metrics(y, mu, sigma, q):
    y, mu, sigma = map(np.asarray, (y, mu, sigma))
    lo, hi = mu - q * sigma, mu + q * sigma
    width = hi - lo
    winkler = width + 20 * np.maximum(lo - y, 0) + 20 * np.maximum(y - hi, 0)
    return dict(n=len(y), coverage=int(np.sum((lo <= y) & (y <= hi))), width=float(width.mean()),
                winkler=float(winkler.mean()), relative_error=float(np.median(np.abs(10. ** (mu - y) - 1))),
                mae=float(np.mean(np.abs(mu - y))), bias=float(np.mean(mu - y)))


def _believer(model, z, count, cells=None, prior=(), sample_ids=None):
    """O(n_train*n_candidates*batch) updates; never allocate candidate covariance."""
    gp = model[2] if isinstance(model, tuple) else model
    z = np.asarray(z)
    ids = np.arange(len(z)) if sample_ids is None else np.asarray(sample_ids)
    assert len(set(ids.tolist())) == len(z) and 0 <= count <= len(z)
    order = np.argsort(ids, kind='stable')
    z, ids = z[order], ids[order]
    categories = np.asarray(cells)[order] if cells is not None else np.full(len(z), '')
    counts = Counter(prior)
    n = len(gp.X_train_)
    V = np.empty((n + count, len(z)))
    V[:n] = solve_triangular(gp.L_, gp.kernel_(gp.X_train_, z), lower=True, check_finite=False)
    variance = gp.kernel_.diag(z) - np.einsum('ij,ij->j', V[:n], V[:n])
    available = np.ones(len(z), dtype=bool)
    chosen, steps = [], []
    for b in range(count):
        sigma = np.maximum(np.sqrt(np.maximum(variance, 0)) * float(gp._y_train_std), FLOOR)
        ac = np.array([counts[c] for c in categories]) if cells is not None else np.zeros(len(z), dtype=int)
        scores = sigma / np.sqrt(1 + ac)
        j = int(np.argmax(np.where(available, scores, -np.inf)))
        chosen.append(int(order[j]))
        steps.append(dict(sample_id=int(ids[j]), sigma=float(sigma[j]), score=float(scores[j]),
                          a_c=int(ac[j]), cell=str(categories[j])))
        # WhiteKernel is included only on the new diagonal, never cross-covariance.
        v = V[:n + b, j]
        diagonal = float(gp.kernel_.diag(z[j:j + 1])[0] + gp.alpha - v @ v)
        if diagonal <= 0:
            raise ValueError('Nonpositive believer Schur complement')
        V[n + b] = (gp.kernel_(z[j:j + 1], z).ravel() - v @ V[:n + b]) / np.sqrt(diagonal)
        variance -= V[n + b] ** 2
        available[j] = False
        counts[categories[j]] += 1
    return chosen, steps


def believer(model, z_candidates, count, sample_ids=None):
    return _believer(model, z_candidates, count, sample_ids=sample_ids)


def mixed_believer(model, z_candidates, count, cells, prior_selected_cells=(), sample_ids=None):
    return _believer(model, z_candidates, count, cells, prior_selected_cells, sample_ids)


def signflip_p(d):
    d = np.asarray(d, dtype=float)
    assert d.ndim == 1 and len(d) > 0 and np.isfinite(d).all()
    return sum(np.mean(np.asarray(s) * d) >= d.mean() - 1e-12
               for s in itertools.product((-1, 1), repeat=len(d))) / 2 ** len(d)


def fixed_sequence(results):
    active, output = True, {}
    for h in CONFIG['tests']['order']:
        value = results[h]
        p = value['p'] if isinstance(value, dict) else value
        assert 0 <= p <= 1
        status = ('rejected' if p < .05 else 'not_rejected') if active else 'not_tested'
        output[h] = status
        active = active and status == 'rejected'
    return output
