#!/usr/bin/env python3
"""第六轮正式运行驱动（主持人）：最多 2 个并行臂、单线程、内存看门狗、断点续跑。

已有 DONE 标记的臂跳过；未完成的臂由 magnet6_arm.py 依据冻结批次文件确定性续跑。
看门狗：MemAvailable < 3.8 GiB 时对子进程 SIGSTOP，> 4.3 GiB 时 SIGCONT。
不打印任何留出集指标。
"""
import os, signal, subprocess, sys, time, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/magnet6'
STATUS = Path('./ai4s_r6_status.md')
CST = timezone(timedelta(hours=8))
PAUSE, RESUME = 3.8 * 2**30, 4.3 * 2**30
MAXJ = 2
ARMS = [f'R{k}' for k in range(1, 9)] + [f'{m}{k}' for k in range(1, 9) for m in ('A', 'M')]
ENV = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
           NUMEXPR_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')

def now(): return datetime.now(CST).strftime('%F %T')
def avail():
    for line in open('/proc/meminfo'):
        if line.startswith('MemAvailable:'): return int(line.split()[1]) * 1024
def log(msg):
    line = f'- {now()} CST：[sweep] {msg}'
    print(line, flush=True)
    with STATUS.open('a') as f: f.write(line + '\n')
def done(arm): return (OUT / 'arms' / arm / 'DONE').exists()

def main():
    todo = [a for a in ARMS if not done(a)]
    log(f'启动；待跑 {len(todo)}/24 臂：{",".join(todo)}；pid={os.getpid()}')
    running = {}; paused = False; t0 = time.time(); fails = {}
    while todo or running:
        a = avail()
        if not paused and a < PAUSE and running:
            for p in running.values(): os.kill(p.pid, signal.SIGSTOP)
            paused = True; log(f'内存 {a/2**30:.2f} GiB < 3.8，暂停子进程')
        elif paused and a > RESUME:
            for p in running.values(): os.kill(p.pid, signal.SIGCONT)
            paused = False; log(f'内存 {a/2**30:.2f} GiB > 4.3，恢复子进程')
        for arm, p in list(running.items()):
            rc = p.poll()
            if rc is None: continue
            del running[arm]
            if rc == 0 and done(arm):
                n = sum(done(x) for x in ARMS)
                log(f'{arm} 完成（{n}/24，已用 {(time.time()-t0)/60:.1f} min）')
            else:
                fails[arm] = fails.get(arm, 0) + 1
                log(f'{arm} 失败 rc={rc}（第 {fails[arm]} 次）；见 data/magnet6/arms/{arm}/stderr.txt')
                if fails[arm] < 3: todo.insert(0, arm)
        while todo and len(running) < MAXJ and not paused and avail() > RESUME:
            arm = todo.pop(0); d = OUT / 'arms' / arm; d.mkdir(parents=True, exist_ok=True)
            err = open(d / 'stderr.txt', 'a')
            running[arm] = subprocess.Popen([sys.executable, str(ROOT/'scripts/magnet6_arm.py'), '--arm', arm,
                '--out', str(OUT)], cwd=ROOT, env=ENV, stdout=err, stderr=err, start_new_session=True)
            log(f'{arm} 启动 pid={running[arm].pid}')
        time.sleep(5)
    n = sum(done(x) for x in ARMS)
    log(f'结束：{n}/24 完成；墙钟 {(time.time()-t0)/60:.1f} min' + ('' if n == 24 else '；有失败臂，检查 stderr 后重启本脚本即可续跑'))
    (OUT / 'sweep_timing.json').write_text(json.dumps(dict(completed=n, wall_s=time.time()-t0, finished=now()), ensure_ascii=False))
if __name__ == '__main__': main()
