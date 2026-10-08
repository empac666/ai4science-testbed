#!/usr/bin/env python3
"""可恢复的非理想扫描；--smoke 完全隔离，正式执行需 READY_TO_RUN。"""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['NUMBA_CACHE_DIR']=str(ROOT/'data/numba_cache')
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
import argparse
import fcntl
import json
import time
import subprocess
from datetime import datetime,timezone
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
import numpy as np
from dclink_design3 import OUT,STAGE,generate,make_split,verify,atomic,freeze,freeze_bytes,digest
from dclink_sweep2 import run_case

def journal_read(path):
    records=[]
    if not path.exists(): return records
    # A crash may leave only the last append incomplete; discard only that tail.
    with path.open('rb+') as f:
        while True:
            offset=f.tell(); line=f.readline()
            if not line: break
            if not line.endswith(b'\n'): f.truncate(offset); break
            records.append(json.loads(line))
    return records

def append(path,record):
    with path.open('a') as f:
        f.write(json.dumps(record,allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())

def prepare_replay(out):
    src=ROOT/'data/dclink_src/fw'
    binary=out/'runtime/fw/build/dclink_replay'
    sources=[src/'src'/f'dclink_{n}.c' for n in ('crc','logger','cap_est','gate','baseline')]+[src/'tools/dclink_replay.c']
    from dclink_design3 import sha
    provenance=dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources+sorted((src/'include').glob('*.h'))},
                    flags=['-std=c99','-Wall','-Wextra','-Werror','-O2'])
    if not binary.exists():
        binary.parent.mkdir(parents=True,exist_ok=True)
        tmp=binary.with_suffix('.tmp')
        subprocess.run(['gcc','-I'+str(src/'include'),'-I'+str(src/'test'),*provenance['flags'],
                        *map(str,sources),'-lm','-o',str(tmp)],check=True)
        tmp.replace(binary)
    provenance['binary_sha256']=sha(binary)
    freeze(out/'runtime/replay_provenance.json',provenance)


def worker(p,out,smoke):
    try:
        import dclink_sweep as original
        original.EDGE=Path(out)/'runtime'
        r=run_case(p,False,out,smoke)
        if not np.isfinite(r['y']): raise ValueError('Nonfinite y')
        return dict(status='ok',result=r)
    except Exception as e: return dict(status='failed',error=f'{type(e).__name__}: {e}')

def batch(cases,jobs,out,smoke,name):
    log=out/'progress.jsonl'; history=journal_read(log)
    by_id={p['case_id']:p for p in cases}
    for r in history:
        if r['case_id'] in by_id: assert r['parameters_sha256']==digest(by_id[r['case_id']]), 'Resume parameters changed'
    done={r['case_id']:r['result'] for r in history if r['status']=='ok'}
    attempts={cid:sum(r['case_id']==cid for r in history) for cid in by_id}
    with ProcessPoolExecutor(jobs) as executor:
        pending={executor.submit(worker,p,str(out),smoke):p for p in cases if p['case_id'] not in done and attempts[p['case_id']]<2}
        while pending:
            f=next(as_completed(pending)); p=pending.pop(f); cid=p['case_id']
            result=f.result(); attempts[cid]+=1
            record=dict(result,case_id=cid,attempt=attempts[cid],parameters_sha256=digest(p),
                        recorded_at=datetime.now(timezone.utc).isoformat())
            append(log,record); print(f'{cid}: {result["status"]}, attempt {attempts[cid]}',flush=True)
            if result['status']=='ok': done[cid]=result['result']
            elif attempts[cid]<2: pending[executor.submit(worker,p,str(out),smoke)]=p
    rows=[done[p['case_id']] for p in cases if p['case_id'] in done]
    target=out/name; tmp=target.with_suffix('.csv.tmp')
    pd.DataFrame(rows,columns=None if rows else ['case_id','y']).to_csv(tmp,index=False); tmp.replace(target)
    return [p['case_id'] for p in cases if p['case_id'] not in done]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['base','active','all'],default='all')
    ap.add_argument('--jobs',type=int,default=4); ap.add_argument('--smoke',action='store_true'); a=ap.parse_args()
    if not 1<=a.jobs<=4: ap.error('jobs must be 1..4')
    out=ROOT/'data/dclink3_smoke' if a.smoke else OUT; out.mkdir(parents=True,exist_ok=True)
    with (out/'.scan.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        execute(a,out)

def execute(a,out):
    from dclink_active3 import select_batch
    from dclink_surrogate3 import verify_config
    start=time.perf_counter()
    if a.smoke:
        design,pool=generate(); split=make_split(design); design=design[:2]
        freeze(out/'design.json',design)
    else:
        split=verify(); verify_config()
        if not (OUT/'READY_TO_RUN').exists(): raise ValueError('READY_TO_RUN missing')
        design=json.loads((OUT/'design.json').read_text()); pool=json.loads((OUT/'pool.json').read_text())
    prepare_replay(out)
    failures=[]
    if a.phase in ('base','all') or a.smoke:
        failures+=batch(design,a.jobs,out,a.smoke,'sweep_base.csv')
    if a.phase in ('active','all') or a.smoke:
        previous=[]; active=[]
        for b in range(1,2 if a.smoke else 6):
            record=select_batch(b,split,pool,previous,out,None if a.smoke else STAGE,a.smoke)
            previous.append(record); active.extend(record['points'])
            failures+=batch(active,a.jobs,out,a.smoke,'sweep_active.csv')
    history=journal_read(out/'progress.jsonl')
    done={r['case_id']:r['result'] for r in history if r['status']=='ok'}
    sessions_path=out/'timing_sessions.jsonl'
    append(sessions_path,dict(wall_s=time.perf_counter()-start,phase=a.phase,jobs=a.jobs,smoke=a.smoke,
                              completed_at=datetime.now(timezone.utc).isoformat()))
    sessions=journal_read(sessions_path)
    timing=dict(total_wall_s=sum(r['wall_s'] for r in sessions),sessions=sessions,
                completed_n=len(done),failed_case_ids=sorted(set(failures)),smoke=a.smoke,
                duration_s=4 if a.smoke else 6,startup_s=1,solver_dt_ns=50,
                mean_case_s=float(np.mean([r['elapsed_s'] for r in done.values()])) if done else 0.)
    atomic(out/'sweep_timing.json',timing)
    if not a.smoke:
        for name in ('sweep_base.csv','sweep_active.csv','sweep_timing.json','progress.jsonl'):
            if (out/name).exists():
                # CSVs and timing are resumable summaries, not immutable first evaluation.
                target=STAGE/name; tmp=target.with_suffix(target.suffix+'.tmp')
                tmp.write_bytes((out/name).read_bytes()); tmp.replace(target)
    print(json.dumps(timing),flush=True)
    if a.smoke and (len(done)!=4 or failures): raise RuntimeError('Smoke incomplete')
if __name__=='__main__': main()
