"""Background dispatcher/watchdog outside worker sessions; at most two heavy jobs."""
from magnet9_common import *
import argparse
import signal
import sys
import time

STATUS=Path('./ai4s_r9_status.md')


def available():
    for line in (Path(os.sep) / 'proc' / 'meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
    raise RuntimeError('MemAvailable missing')


def paused_state(paused,memory):
    return memory<=4.3*2**30 if paused else memory<3.8*2**30


def group_signal(p,sig):
    if p.poll() is None:
        try:os.killpg(p.pid,sig)
        except ProcessLookupError:pass


def dispatch(commands,logdir,tag):
    """Poll every 5 seconds, including after tasks finish; 900 s low-memory stop."""
    todo=list(commands);running=[];paused=False;low=None;peak={};minimum=available()
    logdir.mkdir(parents=True,exist_ok=True)
    log=lambda msg:append(logdir/'watchdog.log',f'{tag} {msg}')
    try:
        while todo or running:
            memory=available();minimum=min(minimum,memory);state=paused_state(paused,memory)
            if state!=paused:
                paused=state
                for p,f,key in running:group_signal(p,signal.SIGSTOP if paused else signal.SIGCONT)
                log(f'{"PAUSED" if paused else "RESUMED"} MemAvailable={memory/2**30:.6f} GiB')
            low=(low or time.monotonic()) if paused else None
            if low and time.monotonic()-low>=900:raise RuntimeError('Persistent low memory: infrastructure stop; same-state resume required')
            for p,f,key in list(running):
                if p.poll() is not None:
                    f.close();running.remove((p,f,key));log(f'END {key} exit={p.returncode}')
                    if p.returncode:raise RuntimeError(f'Worker failed: {key} exit={p.returncode}; no replacement allowed')
                else:
                    status=(Path(os.sep) / 'proc' / str(p.pid) / 'status')
                    if status.exists():
                        for line in status.read_text().splitlines():
                            if line.startswith('VmRSS:'):peak[key]=max(peak.get(key,0),int(line.split()[1])*1024)
            while todo and len(running)<2 and not paused:
                if available()<3.8*2**30:break
                key,cmd=todo.pop(0);f=(logdir/f'{tag}_{key}.log').open('a')
                env=dict(os.environ,**{k:'1' for k in THREADS},PYTHONUNBUFFERED='1')
                p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=f,stderr=f,start_new_session=True)
                running.append((p,f,key));log(f'START {key} pid={p.pid}')
            if todo or running:time.sleep(5)
    finally:
        for p,f,key in running:group_signal(p,signal.SIGCONT);group_signal(p,signal.SIGTERM)
        for p,f,key in running:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:group_signal(p,signal.SIGKILL);p.wait()
            f.close()
        write_json(logdir/f'{tag}_resources.json',dict(peak_rss_bytes=peak,min_MemAvailable_bytes=minimum,
            pause_below_GiB=3.8,resume_above_GiB=4.3,poll_seconds=5,max_heavy_jobs=2,threads_per_job=1))


def commit(paths,message):
    subprocess.run(['git','add','--',*map(str,paths)],cwd=ROOT,check=True)
    subprocess.run(['git','commit','-m',message],cwd=ROOT,check=True)


def run(smoke=False):
    c=config();assert platform.system()=='Linux'
    assert c['execution']['watchdog']['pause_below_GiB']==3.8 and c['execution']['watchdog']['resume_above_GiB']==4.3
    root=STAGE/('smoke' if smoke else 'first');logdir=STAGE/'run_logs';tag='smoke' if smoke else 'formal'
    args=['--smoke'] if smoke else [];py=sys.executable
    append(STATUS,f'{tag} START H={H}; max_jobs=2; MemAvailable pause<3.8 resume>4.3 GiB')
    pending=[]
    for arm in trajectories(smoke):
        if (root/'trajectories'/arm/'EVALUATED').exists():verify_seal(root/'trajectories'/arm,'EVALUATED')
        else:pending.append((arm,[py,str(ROOT/'scripts/magnet9_arm.py'),'--arm',arm]+args))
    if pending:dispatch(pending,logdir,tag+'_acquisition')
    for script,marker,label in [('audit','ACQUIRED','采集与全部逐批重放'),('calibrate','CALIBRATED','校准与区间'),
                                ('evaluate','EVALUATED','首次评估'),('independent_recompute','RECOMPUTED','独立复算')]:
        if (root/marker).exists():verify_seal(root,marker);continue
        dispatch([(script,[py,str(ROOT/f'scripts/magnet9_{script}.py')]+args)],logdir,tag+'_'+script)
        verify_seal(root,marker);append(STATUS,f'{tag} {marker} sha256={sha(root/(marker+".json"))}')
        commit([root,logdir],f'第九轮：封存{"合成冒烟" if smoke else "正式K30"}{label}及日志')
    append(STATUS,f'{tag} COMPLETE')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');a=ap.parse_args()
    try:run(a.smoke)
    except BaseException as e:
        append(STATUS,f'R9 FAILED {type(e).__name__}: {e}');raise
