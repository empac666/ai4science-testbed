#!/usr/bin/env python3
"""Frozen DC-link surrogates; fitting uses train only, intervals use calib only."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import sys
import hashlib
import json
import math
import shutil
import resource
resource.setrlimit(resource.RLIMIT_AS, (2500 * 1024**2, 2500 * 1024**2))
import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

CONFIG = dict(alpha=0.1, load_bins=8, gp_restarts=2, seed=20261002,
              gp_constant=1.0, gp_constant_bounds=[0.01, 100.0],
              gp_length_scales=[1.0]*4, gp_length_bounds=[0.01, 100.0],
              gp_white=0.01, gp_white_bounds=[1e-8, 10.0],
              gp_alpha=1e-10, gp_normalize_y=True,
              mlp_hidden=[32, 32], mlp_max_iter=10000, mlp_alpha=0.0001,
              mlp_tol=1e-6, mlp_learning_rate=0.001, mlp_early_stopping=False,
              mlp_activation='relu', mlp_solver='adam', mlp_no_change=100,
              analytic_features=['intercept', 'dead_time_s*f_carrier/load',
                                 'f_grid/(2*pi*bw_iac_Hz)', 'aperture_s*f_carrier'])
FEATURES = ['load', 'dead_time_us', 'bw_iac_khz', 'aperture_delay_us']
GROUPS = ['train', 'calib', 'test', 'ood_deadtime3', 'ood_lowload_lowbw']
METHODS = ['load_interp_conformal', 'analytic_conformal', 'gp_conformal',
           'mlp_conformal', 'gp_native', 'gp_normalized_conformal']
SETS = ['test', 'ood', 'ood_deadtime3', 'ood_lowload_lowbw']

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_split():
    split = json.loads((ROOT/'data/dclink/split.json').read_text())
    manifest = json.loads((ROOT/'lab/cases/dclink/split_manifest.json').read_text())
    body = {k:v for k,v in split.items() if k not in ('split_sha256', 'design_sha256')}
    actual = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if actual != split['split_sha256'] or actual != manifest['split_sha256']:
        raise ValueError('Frozen split SHA256 mismatch')
    if sha(ROOT/'data/dclink/design.json') != split['design_sha256'] or split['design_sha256'] != manifest['design_sha256']:
        raise ValueError('Design SHA256 mismatch')
    design = json.loads((ROOT/'data/dclink/design.json').read_text())
    seen = set()
    for g in GROUPS:
        ids = split[g]
        if len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError('Duplicate or leaking split')
        seen.update(ids)
    if seen != {r['case_id'] for r in design}:
        raise ValueError('Split does not partition design')
    for r in design:
        dt = abs(r['dead_time_us']-3.0) < 1e-9
        corner = not dt and r['load'] <= .35 and r['bw_iac_khz'] <= 75
        if (r['case_id'] in split['ood_deadtime3']) != dt or (r['case_id'] in split['ood_lowload_lowbw']) != corner:
            raise ValueError('OOD rule mismatch')
    return split

def conformal_quantile(scores, alpha=.1):
    scores = np.asarray(scores, dtype=float)
    if not len(scores) or not np.isfinite(scores).all() or not 0 < alpha < 1:
        raise ValueError('Invalid calibration scores or alpha')
    # Finite-sample rank; n+1 means the required interval is unbounded.
    rank = math.ceil((len(scores)+1)*(1-alpha))
    return float(np.sort(scores)[rank-1]) if rank <= len(scores) else float('inf')

def analytic_features(x):
    sys.path.insert(0, str(ROOT/'data/dclink_src/simsw'))
    from dclink_simsw.common import SimulationConfig
    cfg = SimulationConfig()
    return np.column_stack([np.ones(len(x)), x[:,1]*1e-6*cfg.f_carrier_Hz/x[:,0],
                            cfg.f_grid_Hz/(2*np.pi*x[:,2]*1000), x[:,3]*1e-6*cfg.f_carrier_Hz])

def interval_metrics(y, pred, lower, upper):
    err = pred-y
    return dict(n=len(y), mae=float(np.mean(abs(err))), max_abs_error=float(np.max(abs(err))),
                bias=float(np.mean(err)), coverage=float(np.mean((y>=lower)&(y<=upper))),
                mean_width=float(np.mean(upper-lower)))

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def evidence_metrics(metrics):
    result = {}
    for key, value in metrics.items():
        current = result
        parts = key.split('.')
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = int(value) if isinstance(value, bool) else value
    return result

def main():
    print(json.dumps(CONFIG, ensure_ascii=False), flush=True)
    split = verify_split()
    source = ROOT/'data/dclink/sweep.csv'
    df = pd.read_csv(source).sort_values('case_id').reset_index(drop=True)
    design = pd.DataFrame(json.loads((ROOT/'data/dclink/design.json').read_text())).set_index('case_id')
    if df.case_id.duplicated().any() or set(df.case_id) != set(design.index):
        raise ValueError('Require complete sweep matching frozen design')
    if not np.isfinite(df[FEATURES+['y']].to_numpy()).all():
        raise ValueError('Nonfinite sweep')
    if not np.allclose(df.set_index('case_id').loc[design.index, FEATURES], design[FEATURES], rtol=0, atol=1e-12):
        raise ValueError('Sweep inputs differ from frozen design')
    predictive_body = df[['case_id']+FEATURES+['y']].to_csv(index=False).encode()
    fingerprint = dict(config=CONFIG, predictive_data_sha256=hashlib.sha256(predictive_body).hexdigest(),
                       split_sha256=split['split_sha256'],
                       physics_sha256=sha(ROOT/'data/dclink_src/simsw/dclink_simsw/common.py'),
                       training_script_sha256=sha(Path(__file__)))
    first = ROOT/'lab/cases/dclink/surrogate_first'
    if (first/'provenance.json').exists() and json.loads((first/'provenance.json').read_text()) != fingerprint:
        raise ValueError('First-run provenance differs; preserve first run and explicitly report any amendment')
    x = df[FEATURES].to_numpy(); y = df.y.to_numpy()
    train = df.case_id.isin(split['train']).to_numpy(); calib = df.case_id.isin(split['calib']).to_numpy()
    edges = np.linspace(x[train,0].min(), x[train,0].max(), CONFIG['load_bins']+1)
    bins = np.clip(np.digitize(x[train,0], edges)-1, 0, CONFIG['load_bins']-1)
    centers=[]; means=[]
    for b in range(CONFIG['load_bins']):
        mask = bins==b
        if mask.any():
            centers.append((edges[b]+edges[b+1])/2); means.append(y[train][mask].mean())
    predictions = {'load_interp': np.interp(x[:,0], centers, means)}
    a = analytic_features(x)
    coef = np.linalg.lstsq(a[train], y[train], rcond=None)[0]
    predictions['analytic'] = a@coef
    scale = StandardScaler().fit(x[train]); z=scale.transform(x)
    kernel = ConstantKernel(CONFIG['gp_constant'], CONFIG['gp_constant_bounds'])*RBF(CONFIG['gp_length_scales'], CONFIG['gp_length_bounds'])+WhiteKernel(CONFIG['gp_white'], CONFIG['gp_white_bounds'])
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, alpha=CONFIG['gp_alpha'],
                                  n_restarts_optimizer=CONFIG['gp_restarts'], random_state=CONFIG['seed']).fit(z[train], y[train])
    predictions['gp'], sigma = gp.predict(z, return_std=True)
    sigma = np.maximum(sigma, np.finfo(float).eps)
    mlp = MLPRegressor(hidden_layer_sizes=tuple(CONFIG['mlp_hidden']), early_stopping=False,
                       random_state=CONFIG['seed'], max_iter=CONFIG['mlp_max_iter'], alpha=CONFIG['mlp_alpha'],
                       tol=CONFIG['mlp_tol'], learning_rate_init=CONFIG['mlp_learning_rate'],
                       activation=CONFIG['mlp_activation'], solver=CONFIG['mlp_solver'],
                       n_iter_no_change=CONFIG['mlp_no_change']).fit(z[train], y[train])
    predictions['mlp'] = mlp.predict(z)
    intervals={}; metrics={}; records=[]
    labels = {i:g for g in GROUPS for i in split[g]}
    for method,pred in predictions.items():
        q = conformal_quantile(abs(pred[calib]-y[calib]), CONFIG['alpha'])
        intervals[method+'_conformal']=(pred, np.full(len(y),q))
        metrics[f'{method}_conformal.calib.q']=q
    qn=conformal_quantile(abs(predictions['gp'][calib]-y[calib])/sigma[calib], CONFIG['alpha'])
    intervals['gp_native']=(predictions['gp'],1.645*sigma)
    intervals['gp_normalized_conformal']=(predictions['gp'],qn*sigma)
    metrics['gp_normalized_conformal.calib.q']=qn
    for method,(pred,half) in intervals.items():
        lo=pred-half; hi=pred+half
        for group in SETS:
            ids = split['ood_deadtime3']+split['ood_lowload_lowbw'] if group=='ood' else split[group]
            mask=df.case_id.isin(ids).to_numpy()
            metrics.update({f'{method}.{group}.{k}':v for k,v in interval_metrics(y[mask],pred[mask],lo[mask],hi[mask]).items()})
        for i,row in df.iterrows():
            records.append(dict(case_id=row.case_id, split=labels[row.case_id], method=method,
                                **{k:row[k] for k in FEATURES}, y=y[i], prediction=pred[i], lower=lo[i], upper=hi[i],
                                sigma=sigma[i] if method.startswith('gp') else None))
    metrics['criterion.gp_ood_coverage_in_85_95']=bool(.85<=metrics['gp_conformal.ood.coverage']<=.95)
    out=ROOT/'data/dclink'
    write_json(out/'surrogate_metrics.json',metrics)
    write_json(out/'surrogate_evidence_metrics.json', evidence_metrics(metrics))
    pd.DataFrame(records).to_csv(out/'predictions.csv',index=False)
    metadata=dict(**fingerprint, sweep_sha256=sha(source), fitted_gp_kernel=str(gp.kernel_), analytic_coefficients=coef.tolist(),
                  mlp_iterations=int(mlp.n_iter_), mlp_reached_max_iter=bool(mlp.n_iter_>=CONFIG['mlp_max_iter']))
    write_json(out/'surrogate_metadata.json', metadata)
    if not first.exists():
        first.mkdir()
        write_json(first/'provenance.json',fingerprint)
        for name in ('surrogate_metrics.json','predictions.csv','surrogate_metadata.json'):
            shutil.copy2(out/name,first/name)
    replica = out/'surrogate_first'
    if not replica.exists():
        shutil.copytree(first, replica)
    for name in ('surrogate_metrics.json','predictions.csv','surrogate_metadata.json'):
        shutil.copy2(out/name,ROOT/'lab/cases/dclink'/name)
    print(json.dumps(metrics,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
