#!/usr/bin/env python3
"""有提交日志、会话恢复和有界在途队列的第四轮扫描。"""
from dclink_active4 import ROOT,OUT,STAGE,R3,verify,CONFIG_SHA,select_batch,digest,freeze,sha
import os
os.environ['NUMBA_CACHE_DIR']=str(ROOT/'data/numba_cache')
import argparse
import fcntl
import json
import time
import uuid
import subprocess
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import pandas as pd
from dclink_design3 import atomic,freeze_bytes
from dclink_sweep3 import journal_read,append,prepare_replay,worker

def summarize(events):
    sessions={}; done={}; failures={}; inflight=0
    for r in events:
        sid=r['session']; kind=r['event']
        if kind=='start': sessions[sid]=dict(r,status='running',wall_s=0.)
        elif kind in ('heartbeat','end','interrupted'):
            sessions[sid]['wall_s']=r['wall_s']
            if kind!='heartbeat': sessions[sid]['status']=kind
        elif kind=='interrupted_inflight': inflight+=1
        elif kind=='result':
            if r['status']=='ok': done[r['case_id']]=r['result']; failures.pop(r['case_id'],None)
            else: failures[r['case_id']]=r['attempt']
    return dict(sessions=list(sessions.values()),total_wall_s=sum(s['wall_s'] for s in sessions.values()),
                interrupted_inflight_n=inflight,completed_n=len(done),
                failed_case_ids=sorted(k for k,v in failures.items() if v>=2),
                mean_case_s=float(np.mean([r['elapsed_s'] for r in done.values()])) if done else 0.)

class Session:
    def __init__(self,out,jobs,phase,smoke):
        self.out=out; self.path=out/'progress.jsonl'; self.id=uuid.uuid4().hex; self.started=time.perf_counter()
        journal_read(self.path)  # Repair an incomplete trailing append before writing start.
        self.write('start',jobs=jobs,phase=phase,smoke=smoke,started_at=time.time())
        history=journal_read(self.path)
        for s in summarize(history)['sessions']:
            if s['session']==self.id or s['status']!='running': continue
            sid=s['session']; pending={}
            for r in history:
                if r['session']!=sid: continue
                if r['event']=='submitted': pending[r['case_id']]=r
                elif r['event']=='result': pending.pop(r['case_id'],None)
            recovered={r['case_id'] for r in history if r['session']==sid and r['event']=='interrupted_inflight'}
            for cid,r in pending.items():
                if cid in recovered: continue
                append(self.path,dict(event='interrupted_inflight',session=sid,case_id=cid,
                                      attempt=r['attempt'],parameters_sha256=r['parameters_sha256']))
            append(self.path,dict(event='interrupted',session=sid,wall_s=s['wall_s']))
        self.summary()
    def write(self,event,**kw): append(self.path,dict(event=event,session=self.id,**kw))
    def summary(self):
        value=summarize(journal_read(self.path)); atomic(self.out/'sweep_timing.json',value); return value
    def heartbeat(self): self.write('heartbeat',wall_s=time.perf_counter()-self.started); self.summary()
    def end(self): self.write('end',wall_s=time.perf_counter()-self.started); return self.summary()

def batch(cases,jobs,out,smoke,name,session):
    history=journal_read(session.path); by_id={p['case_id']:p for p in cases}
    for r in history:
        if r.get('case_id') in by_id and 'parameters_sha256' in r:
            assert r['parameters_sha256']==digest(by_id[r['case_id']]), 'Resume parameters changed'
    results=[r for r in history if r['event']=='result']
    done={r['case_id']:r['result'] for r in results if r['status']=='ok'}
    attempts={cid:sum(r['case_id']==cid for r in results) for cid in by_id}
    queue=[p for p in cases if p['case_id'] not in done and attempts[p['case_id']]<2]
    with ProcessPoolExecutor(jobs) as executor:
        pending={}
        def submit(p):
            cid=p['case_id']; session.write('submitted',case_id=cid,attempt=attempts[cid]+1,parameters_sha256=digest(p))
            pending[executor.submit(worker,p,str(out),smoke)]=p
        while queue or pending:
            while queue and len(pending)<jobs: submit(queue.pop(0))
            f=next(as_completed(pending)); p=pending.pop(f); cid=p['case_id']
            result=f.result(); attempts[cid]+=1
            session.write('result',case_id=cid,attempt=attempts[cid],parameters_sha256=digest(p),**result)
            session.heartbeat()
            print(f'{cid}: {result["status"]}, attempt {attempts[cid]}',flush=True)
            if result['status']=='ok': done[cid]=result['result']
            elif attempts[cid]<2: queue.insert(0,p)
    rows=[done[p['case_id']] for p in cases if p['case_id'] in done]
    target=out/name; tmp=target.with_suffix('.csv.tmp')
    pd.DataFrame(rows,columns=None if rows else ['case_id','y']).to_csv(tmp,index=False); tmp.replace(target)
    return [p['case_id'] for p in cases if p['case_id'] not in done]

def memory_gate():
    while True:
        result=subprocess.run(['free','-g'],text=True,capture_output=True,check=True)
        print(result.stdout,flush=True)
        mem=next(line.split() for line in result.stdout.splitlines() if line.startswith('Mem:'))
        if int(mem[-1])>=4: return
        print('可用内存不足 4 GB，等待 30 秒。',flush=True); time.sleep(30)

def execute(a,out,split):
    session=Session(out,a.jobs,a.phase,a.smoke)
    if not a.smoke:
        marker=json.loads((OUT/'READY_TO_RUN').read_text())
        for path,value in marker['sha256'].items(): assert sha(ROOT/path)==value
        assert marker['sha256']['lab/cases/dclink4/config_prerun.json']==CONFIG_SHA
    design=json.loads((OUT/'design.json').read_text()); pool=json.loads((R3/'pool.json').read_text())
    if a.smoke: design=design[:2]; freeze(out/'design.json',design)
    memory_gate(); prepare_replay(out); failures=[]
    if a.phase in ('random','all'):
        failures+=batch(design,a.jobs,out,a.smoke,'sweep_random.csv',session)
    if a.phase in ('mixed','all'):
        previous=[]; points=[]
        for b in range(1,2 if a.smoke else 6):
            record=select_batch(b,split,pool,previous,out,None if a.smoke else STAGE,a.smoke)
            previous.append(record); points.extend(record['points'])
            failures+=batch(points,a.jobs,out,a.smoke,'sweep_mixed.csv',session)
    value=session.end()
    print(json.dumps(value),flush=True)
    if failures: raise RuntimeError(f'Failed cases: {sorted(set(failures))}')

def main():
    split=verify()
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['random','mixed','all'],default='all')
    ap.add_argument('--jobs',type=int,default=2); ap.add_argument('--smoke',action='store_true'); a=ap.parse_args()
    if not 1<=a.jobs<=2: ap.error('jobs must be 1..2')
    out=ROOT/'data/dclink4_smoke' if a.smoke else OUT; out.mkdir(parents=True,exist_ok=True)
    with (out/'.scan.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); execute(a,out,split)
if __name__=='__main__': main()
