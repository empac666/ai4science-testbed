#!/usr/bin/env python3
"""训练目标隔离；固定核与归一化常数的精确 kriging believer。"""
import csv
import json
import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
from sklearn.preprocessing import StandardScaler
from dclink_design3 import ROOT,OUT,STAGE,SOURCE,FEATURES,assign,digest,freeze
from dclink_surrogate2 import reviewer_b_features,gp_fit,CONFIG as MODEL_CONFIG
CONFIG=dict(batches=5,batch_size=22,pool_size=5000,base_count=310,
            acquisition='residual GP predictive std including WhiteKernel',
            believer='fixed kernel and original y normalization; Cholesky augmentation',
            tie_break='first remaining pool order',smoke_pool=200,smoke_s0=40,smoke_batch_size=2)

def load_training(split,completed,active_path=None,smoke=False):
    """Filter by identifiers BEFORE accessing/converting any y field."""
    allowed=split['s0'][:CONFIG['smoke_s0']] if smoke else split['s0']
    forbidden=set().union(*(set(split[k]) for k in ('calib','test','ood_corner','ood_dt3','random','supplement_corner','supplement_dt3')))
    assert not set(allowed+completed)&forbidden, 'Holdout targets forbidden in acquisition'
    assert len(set(allowed+completed))==len(allowed+completed)
    rows=[]
    for path,ids in [(SOURCE,allowed),(active_path,completed)]:
        if not ids: continue
        assert path is not None
        # First pass explicitly excludes targets. Second pass skips every forbidden
        # physical CSV record before parsing the selected target columns.
        header=pd.read_csv(path,usecols=['case_id','group','ideal'])
        mask=header.case_id.isin(ids)
        assert not set(header.loc[mask,'case_id'])&forbidden
        assert (header.loc[mask,'group']==('E-in' if path==SOURCE else 'A')).all()
        assert not header.loc[mask,'ideal'].any()
        selected=pd.read_csv(path,skiprows=(np.flatnonzero(~mask.to_numpy())+1).tolist(),
                             usecols=['case_id',*FEATURES,'y'],float_precision='round_trip')
        assert set(selected.case_id)==set(ids)
        rows.extend(selected.to_dict('records'))
    df=pd.DataFrame(rows).set_index('case_id')
    assert not df.index.duplicated().any() and set(df.index)==set(allowed+completed), 'Missing training cases'
    assert np.isfinite(df[FEATURES+['y']].to_numpy()).all()
    return df.loc[allowed+completed].reset_index()

def fit_m2(train):
    x=train[FEATURES].to_numpy(); y=train.y.to_numpy(); a=reviewer_b_features(x)
    coef=np.linalg.lstsq(a,y,rcond=MODEL_CONFIG['linear_rcond'])[0]
    scaler=StandardScaler().fit(x)
    gp=gp_fit(scaler.transform(x),y-a@coef)
    return scaler,coef,gp

def posterior_std(kernel,condition,L,candidates,y_std):
    v=solve_triangular(L,kernel(condition,candidates),lower=True,check_finite=False)
    variance=np.maximum(kernel.diag(candidates)-np.einsum('ij,ij->j',v,v),0)
    return np.maximum(np.sqrt(variance)*float(y_std),MODEL_CONFIG['normalized_sigma_floor'])

def believer(gp,z,count):
    """Pseudo-observations at the posterior mean change covariance only.

    WhiteKernel contributes to diagonals, never cross-covariances; alpha is
    included on every conditioning observation, exactly as sklearn GPR.
    """
    condition=gp.X_train_.copy(); L=gp.L_.copy(); remaining=list(range(len(z)))
    chosen=[]; stats=[]; selected_sigma=[]
    for _ in range(count):
        sigma=posterior_std(gp.kernel_,condition,L,z[remaining],gp._y_train_std)
        stats.append(np.quantile(sigma,[0,.25,.5,.75,.9,1]).tolist())
        j=int(np.argmax(sigma)); idx=remaining.pop(j); chosen.append(idx); selected_sigma.append(float(sigma[j]))
        v=solve_triangular(L,gp.kernel_(condition,z[idx:idx+1]),lower=True,check_finite=False).ravel()
        diag=float(gp.kernel_.diag(z[idx:idx+1])[0]+gp.alpha-v@v)
        if diag<=0: raise ValueError('Nonpositive believer Schur complement')
        enlarged=np.zeros((len(L)+1,len(L)+1)); enlarged[:-1,:-1]=L
        enlarged[-1,:-1]=v; enlarged[-1,-1]=np.sqrt(diag); L=enlarged
        condition=np.vstack([condition,z[idx]])
    return chosen,stats,selected_sigma

def select_batch(b,split,pool,previous,out=OUT,stage=STAGE,smoke=False):
    path=out/'active'/f'batch_{b}.json'
    allocated=[p['case_id'] for record in previous for p in record['points']]
    completed=allocated
    if allocated:
        successful=set(pd.read_csv(out/'sweep_active.csv',usecols=['case_id']).case_id)
        completed=[cid for cid in allocated if cid in successful]
    used={p['pool_id'] for record in previous for p in record['points']}
    candidates=[p for p in (pool[:CONFIG['smoke_pool']] if smoke else pool) if p['pool_id'] not in used]
    train=load_training(split,completed,out/'sweep_active.csv',smoke)
    fingerprint=dict(training_ids=train.case_id.tolist(),training_sha256=digest(train.to_dict('records')),
                     candidates_sha256=digest(candidates),batch=b,smoke=smoke,config=CONFIG)
    if path.exists():
        record=json.loads(path.read_text()); body={k:v for k,v in record.items() if k!='sha256'}
        assert record['sha256']==digest(body) and record['fingerprint']==fingerprint, 'Frozen batch mismatch'
        if stage is not None: freeze(stage/'active'/path.name,record)
        return record
    scaler,coef,gp=fit_m2(train)
    z=scaler.transform(pd.DataFrame(candidates)[FEATURES].to_numpy())
    indices,stats,sigmas=believer(gp,z,CONFIG['smoke_batch_size'] if smoke else CONFIG['batch_size'])
    start=CONFIG['base_count']+len(allocated)
    points=[assign(dict(candidates[i],group='A',batch=b),start+j) for j,i in enumerate(indices)]
    record=dict(fingerprint=fingerprint,points=points,kernel=str(gp.kernel_),kernel_theta=gp.kernel_.theta.tolist(),
                y_normalization_mean=float(gp._y_train_mean),y_normalization_std=float(gp._y_train_std),
                scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),linear_coef=coef.tolist(),
                sigma_quantile_levels=[0,.25,.5,.75,.9,1],candidate_sigma_quantiles=stats,
                selected_sigma=sigmas,training_case_ids=train.case_id.tolist())
    record['sha256']=digest(record); freeze(path,record)
    if stage is not None: freeze(stage/'active'/path.name,record)
    return record
