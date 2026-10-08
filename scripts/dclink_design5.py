#!/usr/bin/env python3
"""第五轮输入设计：新留出集 T5/C5/D5 与 6 个随机臂；种子 H 来自预注册提交 SHA。只生成输入，不读目标、不仿真；重复运行只核对。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from scipy.stats import qmc
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/dclink5'; STAGE=ROOT/'lab/cases/dclink5'
PREREG_COMMIT='aec77cb7090e30a695927eae15305b2940ca1c15'
H=int(PREREG_COMMIT[:8],16); K=6; NONIDEAL_BASE=20290000
def encoded(o): return (json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def digest(o): return hashlib.sha256(encoded(o)).hexdigest()
def case(p,i,group): return dict(p,group=group,case_id=f'dclink5_{i:04d}',index=i,nonideal_seed=NONIDEAL_BASE+i,seed=NONIDEAL_BASE+i,ideal=False,solver_dt_ns=50.)
def generate():
    rng=np.random.default_rng(H); out=[]
    u=qmc.LatinHypercube(d=4,seed=rng).random(300); t=[]
    for x in u:
        p=dict(load=.30+.70*x[0],dead_time_us=.5*int(6*x[1]),bw_iac_khz=50*8**x[2],aperture_delay_us=30*x[3])
        if p['load']<=.35 and p['bw_iac_khz']<=75: continue
        t.append(p)
    assert len(t)>=60
    for p in t[:60]: out.append(case(p,len(out),'T5'))
    for x in qmc.LatinHypercube(d=4,seed=rng).random(40):
        out.append(case(dict(load=.30+.05*x[0],dead_time_us=.5*int(6*x[1]),bw_iac_khz=50*1.5**x[2],aperture_delay_us=30*x[3]),len(out),'C5'))
    for x in qmc.LatinHypercube(d=4,seed=rng).random(40):
        out.append(case(dict(load=.30+.70*x[0],dead_time_us=3.,bw_iac_khz=50*8**x[2],aperture_delay_us=30*x[3]),len(out),'D5'))
    for k in range(1,K+1):
        for x in qmc.LatinHypercube(d=4,seed=np.random.default_rng(H+k)).random(110):
            out.append(case(dict(load=.30+.70*x[0],dead_time_us=.5*int(7*x[1]),bw_iac_khz=50*8**x[2],aperture_delay_us=30*x[3],random_seed=H+k),len(out),f'R{k}'))
    assert len(out)==800
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--verify',action='store_true'); a=ap.parse_args()
    d=generate(); m=dict(prereg_commit=PREREG_COMMIT,H=H,design_sha256=digest(d),n=len(d),
                         groups={g:sum(p['group']==g for p in d) for g in dict.fromkeys(p['group'] for p in d)},
                         config_sha256=hashlib.sha256((STAGE/'config_prerun.json').read_bytes()).hexdigest())
    for p,body in [(OUT/'design.json',encoded(d)),(STAGE/'design.json',encoded(d)),(STAGE/'design_manifest.json',encoded(m))]:
        if a.verify or p.exists():
            if p.read_bytes()!=body: raise ValueError(f'Frozen file differs: {p}')
        else: p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(body)
    print(json.dumps(m,ensure_ascii=False))
if __name__=='__main__': main()
