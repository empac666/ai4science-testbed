#!/usr/bin/env python3
"""第二轮冻结设计；默认只供主持人启动扫描，--smoke 不接触正式目录。"""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.environ['NUMBA_CACHE_DIR'] = str(ROOT/'data/numba_cache')
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[k] = '1'
import argparse
import json
import time
import shutil
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd
from scipy.stats import qmc
SEED = 20261004

def design():
    # Independent sequential draws from one frozen generator; discrete dimension by six equal bins.
    rng = np.random.default_rng(SEED)
    groups = []
    for group, n, low, high in [('E-in',600,.30,1.),('E-dt3',30,.30,1.),('E-corner',30,.30,.35)]:
        u = qmc.LatinHypercube(4, seed=rng).random(n)
        pts = []
        for x in u:
            p = dict(load=low+(high-low)*x[0], dead_time_us=3. if group=='E-dt3' else .5*min(5,int(6*x[1])),
                     bw_iac_khz=50*(1.5 if group=='E-corner' else 8)**x[2], aperture_delay_us=30*x[3],
                     solver_dt_ns=50., group=group)
            if group=='E-in' and p['load']<=.35 and p['bw_iac_khz']<=75: continue
            pts.append(p)
        groups.extend(pts[:150] if group=='E-in' else pts)
    return [dict(p, case_id=f'dclink2_{i:03d}', index=i, seed=20261002, nonideal_seed=SEED+i,
                 design_seed=SEED) for i,p in enumerate(groups)]

def run_case(p, ideal, out, smoke=False):
    # Reuse original target, replay, filtering and precision without editing round one.
    import dclink_sweep as base
    original = base.SimulationConfig
    old_out = base.OUT
    def config(**kwargs):
        kwargs['sensor'].ideal = ideal
        if smoke:
            kwargs.update(duration_s=4, startup_s=1)
        return original(**kwargs)
    base.SimulationConfig = config
    base.OUT = Path(out)/('ideal' if ideal else 'nonideal')
    (base.OUT/'waveforms').mkdir(parents=True, exist_ok=True)
    params = dict(p, seed=p['seed'] if ideal else p['nonideal_seed'], ideal=ideal)
    try:
        return base.run_case(params)
    finally:
        base.SimulationConfig, base.OUT = original, old_out

def atomic_json(path, obj):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    tmp.replace(path)

def batch(cases, jobs, out, smoke):
    start=time.perf_counter(); started=datetime.now(timezone.utc).isoformat()
    rows={True:[], False:[]}
    with ProcessPoolExecutor(jobs) as pool:
        fs={pool.submit(run_case,p,ideal,str(out),smoke):ideal for p in cases for ideal in (True,False)}
        for f in as_completed(fs):
            ideal=fs[f]; r=f.result(); rows[ideal].append(r)
            with (out/'progress.jsonl').open('a') as h: h.write(json.dumps(r,allow_nan=False)+'\n')
            print(f"{r['case_id']} ideal={ideal} y={r['y']:.6g} ({r['elapsed_s']:.1f}s)",flush=True)
    timing=dict(started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
                total_wall_s=time.perf_counter()-start, jobs=jobs, completed_n=sum(map(len,rows.values())),
                smoke=smoke, duration_s=4 if smoke else 6, startup_s=1)
    # Publish CSVs only when both complete; atomic replace avoids partial reads.
    for ideal, rr in rows.items():
        name='sweep_ideal.csv' if ideal else 'sweep_nonideal.csv'
        df=pd.DataFrame(rr).sort_values('index')
        tmp=out/(name+'.tmp'); df.to_csv(tmp,index=False); tmp.replace(out/name)
    atomic_json(out/'sweep_timing.json',timing)
    if not smoke:
        dest=ROOT/'lab/cases/dclink2'; dest.mkdir(parents=True,exist_ok=True)
        for name in ('sweep_ideal.csv','sweep_nonideal.csv','sweep_timing.json','progress.jsonl','design.json'):
            shutil.copy2(out/name,dest/name)
    print(json.dumps(timing),flush=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--jobs',type=int,default=4); ap.add_argument('--smoke',action='store_true')
    a=ap.parse_args()
    if not 1<=a.jobs<=4: ap.error('jobs must be 1..4')
    out=ROOT/('data/dclink2_smoke' if a.smoke else 'data/dclink2'); out.mkdir(parents=True,exist_ok=True)
    if a.smoke:
        cases=design()[:2]; atomic_json(out/'design.json',cases)
    else:
        from dclink_split2 import verify
        verify()
        if not (out/'READY_TO_RUN').exists(): raise ValueError('READY_TO_RUN missing')
        if any((out/n).exists() for n in ('sweep_ideal.csv','sweep_nonideal.csv','progress.jsonl')):
            raise ValueError('Existing scan outputs: preserve them; do not silently rerun')
        cases=json.loads((out/'design.json').read_text())
    batch(cases,a.jobs,out,a.smoke)
if __name__=='__main__': main()
