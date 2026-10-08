#!/usr/bin/env python3
"""第五轮同步批次扫描，最多两个仿真进程；沿用第四轮会话与恢复日志。"""
from dclink_active5 import ROOT, OUT, STAGE, R3, ADAPTIVE, CONFIG_SHA, DESIGN_SHA, verify, select_batch, sha, freeze
import os
os.environ['NUMBA_CACHE_DIR']=str(ROOT/'data/numba_cache')
import argparse
import fcntl
import json
from dclink_sweep4 import Session, summarize, batch, memory_gate
from dclink_sweep3 import prepare_replay,journal_read
from dclink_active5 import digest

def require_base_complete(out,design):
    expected={p['case_id']:digest(p) for p in design}
    done=set()
    for event in journal_read(out/'progress.jsonl'):
        cid=event.get('case_id')
        if cid in expected and 'parameters_sha256' in event:
            assert event['parameters_sha256']==expected[cid], 'Base resume parameters changed'
        if cid in expected and event['event']=='result' and event['status']=='ok': done.add(cid)
    assert done==set(expected), 'Complete all 800 base cases before adaptive phase'

def execute(a,out,split):
    if not a.smoke:
        marker=json.loads((OUT/'READY_TO_RUN').read_text())
        assert marker['sha256']['lab/cases/dclink5/config_prerun.json']==CONFIG_SHA
        assert marker['sha256']['lab/cases/dclink5/design.json']==DESIGN_SHA
        for path,value in marker['sha256'].items(): assert sha(ROOT/path)==value,path
    design=json.loads((OUT/'design.json').read_text()); pool=json.loads((R3/'pool.json').read_text())
    if a.smoke: design=design[:2]; freeze(out/'design.json',design)
    elif a.phase=='adaptive': require_base_complete(out,design)
    memory_gate(); prepare_replay(out)
    session=Session(out,a.jobs,a.phase,a.smoke)
    try:
        if a.phase in ('base','all'):
            failed=batch(design,a.jobs,out,a.smoke,'sweep_base.csv',session)
            if failed: raise RuntimeError(f'Failed cases (two attempts): {failed}')
        if a.phase in ('adaptive','all'):
            arms=['A1','M1'] if a.smoke else ADAPTIVE
            previous={arm:[] for arm in arms}; points=[]
            for b in range(1,2 if a.smoke else 6):
                # All 12 acquisitions finish before ANY simulation of this batch.
                for arm in arms:
                    rec=select_batch(arm,b,split,pool,previous[arm],out,None if a.smoke else STAGE,a.smoke)
                    previous[arm].append(rec); points.extend(rec['points'])
                failed=batch(points,a.jobs,out,a.smoke,'sweep_adaptive.csv',session)
                if failed: raise RuntimeError(f'Failed cases (two attempts): {failed}')
        value=session.end(); print(json.dumps(value),flush=True)
    except BaseException:
        # Leave session running: the next Session recovers submitted/no-result cases,
        # recording interrupted_inflight exactly once using the R4 protocol.
        session.heartbeat()
        raise
    finally:
        if not a.smoke:
            for name in ('sweep_base.csv','sweep_adaptive.csv','progress.jsonl','sweep_timing.json'):
                if (out/name).exists():
                    target=STAGE/name; tmp=target.with_suffix(target.suffix+'.tmp')
                    tmp.write_bytes((out/name).read_bytes()); tmp.replace(target)

def main():
    split=verify()
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase',choices=['base','adaptive','all'],default='all')
    ap.add_argument('--jobs',type=int,default=2); ap.add_argument('--smoke',action='store_true'); a=ap.parse_args()
    if not 1<=a.jobs<=2: ap.error('jobs must be 1..2')
    out=ROOT/'data/dclink5_smoke' if a.smoke else OUT; out.mkdir(parents=True,exist_ok=True)
    with (out/'.scan.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); execute(a,out,split)
if __name__=='__main__': main()
