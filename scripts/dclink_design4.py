#!/usr/bin/env python3
"""第四轮输入设计（预注册冻结用）：5 个新随机臂种子的 LHS 点 + 复用第三轮的候选池/划分/主动臂。
只生成输入、不读取任何目标列、不运行仿真。重复运行只核对，不覆盖。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from scipy.stats import qmc
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/dclink4'; STAGE=ROOT/'lab/cases/dclink4'; R3=ROOT/'lab/cases/dclink3'
SEEDS=[20261101,20261102,20261103,20261104,20261105]
N_RANDOM=110; N_MIXED=110; NONIDEAL_BASE=20280000

def encoded(obj): return (json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def digest(obj): return hashlib.sha256(encoded(obj)).hexdigest()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def generate():
    design=[]
    for k,seed in enumerate(SEEDS,1):
        u=qmc.LatinHypercube(d=4,seed=np.random.default_rng(seed)).random(N_RANDOM)
        for x in u:
            i=len(design)
            design.append(dict(load=.30+.70*x[0],dead_time_us=.5*int(7*x[1]),bw_iac_khz=50*8**x[2],
                               aperture_delay_us=30*x[3],solver_dt_ns=50.,group=f'RS{k}',random_seed=seed,ideal=False,
                               case_id=f'dclink4_{i:03d}',index=i,nonideal_seed=NONIDEAL_BASE+i,seed=NONIDEAL_BASE+i))
    return design

def manifest(design):
    r3=json.loads((R3/'split_manifest.json').read_text())
    return dict(design_sha256=digest(design),n_design=len(design),random_seeds=SEEDS,
                mixed=dict(n=N_MIXED,index_start=len(design),case_id_format='dclink4_{index:03d}',nonideal_seed='20280000+index'),
                reused_round3=dict(split_sha256=r3['split_sha256'],groups_sha256=r3['groups_sha256'],
                                   pool_json_sha256=sha(R3/'pool.json'),design_json_sha256=sha(R3/'design.json'),
                                   sweep_base_csv_sha256=sha(R3/'sweep_base.csv'),sweep_active_csv_sha256=sha(R3/'sweep_active.csv'),
                                   active_batches_sha256={f'batch_{b}.json':sha(R3/'active'/f'batch_{b}.json') for b in range(1,6)},
                                   round2_nonideal_csv_sha256=sha(ROOT/'lab/cases/dclink2/sweep_nonideal.csv'),
                                   first_metrics_sha256=sha(R3/'first/surrogate_metrics.json')))

def freeze(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=body: raise ValueError(f'Frozen file differs: {path}')
        return
    path.write_bytes(body)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--verify',action='store_true'); a=ap.parse_args()
    d=generate(); m=manifest(d)
    targets=[(OUT/'design.json',encoded(d)),(STAGE/'design.json',encoded(d)),(STAGE/'design_manifest.json',encoded(m))]
    for p,body in targets:
        if a.verify:
            if p.read_bytes()!=body: raise ValueError(f'Verification failed: {p}')
        else: freeze(p,body)
    print(json.dumps(m,ensure_ascii=False))
if __name__=='__main__': main()
