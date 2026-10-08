#!/usr/bin/env python3
"""第五轮冻结守卫与严格逐臂目标隔离；采集数学直接复用第三、四轮。"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import json
import subprocess
import sys
import numpy as np
import pandas as pd
from dclink_design5 import ROOT, OUT, STAGE, case
from dclink_design3 import SOURCE, FEATURES, sha, digest, freeze, freeze_bytes, encoded
from dclink_active3 import fit_m2, believer, posterior_std
from dclink_active4 import mixed_believer, LEVELS
from dclink_surrogate2 import CONFIG as MODEL_CONFIG
R3=ROOT/'lab/cases/dclink3'
CONFIG_SHA='040fb2881a8f80e9f262433f5deec62d6b8b4f529ac34bee89c209b1aa5b4a8d'
DESIGN_SHA='8f1496ba6e5b4c27d50582f55fe1fa0fc8d1682a8e7f87ae1f56d589ec6ca3fb'
CONFIG=json.loads((STAGE/'config_prerun.json').read_text())
ADAPTIVE=[f'{method}{k}' for k in range(1,7) for method in ('A','M')]

def verify():
    subprocess.run([sys.executable,str(ROOT/'scripts/dclink_design5.py'),'--verify'],check=True,capture_output=True)
    assert sha(STAGE/'config_prerun.json')==CONFIG_SHA
    assert sha(STAGE/'design.json')==sha(OUT/'design.json')==DESIGN_SHA
    assert CONFIG==json.loads((STAGE/'config_prerun.json').read_text())
    for path,value in CONFIG['reused_sha256'].items(): assert sha(ROOT/path)==value,path
    assert CONFIG['model']==MODEL_CONFIG==json.loads((R3/'config_prerun.json').read_text())['model']
    return json.loads((ROOT/'data/dclink3/split.json').read_text())

def arm_start(arm):
    assert arm in ADAPTIVE, 'Unknown adaptive arm'
    return (800 if arm[0]=='A' else 910)+220*(int(arm[1:])-1)

def assign(p,arm,j):
    assert 0<=j<110
    return case(p,arm_start(arm)+j,arm)

def load_training(split,arm,completed,adaptive_path=None,smoke=False):
    start=arm_start(arm)
    own={f'dclink5_{i:04d}' for i in range(start,start+110)}
    allowed=split['s0'][:40] if smoke else split['s0']
    forbidden=set().union(*(set(v) for k,v in split.items() if isinstance(v,list) and k!='s0'))
    assert set(completed)<=own, 'Cross-arm or holdout target forbidden'
    assert not set(allowed+completed)&forbidden
    assert not any(cid.startswith(('dclink3_','dclink4_','dclink5_')) for cid in allowed)
    assert len(set(allowed+completed))==len(allowed+completed)
    rows=[]
    for path,ids,group in [(SOURCE,allowed,'E-in'),(adaptive_path,completed,arm)]:
        if not ids: continue
        assert path is not None
        # Read identifier columns first; never parse y outside this arm's allowlist.
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

def select_batch(arm,b,split,pool,previous,out=OUT,stage=STAGE,smoke=False):
    assert b==len(previous)+1 and 1<=b<=5
    allocated=[p for record in previous for p in record['points']]
    assert all(p['group']==arm for p in allocated)
    used={p['pool_id'] for p in allocated}
    assert len(used)==len(allocated)
    completed=[p['case_id'] for p in allocated]
    if completed:
        successful=set(pd.read_csv(out/'sweep_adaptive.csv',usecols=['case_id']).case_id)
        assert set(completed)<=successful, 'Previous batch incomplete; stop before acquisition'
    candidates=[p for p in (pool[:200] if smoke else pool) if p['pool_id'] not in used]
    train=load_training(split,arm,completed,out/'sweep_adaptive.csv',smoke)
    fingerprint=dict(arm=arm,batch=b,smoke=smoke,training_ids=train.case_id.tolist(),
                     training_sha256=digest(train.to_dict('records')),candidates_sha256=digest(candidates),
                     previous_sha256=digest(previous),config_sha256=CONFIG_SHA,
                     code_sha256={n:sha(ROOT/'scripts'/n) for n in ('dclink_active5.py','dclink_active3.py','dclink_active4.py','dclink_surrogate2.py')})
    path=out/'adaptive'/arm/f'batch_{b}.json'
    if path.exists():
        record=json.loads(path.read_text())
        assert record['sha256']==digest({k:v for k,v in record.items() if k!='sha256'})
        assert record['fingerprint']==fingerprint, 'Frozen acquisition inputs changed'
    else:
        scaler,coef,gp=fit_m2(train)
        z=scaler.transform(pd.DataFrame(candidates)[FEATURES].to_numpy()); count=2 if smoke else 22
        if arm[0]=='M':
            indices,steps=mixed_believer(gp,z,[p['dead_time_us'] for p in candidates],count,
                                        [p['dead_time_us'] for p in allocated])
        else:
            indices,stats,sigmas=believer(gp,z,count)
            steps=[dict(pool_index=i,sigma=s,score=s,sigma_quantiles=q,score_quantiles=q)
                   for i,q,s in zip(indices,stats,sigmas)]
        points=[assign(dict(candidates[i],batch=b),arm,len(allocated)+j) for j,i in enumerate(indices)]
        record=dict(fingerprint=fingerprint,points=points,steps=steps,quantile_levels=LEVELS,
                    kernel=str(gp.kernel_),kernel_theta=gp.kernel_.theta.tolist(),
                    y_normalization_mean=float(gp._y_train_mean),y_normalization_std=float(gp._y_train_std),
                    scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),linear_coef=coef.tolist())
        record['sha256']=digest(record); freeze(path,record)
    if stage is not None: freeze(stage/'adaptive'/arm/path.name,record)
    return record

if __name__=='__main__':
    verify(); print('第五轮冻结核对通过；采集由扫描入口按批调用。')
