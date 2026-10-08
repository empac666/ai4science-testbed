#!/usr/bin/env python3
"""第四轮冻结守卫与仅访问 S0/M 目标的饱和折扣采集。"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import json
import subprocess
import sys
import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
from dclink_design4 import ROOT,OUT,STAGE,R3
from dclink_design3 import SOURCE,FEATURES,sha,digest,freeze,freeze_bytes,encoded
from dclink_active3 import fit_m2,posterior_std
from dclink_surrogate2 import CONFIG as MODEL_CONFIG
CONFIG_SHA='da1cdf3cc9696ba7f870446d63cd21a1b2f28e8d27187dfa0480d7f5219efbd5'
CONFIG=json.loads((STAGE/'config_prerun.json').read_text())
LEVELS=[0,.25,.5,.75,.9,1]

def verify():
    subprocess.run([sys.executable,str(ROOT/'scripts/dclink_design4.py'),'--verify'],check=True,capture_output=True)
    assert sha(STAGE/'config_prerun.json')==CONFIG_SHA, 'Frozen configuration hash changed'
    assert sha(STAGE/'design.json')=='7cfdc9423eb84d9436c1966335e3938fe98a003557587eb264f9f9dbed5be437'
    assert sha(STAGE/'design_manifest.json')=='20539eb0a312faa3b376a45ef4249f307300d50affe275e234483d9dffd1acc1'
    assert CONFIG['model']==MODEL_CONFIG==json.loads((R3/'config_prerun.json').read_text())['model']
    split=json.loads((ROOT/'data/dclink3/split.json').read_text())
    reused=json.loads((STAGE/'design_manifest.json').read_text())['reused_round3']
    assert digest(split)==reused['split_sha256']
    assert {k:digest(v) for k,v in split.items() if isinstance(v,list)}==reused['groups_sha256']
    return split

def assign(p,index):
    return dict(p,group='M',case_id=f'dclink4_{index:03d}',index=index,
                nonideal_seed=20280000+index,seed=20280000+index,ideal=False)

def load_training(split,completed,mixed_path=None,smoke=False):
    allowed=split['s0'][:40] if smoke else split['s0']
    forbidden=set().union(*(set(v) for k,v in split.items() if isinstance(v,list) and k!='s0'))
    forbidden.update(f'dclink4_{i:03d}' for i in range(550))
    forbidden.update(f'dclink3_{i:03d}' for i in range(420))
    assert not set(allowed+completed)&forbidden, 'Holdout targets forbidden in acquisition'
    assert all(cid.startswith('dclink4_') and 550<=int(cid.rsplit('_', 1)[1])<=659 for cid in completed)
    assert len(set(allowed+completed))==len(allowed+completed)
    rows=[]
    for path,ids,group in [(SOURCE,allowed,'E-in'),(mixed_path,completed,'M')]:
        if not ids: continue
        assert path is not None
        header=pd.read_csv(path,usecols=['case_id','group','ideal'])
        mask=header.case_id.isin(ids)
        assert (header.loc[mask,'group']==group).all() and not header.loc[mask,'ideal'].any()
        selected=pd.read_csv(path,skiprows=(np.flatnonzero(~mask.to_numpy())+1).tolist(),
                             usecols=['case_id',*FEATURES,'y'],float_precision='round_trip')
        assert set(selected.case_id)==set(ids)
        rows.extend(selected.to_dict('records'))
    frame=pd.DataFrame(rows).set_index('case_id')
    assert not frame.index.duplicated().any() and set(frame.index)==set(allowed+completed)
    assert np.isfinite(frame[FEATURES+['y']].to_numpy()).all()
    return frame.loc[allowed+completed].reset_index()

def mixed_believer(gp,z,categories,count,previous=()):
    categories=np.asarray(categories); counts={c:sum(float(v)==c for v in previous) for c in np.arange(0,3.5,.5)}
    assert set(categories)<=set(counts)
    condition=gp.X_train_.copy(); L=gp.L_.copy(); remaining=list(range(len(z)))
    chosen=[]; steps=[]
    for _ in range(count):
        sigma=posterior_std(gp.kernel_,condition,L,z[remaining],gp._y_train_std)
        ac=np.array([counts[categories[i]] for i in remaining]); scores=sigma/np.sqrt(1+ac)
        j=int(np.argmax(scores)); idx=remaining.pop(j)
        steps.append(dict(pool_index=idx,dead_time_us=float(categories[idx]),a_c=int(ac[j]),
                          counts_before={str(c):int(n) for c,n in counts.items()},
                          sigma=float(sigma[j]),score=float(scores[j]),
                          sigma_quantiles=np.quantile(sigma,LEVELS).tolist(),score_quantiles=np.quantile(scores,LEVELS).tolist()))
        chosen.append(idx); counts[categories[idx]]+=1
        v=solve_triangular(L,gp.kernel_(condition,z[idx:idx+1]),lower=True,check_finite=False).ravel()
        diagonal=float(gp.kernel_.diag(z[idx:idx+1])[0]+gp.alpha-v@v)
        if diagonal<=0: raise ValueError('Nonpositive believer Schur complement')
        enlarged=np.zeros((len(L)+1,len(L)+1)); enlarged[:-1,:-1]=L
        enlarged[-1,:-1]=v; enlarged[-1,-1]=np.sqrt(diagonal); L=enlarged
        condition=np.vstack([condition,z[idx]])
    return chosen,steps

def select_batch(b,split,pool,previous,out=OUT,stage=STAGE,smoke=False):
    allocated=[p for record in previous for p in record['points']]
    assert b==len(previous)+1
    used={p['pool_id'] for p in allocated}
    successful=set(pd.read_csv(out/'sweep_mixed.csv',usecols=['case_id']).case_id) if allocated else set()
    completed=[p['case_id'] for p in allocated if p['case_id'] in successful]
    candidates=[p for p in (pool[:200] if smoke else pool) if p['pool_id'] not in used]
    train=load_training(split,completed,out/'sweep_mixed.csv',smoke)
    fingerprint=dict(training_ids=train.case_id.tolist(),training_sha256=digest(train.to_dict('records')),
                     candidates_sha256=digest(candidates),previous_sha256=digest(previous),batch=b,smoke=smoke,config_sha256=CONFIG_SHA,
                     code_sha256={name:sha(ROOT/'scripts'/name) for name in ('dclink_active4.py','dclink_active3.py','dclink_surrogate2.py')})
    path=out/'mixed'/f'batch_{b}.json'
    if path.exists():
        record=json.loads(path.read_text())
        assert record['sha256']==digest({k:v for k,v in record.items() if k!='sha256'}) and record['fingerprint']==fingerprint
    else:
        scaler,coef,gp=fit_m2(train)
        z=scaler.transform(pd.DataFrame(candidates)[FEATURES].to_numpy())
        indices,steps=mixed_believer(gp,z,[p['dead_time_us'] for p in candidates],2 if smoke else 22,
                                    [p['dead_time_us'] for p in allocated])
        points=[assign(dict(candidates[i],batch=b),550+len(allocated)+j) for j,i in enumerate(indices)]
        record=dict(fingerprint=fingerprint,points=points,steps=steps,quantile_levels=LEVELS,
                    kernel=str(gp.kernel_),kernel_theta=gp.kernel_.theta.tolist(),
                    y_normalization_mean=float(gp._y_train_mean),y_normalization_std=float(gp._y_train_std),
                    scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),linear_coef=coef.tolist())
        record['sha256']=digest(record); freeze(path,record)
    if stage is not None: freeze(stage/'mixed'/path.name,record)
    return record

if __name__=='__main__':
    verify()
    print('第四轮冻结核对通过；采集由 dclink_sweep4.py 按批调用。')
