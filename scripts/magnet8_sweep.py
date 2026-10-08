"""Linux-only dispatcher: 180 arms, <=2 workers, independent memory watchdog."""
from magnet8_common import *
import argparse
import math
import signal
import sys
import time

STATUS = Path('./ai4s_r8_status.md')
LOG = Path('./r6_logs/sweep8.log')
PAUSE_GIB, RESUME_GIB = 3.8, 4.3


def schedule():
    return [(exp, f'{method}{k}') for k in range(1, 31) for exp in CAL for method in 'AMR']


def done(source, exp, arm):
    folder = Path(source)/'arms'/exp/arm
    if not (folder/'DONE').exists():
        return False
    assert not (folder/'RUNNING').exists()
    assert (folder/'DONE').read_text(encoding='utf-8').strip() == sha(folder/'result.json'), 'Invalid DONE seal'
    return True


def pending(source=OUT):
    return [(e, a) for e, a in schedule() if not done(source, e, a)]


def available(path=Path('/proc/meminfo')):
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1])*1024
    raise RuntimeError('MemAvailable unavailable; refusing dispatch')


def paused_state(paused, memory, pause_gib=PAUSE_GIB, resume_gib=RESUME_GIB):
    return memory <= resume_gib*2**30 if paused else memory < pause_gib*2**30


def validate_thresholds(pause_gib, resume_gib):
    if not (math.isfinite(pause_gib) and math.isfinite(resume_gib) and 0 < pause_gib < resume_gib):
        raise ValueError('thresholds must be finite and satisfy 0 < pause-gib < resume-gib')


def group_signal(process, sig):
    if process.poll() is None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass


