#!/usr/bin/env python3
"""第三轮输入设计与不可覆盖的冻结清单；不读取目标列。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[k]='1'
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import qmc
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/dclink3'
STAGE=ROOT/'lab/cases/dclink3'
SOURCE=ROOT/'lab/cases/dclink2/sweep_nonideal.csv'
FEATURES=['load','dead_time_us','bw_iac_khz','aperture_delay_us']

def encoded(obj): return (json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def digest(obj): return hashlib.sha256(encoded(obj)).hexdigest()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def freeze_bytes(path,body):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=body: raise ValueError(f'Frozen file differs: {path}')
        return
    # Atomic publish, never replace an existing file (also safe against competing writers).
    tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    with tmp.open('wb') as f: f.write(body); f.flush(); os.fsync(f.fileno())
    try: os.link(tmp,path)
    finally: tmp.unlink()
def freeze(path,obj): freeze_bytes(path,encoded(obj))
def atomic(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('wb') as f: f.write(encoded(obj)); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)

def generate():
    rng=np.random.default_rng(20261010); groups=[]
    for group,n in [('E-in',600),('E-corner',40),('E-dt3',40),('R',110),('P',5000)]:
        u=qmc.LatinHypercube(d=4,seed=rng).random(n); pts=[]
        for x in u:
            p=dict(load=.30+(.05 if group=='E-corner' else .70)*x[0],
                   dead_time_us=3. if group=='E-dt3' else .5*int((7 if group in ('R','P') else 6)*x[1]),
                   bw_iac_khz=50*(1.5 if group=='E-corner' else 8)**x[2],
                   aperture_delay_us=30*x[3],solver_dt_ns=50.,group=group,ideal=False)
            if group=='E-in' and ((p['load']<=.35 and p['bw_iac_khz']<=75) or p['dead_time_us']==3): continue
            pts.append(p)
        if group=='P': pool=[dict(p,pool_id=f'pool_{i:04d}') for i,p in enumerate(pts)]
        else: groups.extend(pts[:120] if group=='E-in' else pts)
    design=[assign(p,i) for i,p in enumerate(groups)]
    return design,pool

def assign(p,index):
    return dict(p,case_id=f'dclink3_{index:03d}',index=index,nonideal_seed=20270000+index,
                seed=20270000+index,design_seed=20261010,ideal=False)

def make_split(design):
    old=pd.read_csv(SOURCE,usecols=['case_id','group'])  # no target column is loaded
    s0=old.loc[old.group=='E-in','case_id'].tolist()
    supp={g:old.loc[old.group==g,'case_id'].tolist() for g in ('E-corner','E-dt3')}
    assert len(s0)==150 and all(len(v)==30 for v in supp.values())
    ids=[p['case_id'] for p in design if p['group']=='E-in']
    ids=np.asarray(ids)[np.random.default_rng(20261011).permutation(120)].tolist()
    return dict(seed=20261011,s0=s0,calib=ids[:60],test=ids[60:],
                ood_corner=[p['case_id'] for p in design if p['group']=='E-corner'],
                ood_dt3=[p['case_id'] for p in design if p['group']=='E-dt3'],
                random=[p['case_id'] for p in design if p['group']=='R'],
                supplement_corner=supp['E-corner'],supplement_dt3=supp['E-dt3'])

def artifacts():
    design,pool=generate(); split=make_split(design)
    manifest=dict(files_sha256={n:digest(v) for n,v in [('design.json',design),('pool.json',pool),('split.json',split)]},
                  split_sha256=digest(split),groups_sha256={k:digest(v) for k,v in split.items() if isinstance(v,list)},
                  source_ids_sha256=digest(pd.read_csv(SOURCE,usecols=['case_id','group']).to_dict('records')))
    return design,pool,split,manifest

def verify():
    design,pool,split,manifest=artifacts()
    for path,obj in [(OUT/'design.json',design),(OUT/'pool.json',pool),(OUT/'split.json',split),
                     (STAGE/'design.json',design),(STAGE/'pool.json',pool),(STAGE/'split_manifest.json',manifest)]:
        if path.read_bytes()!=encoded(obj): raise ValueError(f'Frozen design verification failed: {path}')
    return split

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--verify',action='store_true'); a=ap.parse_args()
    if not a.verify:
        d,p,s,m=artifacts()
        for path,obj in [(OUT/'design.json',d),(OUT/'pool.json',p),(OUT/'split.json',s),
                         (STAGE/'design.json',d),(STAGE/'pool.json',p),(STAGE/'split_manifest.json',m)]: freeze(path,obj)
    verify(); print(json.dumps(json.loads((STAGE/'split_manifest.json').read_text()),ensure_ascii=False))
if __name__=='__main__': main()
