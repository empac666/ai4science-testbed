#!/usr/bin/env python3
"""Reproducible switching simulation + LS replay; no external files are modified."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.environ['NUMBA_CACHE_DIR'] = str(ROOT / 'data/numba_cache')
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd
from scipy.stats import qmc
EDGE = ROOT / 'data/dclink_src'  # dclink-edge-ai@be9a0f4 git archive 快照（由 make dclink-check 生成并编译 fw）
sys.path.insert(0, str(EDGE / 'simsw'))
sys.path.insert(0, str(EDGE / 'replay'))
from dclink_simsw.common import SimulationConfig, CapacitorModel, SensorConfig
from dclink_simsw.model import simulate_chb_cell_sw
from run_replay import run_cli, c_ref
OUT = ROOT / 'data/dclink'
SEED = 20261002

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def design(n):
    u = qmc.LatinHypercube(4, seed=SEED).random(n)
    return [dict(case_id=f'dclink_{i:03d}', load=0.3+0.7*x[0], dead_time_us=0.5*min(6,int(7*x[1])),
                 bw_iac_khz=50*8**x[2], aperture_delay_us=30*x[3], seed=SEED,
                 solver_dt_ns=50.0) for i,x in enumerate(u)]

def run_case(p):
    import resource
    start = time.perf_counter()
    case_hash = digest(p)
    cfg = SimulationConfig(load_ratio=p['load'], duration_s=6, startup_s=1,
        dead_time_s=p['dead_time_us']*1e-6, solver_dt_s=p['solver_dt_ns']*1e-9,
        capacitor=CapacitorModel(cap_type='film', C_ratio_initial=1.0),
        sensor=SensorConfig(bw_iac_Hz=p['bw_iac_khz']*1000,
                            aperture_delay_s=p['aperture_delay_us']*1e-6), seed=p['seed'])
    period_steps = round(1/cfg.f_carrier_Hz/cfg.solver_dt_s)
    sample_step = period_steps//2 + round(cfg.sensor.aperture_delay_s/cfg.solver_dt_s)
    if not 0 <= sample_step < period_steps:
        raise ValueError('aperture crosses carrier period')
    df, meta = simulate_chb_cell_sw(cfg)
    prefix = OUT/'waveforms'/p['case_id']
    df.to_csv(prefix.with_suffix('.csv'), index=False, float_format='%.6f', na_rep='nan')
    meta = {k: None if isinstance(v,float) and not np.isfinite(v) else v for k,v in meta.items()}
    prefix.with_suffix('.json').write_text(json.dumps(meta, allow_nan=False, indent=2))
    windows = run_cli(EDGE/'fw/build/dclink_replay', prefix.with_suffix('.csv'), meta, ['--method','ls'])
    windows.to_csv(prefix.with_name(prefix.name+'_windows.csv'), index=False)
    w = windows.iloc[1:]
    v = w[w.gate_code == 0]
    if len(v) == 0:
        raise ValueError(f"{p['case_id']}: no VALID windows")
    cref = c_ref(meta, df.t_cap.mean())
    return dict(**p, case_hash=case_hash, y=float(((v.C_comp/cref-1)*100).mean()),
        esr_ratio=float(v.ESR_est.median()/meta['ESR_true_ohm']), valid_windows=len(v),
        gate_codes=','.join(str(int(g)) for g in sorted(w.gate_code.unique())),
        c_ref_F=cref, elapsed_s=time.perf_counter()-start,
        peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)

def batch(cases, jobs):
    rows=[]
    with ProcessPoolExecutor(jobs) as pool:
        fs=[pool.submit(run_case,p) for p in cases]
        for f in as_completed(fs):
            r=f.result(); rows.append(r)
            with open(OUT/'progress.jsonl','a') as fh: fh.write(json.dumps(r)+'\n')
            print(f"{r['case_id']} {r['elapsed_s']:.2f}s y={r['y']:.5f}",flush=True)
    return pd.DataFrame(rows).sort_values('case_id')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--jobs',type=int,default=4)
    ap.add_argument('--n',type=int,default=240); ap.add_argument('--pilot-only',action='store_true')
    ap.add_argument('--with-pilot',action='store_true',help='先跑 8 例试点并按预算自动定 n（默认关闭：n 固定）')
    ap.add_argument('--convergence',action='store_true'); a=ap.parse_args()
    if not 1<=a.jobs<=4: ap.error('jobs must be 1..4 (共用机器)')
    OUT.mkdir(parents=True,exist_ok=True); (OUT/'waveforms').mkdir(exist_ok=True)
    if a.convergence:
        pts=[(.3,3,50,0), (1,3,400,30), (.3,0,75,15), (1,0,50,30), (.65,1.5,150,15)]
        cases=[dict(case_id=f'conv_{i}_{dt}',load=l,dead_time_us=d,bw_iac_khz=b,
                    aperture_delay_us=t,solver_dt_ns=dt,seed=SEED)
               for i,(l,d,b,t) in enumerate(pts) for dt in (50,25)]
        start=time.perf_counter(); r=batch(cases,a.jobs); r.to_csv(OUT/'convergence.csv',index=False)
        (OUT/'convergence_timing.json').write_text(json.dumps({'wall_s':time.perf_counter()-start}))
        return
    started=datetime.now(timezone.utc).isoformat(); start=time.perf_counter()
    pilot_wall=None; estimated_per_case=None; n=a.n
    if a.with_pilot or a.pilot_only:
        pilot=design(8)
        for i,p in enumerate(pilot): p['case_id']=f'pilot_{i:03d}'
        r=batch(pilot,a.jobs); r.to_csv(OUT/'pilot.csv',index=False)
        pilot_wall=time.perf_counter()-start
        # Conservative throughput estimate including cold compilation and replay.
        estimated_per_case=max(pilot_wall/8, float(r.elapsed_s.mean())/a.jobs)
        n=min(a.n, max(28,int((1500-pilot_wall)*0.90/estimated_per_case)))
    plan=dict(seed=SEED,edge_git_sha='be9a0f4',jobs=a.jobs,pilot_wall_s=pilot_wall,
              estimated_per_case_s=estimated_per_case,requested_n=a.n,selected_n=n,
              started_at=started,design='scrambled Latin hypercube; uniform dead-time categories')
    (OUT/'sweep_plan.json').write_text(json.dumps(plan,indent=2))
    print(json.dumps(plan),flush=True)
    if a.pilot_only: return
    cases=design(n); (OUT/'design.json').write_text(json.dumps(cases,indent=2))
    r=batch(cases,a.jobs); r.to_csv(OUT/'sweep.csv',index=False)
    r.to_csv(ROOT/'lab/cases/dclink/sweep_summary.csv',index=False,float_format='%.10g')
    plan.update(total_wall_s=time.perf_counter()-start, completed_n=len(r),
                peak_workers_rss_mb=float(r.peak_rss_mb.max())*a.jobs,
                mean_case_s=float(r.elapsed_s.mean()))
    (OUT/'sweep_timing.json').write_text(json.dumps(plan,indent=2))
    print(json.dumps(plan),flush=True)
if __name__=='__main__': main()