def run(source=OUT, jobs=2, dry_run=False, low_memory_timeout=900,
        pause_gib=PAUSE_GIB, resume_gib=RESUME_GIB):
    validate_thresholds(pause_gib, resume_gib)
    assert jobs in (1, 2) and low_memory_timeout > 0
    source = Path(source)
    todo = pending(source)
    if dry_run:
        for exp, arm in todo:
            print(f'{exp}/{arm}')
        print(f'Pending: {len(todo)}/180; no workers started.')
        return 0
    require_box()
    assert source.resolve() == OUT.resolve(), 'Formal arms use the frozen data/magnet8 output root'
    verify_sources()
    source.mkdir(parents=True, exist_ok=True)
    lock = source/'SWEEP_RUNNING'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    running, failed, finished = {}, {}, []
    paused, low_since, started = False, None, time.monotonic()
    initial_done = 180-len(todo)
    aborted = False
    timing = dict(started_at=now(), pause_gib=pause_gib, resume_gib=resume_gib)
    def log(message, status=False):
        line = f'{now()} CST [sweep8] completed={initial_done+len(finished)}/180 failed={len(failed)} {message}'
        append(LOG, line)
        if status:
            append(STATUS, line)
        print(line, flush=True)
    env = dict(os.environ, **{k: '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')},
               PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    old_handlers = {}
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'signal={signum}')
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, interrupted)
        log(f'Start pending={len(todo)} jobs={jobs} pause_gib={pause_gib} resume_gib={resume_gib}', True)
        write_json(source/'sweep_timing.json', dict(timing, completed=initial_done, failed={},
                   wall_seconds=0., finished_at=None, aborted=False, pending=todo))
        while todo or running:
            memory = available()
            next_paused = paused_state(paused, memory, pause_gib, resume_gib)
            if next_paused != paused:
                paused = next_paused
                for process, _ in running.values():
                    group_signal(process, signal.SIGSTOP if paused else signal.SIGCONT)
                log(f'{"PAUSED" if paused else "RESUMED"} MemAvailable={memory/2**30:.3f} GiB', True)
            low_since = (low_since or time.monotonic()) if paused else None
            if low_since and time.monotonic()-low_since >= low_memory_timeout:
                raise RuntimeError('Persistent low memory: infrastructure stop; resume same frozen state')
            for key, (process, stream) in list(running.items()):
                rc = process.poll()
                if rc is None:
                    status_path = Path(f'/proc/{process.pid}/status')
                    if status_path.exists():
                        for line in status_path.read_text(encoding='utf-8').splitlines():
                            if line.startswith('VmRSS:') and int(line.split()[1])*1024 >= 1.5*2**30:
                                group_signal(process, signal.SIGCONT)
                                group_signal(process, signal.SIGTERM)
                                failed['/'.join(key)] = 'RSS >= 1.5 GiB'
                                log(f'{key} memory limit termination', True)
                    continue
                stream.close()
                del running[key]
                label = '/'.join(key)
                if rc == 0 and done(source, *key) and label not in failed:
                    finished.append(label)
                    log(f'DONE {label}', (initial_done+len(finished)) % 10 == 0)
                else:
                    failed[label] = failed.get(label, f'exit={rc}; missing DONE' if rc == 0 else f'exit={rc}')
                    log(f'FAILED {label} {failed[label]}; continuing remaining arms', True)
            while todo and len(running) < jobs and not paused:
                # Check between launches as well as every five seconds.
                if paused_state(False, available(), pause_gib, resume_gib):
                    break
                exp, arm = todo.pop(0)
                folder = source/'arms'/exp/arm
                folder.mkdir(parents=True, exist_ok=True)
                stream = (folder/'stderr.txt').open('a', encoding='utf-8', newline='\n')
                try:
                    process = subprocess.Popen([sys.executable, str(ROOT/'scripts/magnet8_arm.py'), '--exp', exp, '--arm', arm],
                                               cwd=ROOT, env=env, stdout=stream, stderr=stream, start_new_session=True)
                except OSError as exc:
                    stream.close()
                    failed[f'{exp}/{arm}'] = str(exc)
                    log(f'FAILED launch {exp}/{arm}: {exc}', True)
                    continue
                running[(exp, arm)] = (process, stream)
                log(f'Started {exp}/{arm} pid={process.pid}')
            if todo or running:
                time.sleep(5)
    except BaseException as exc:
        aborted = True
        log(f'Infrastructure stop: {type(exc).__name__}: {exc}', True)
    finally:
        for process, _ in running.values():
            group_signal(process, signal.SIGCONT)
            group_signal(process, signal.SIGTERM)
        for key, (process, stream) in running.items():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                group_signal(process, signal.SIGKILL)
                process.wait(timeout=5)
            stream.close()
            failed['/'.join(key)] = 'Infrastructure stop; inspect checkpoint/lock before resuming'
        log('Finished' if not aborted else 'Stopped incomplete', True)
        write_json(source/'sweep_timing.json', dict(timing, completed=initial_done+len(finished), failed=failed,
                   wall_seconds=time.monotonic()-started, finished_at=now(), aborted=aborted, pending=todo))
        lock.unlink()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    return int(aborted or bool(failed) or initial_done+len(finished) != 180)


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--jobs', type=int, default=2, choices=(1, 2))
    ap.add_argument('--low-memory-timeout', type=float, default=900)
    ap.add_argument('--pause-gib', type=float, default=PAUSE_GIB, help='Pause below this MemAvailable threshold in GiB (default: 3.8)')
    ap.add_argument('--resume-gib', type=float, default=RESUME_GIB, help='Resume above this MemAvailable threshold in GiB (default: 4.3)')
    args = ap.parse_args(argv)
    try:
        validate_thresholds(args.pause_gib, args.resume_gib)
    except ValueError as exc:
        ap.error(str(exc))
    return args


def main():
    args = parse_args()
    raise SystemExit(run(jobs=args.jobs, dry_run=args.dry_run, low_memory_timeout=args.low_memory_timeout,
                         pause_gib=args.pause_gib, resume_gib=args.resume_gib))


if __name__ == '__main__':
    main()
