#!/usr/bin/env python3
"""预注册 M0–M5；只拟合第一轮分布内数据，只校准新 E-in calib。"""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[k]='1'
import json
import shutil
import sys
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel,RBF,WhiteKernel
from sklearn.neural_network import MLPRegressor
from dclink_surrogate import CONFIG as ROUND1_CONFIG, conformal_quantile, analytic_features, evidence_metrics
from dclink_split2 import verify, sha
CONFIG=dict(ROUND1_CONFIG, normalized_sigma_floor=float(np.finfo(float).eps), linear_rcond=None,
            reviewer_b_features=['intercept','t_dead*f_carrier','load','f_grid/bw_iac','4*pi*f_grid*t_ap'],
            methods={'m0':'GP + standard conformal','m1':'GP + sigma conformal',
                     'm2':'reviewer_b linear mean + residual GP + sigma conformal',
                     'm3':'reviewer_b linear + standard conformal','m4':'MLP + standard conformal',
                     'm5':'round1 researcher_a linear + standard conformal'})
METHODS=list(CONFIG['methods'])
SETS=['test','ood_dt3','ood_corner','supplement_ood']
OUT=ROOT/'data/dclink2'; STAGE=ROOT/'lab/cases/dclink2'

def write_json(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def reviewer_b_features(x):
    sys.path.insert(0,str(ROOT/'data/dclink_src/simsw'))
    from dclink_simsw.common import SimulationConfig
    cfg=SimulationConfig()
    return np.column_stack([np.ones(len(x)),x[:,1]*1e-6*cfg.f_carrier_Hz,x[:,0],
                            cfg.f_grid_Hz/(x[:,2]*1000),4*np.pi*cfg.f_grid_Hz*x[:,3]*1e-6])

def normalized_quantile(y,pred,sigma):
    return conformal_quantile(abs(y-pred)/np.maximum(sigma,CONFIG['normalized_sigma_floor']),CONFIG['alpha'])

def interval_metrics(y,pred,half):
    err=pred-y; covered=int(np.sum(abs(err)<=half))
    return dict(n=len(y),covered=covered,mae=float(np.mean(abs(err))),max_abs_error=float(np.max(abs(err))),
                bias=float(np.mean(err)),coverage=covered/len(y),mean_width=float(np.mean(2*half)))

def criteria(m):
    out={}
    test_width=m['m2.test.mean_width']
    for label,g,count in [('C1','test',62),('C2-dt3','ood_dt3',24),('C2-corner','ood_corner',24)]:
        prefix='criterion.'+label
        out[prefix+'.covered']=m[f'm2.{g}.covered']; out[prefix+'.n']=m[f'm2.{g}.n']
        out[prefix+'.required_covered']=count
        out[prefix+'.coverage_pass']=m[f'm2.{g}.covered']>=count
        out[prefix+'.mean_width']=m[f'm2.{g}.mean_width']
        if g!='test':
            out[prefix+'.width_limit']=3*test_width
            out[prefix+'.width_pass']=m[f'm2.{g}.mean_width']<=3*test_width
        out[prefix+'.pass']=out[prefix+'.coverage_pass'] and (g=='test' or out[prefix+'.width_pass'])
    out['criterion.overall']=all(out['criterion.'+c+'.pass'] for c in ('C1','C2-dt3','C2-corner'))
    return out

def load_sweep(path,design,ideal):
    df=pd.read_csv(path).sort_values('case_id').reset_index(drop=True)
    if len(df)!=210 or df.case_id.duplicated().any() or set(df.case_id)!={p['case_id'] for p in design}:
        raise ValueError('Incomplete or duplicate sweep')
    indexed=df.set_index('case_id')
    for p in design:
        r=indexed.loc[p['case_id']]
        for k in ('load','dead_time_us','bw_iac_khz','aperture_delay_us','solver_dt_ns'):
            if not np.isclose(r[k],p[k],rtol=1e-14,atol=1e-14): raise ValueError('Sweep parameters differ from design')
        if int(r.seed)!=(p['seed'] if ideal else p['nonideal_seed']) or bool(r.ideal)!=ideal:
            raise ValueError('Sweep sensor seed/mode mismatch')
        if r.group!=p['group']: raise ValueError('Sweep group mismatch')
    if not np.isfinite(df.y).all(): raise ValueError('Nonfinite targets')
    return df

def gp_fit(z,y):
    kernel=ConstantKernel(CONFIG['gp_constant'],CONFIG['gp_constant_bounds'])*RBF(CONFIG['gp_length_scales'],CONFIG['gp_length_bounds'])+WhiteKernel(CONFIG['gp_white'],CONFIG['gp_white_bounds'])
    return GaussianProcessRegressor(kernel=kernel,normalize_y=CONFIG['gp_normalize_y'],alpha=CONFIG['gp_alpha'],
          n_restarts_optimizer=CONFIG['gp_restarts'],random_state=CONFIG['seed']).fit(z,y)

def main():
    print(json.dumps(CONFIG,ensure_ascii=False),flush=True)
    if json.loads((STAGE/'config_prerun.json').read_text()) != CONFIG:
        raise ValueError('Configuration differs from frozen pre-run configuration')
    split=verify(); design=json.loads((OUT/'design.json').read_text())
    ideal=load_sweep(OUT/'sweep_ideal.csv',design,True)
    nonideal=load_sweep(OUT/'sweep_nonideal.csv',design,False)
    fingerprint=dict(config=CONFIG,split_sha256=split['split_sha256'],
                     input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [OUT/'sweep_ideal.csv',OUT/'sweep_nonideal.csv',
                         ROOT/'data/dclink/sweep.csv',OUT/'design.json',ROOT/'scripts/dclink_surrogate2.py',
                         ROOT/'scripts/dclink_surrogate.py',ROOT/'data/dclink_src/simsw/dclink_simsw/common.py']})
    first=STAGE/'first'
    names=('surrogate_metrics.json','surrogate_evidence_metrics.json','predictions.csv','surrogate_metadata.json')
    if first.exists():
        if json.loads((first/'provenance.json').read_text())!=fingerprint: raise ValueError('First run preserved: provenance changed')
        for name in names:
            shutil.copy2(first/name,OUT/name); shutil.copy2(first/name,STAGE/name)
        print('Reused frozen first run; no refitting.'); return
    old=pd.read_csv(ROOT/'data/dclink/sweep.csv').sort_values('case_id').reset_index(drop=True)
    if old.case_id.duplicated().any() or set(old.case_id)!=set(split['train']+split['supplement_ood']):
        raise ValueError('Round1 sweep incomplete')
    df=pd.concat([old,ideal],ignore_index=True)
    features=['load','dead_time_us','bw_iac_khz','aperture_delay_us']
    x=df[features].to_numpy(); y=df.y.to_numpy()
    train=df.case_id.isin(split['train']).to_numpy(); calib=df.case_id.isin(split['calib']).to_numpy()
    a=reviewer_b_features(x); b=analytic_features(x)
    ca=np.linalg.lstsq(a[train],y[train],rcond=CONFIG['linear_rcond'])[0]
    cb=np.linalg.lstsq(b[train],y[train],rcond=CONFIG['linear_rcond'])[0]
    linear=a@ca
    scale=StandardScaler().fit(x[train]); z=scale.transform(x)
    gp=gp_fit(z[train],y[train]); p0,s0=gp.predict(z,return_std=True)
    rgp=gp_fit(z[train],y[train]-linear[train]); residual,s2=rgp.predict(z,return_std=True)
    s0=np.maximum(s0,CONFIG['normalized_sigma_floor']); s2=np.maximum(s2,CONFIG['normalized_sigma_floor'])
    mlp=MLPRegressor(hidden_layer_sizes=tuple(CONFIG['mlp_hidden']),early_stopping=CONFIG['mlp_early_stopping'],
                    random_state=CONFIG['seed'],max_iter=CONFIG['mlp_max_iter'],alpha=CONFIG['mlp_alpha'],tol=CONFIG['mlp_tol'],
                    learning_rate_init=CONFIG['mlp_learning_rate'],activation=CONFIG['mlp_activation'],solver=CONFIG['mlp_solver'],
                    n_iter_no_change=CONFIG['mlp_no_change']).fit(z[train],y[train])
    preds={'m0':p0,'m1':p0,'m2':linear+residual,'m3':linear,'m4':mlp.predict(z),'m5':b@cb}
    metrics={}; records=[]; labels={i:g for g in ('train','calib',*SETS) for i in split[g]}
    for method,pred in preds.items():
        sigma=s0 if method=='m1' else s2 if method=='m2' else np.ones(len(y))
        q=normalized_quantile(y[calib],pred[calib],sigma[calib]); half=q*sigma
        metrics[f'{method}.calib.q']=q
        for group in SETS:
            mask=df.case_id.isin(split[group]).to_numpy()
            metrics.update({f'{method}.{group}.{k}':v for k,v in interval_metrics(y[mask],pred[mask],half[mask]).items()})
        for i,r in df.iterrows():
            records.append(dict(case_id=r.case_id,split=labels[r.case_id],method=method,sensor='ideal',
                y=y[i],prediction=pred[i],lower=pred[i]-half[i],upper=pred[i]+half[i],sigma=sigma[i]))
        if method=='m2':
            # Matched inputs: preserve ideal fit and calibration; replace target only.
            ni=nonideal.set_index('case_id').loc[ideal.case_id]
            indices=np.flatnonzero(df.case_id.isin(ideal.case_id))
            ny=ni.y.to_numpy()
            for group in ('calib','test','ood_dt3','ood_corner'):
                mask=ideal.case_id.isin(split[group]).to_numpy()
                ii=indices[mask]
                metrics.update({f'm2.nonideal_{group}.{k}':v for k,v in interval_metrics(ny[mask],pred[ii],half[ii]).items()})
            metrics.update({f'm2.nonideal_all.{k}':v for k,v in interval_metrics(ny,pred[indices],half[indices]).items()})
            for j,i in enumerate(indices):
                records.append(dict(case_id=df.iloc[i].case_id,split=labels[df.iloc[i].case_id],method=method,sensor='nonideal',
                    y=ny[j],prediction=pred[i],lower=pred[i]-half[i],upper=pred[i]+half[i],sigma=sigma[i]))
    delta=abs(nonideal.y.to_numpy()-ideal.y.to_numpy())
    metrics.update({'nonideal.abs_delta.'+k:float(v) for k,v in dict(mean=delta.mean(),median=np.median(delta),
                    p90=np.quantile(delta,.9),p95=np.quantile(delta,.95),max=delta.max()).items()})
    metrics['nonideal.abs_delta.n']=len(delta)
    metrics.update(criteria(metrics))
    write_json(OUT/'surrogate_metrics.json',metrics)
    write_json(OUT/'surrogate_evidence_metrics.json',evidence_metrics(metrics))
    pd.DataFrame(records).to_csv(OUT/'predictions.csv',index=False)
    metadata=dict(**fingerprint,reviewer_b_coefficients=ca.tolist(),researcher_a_coefficients=cb.tolist(),
                  gp_kernel=str(gp.kernel_),residual_gp_kernel=str(rgp.kernel_),mlp_iterations=int(mlp.n_iter_),
                  mlp_reached_max_iter=bool(mlp.n_iter_>=CONFIG['mlp_max_iter']))
    write_json(OUT/'surrogate_metadata.json',metadata)
    first.mkdir(parents=True); write_json(first/'provenance.json',fingerprint)
    for name in names:
        shutil.copy2(OUT/name,first/name); shutil.copy2(OUT/name,STAGE/name)
    print(json.dumps(metrics,ensure_ascii=False),flush=True)
if __name__=='__main__': main()
