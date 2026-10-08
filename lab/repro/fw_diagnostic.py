"""Explicit diagnostic for hosts without GNU make; never presented as a make run.

Commands mirror be9a0f4 fw/Makefile and execute serially. This supplemental
command does not satisfy the milestone's requirement to execute GNU make.
"""
import argparse
import shlex
import shutil
import subprocess
from pathlib import Path
from .runner import ROOT, PYTHON


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fw', default='data/dclink_src/fw')
    args = parser.parse_args()
    fw = (ROOT / args.fw).resolve()
    fw.relative_to(ROOT)
    build = fw / 'build'
    if build.exists():
        shutil.rmtree(build)
    build.mkdir()
    sources = ['src/dclink_crc.c', 'src/dclink_logger.c', 'src/dclink_cap_est.c', 'src/dclink_gate.c', 'src/dclink_baseline.c']
    flags = ['gcc', '-Iinclude', '-Itest', '-std=c99', '-Wall', '-Wextra', '-Werror', '-O2']
    def execute(cmd):
        print('+ ' + shlex.join(cmd), flush=True)
        subprocess.run(cmd, cwd=fw, check=True)
    def compile_all(extra, suffix):
        execute(flags + extra + sources + ['test/mock_flash.c', 'test/test_dclink.c', '-pthread', '-lm', '-o', 'build/test_dclink' + suffix])
        execute(flags + extra + sources + ['tools/dclink_replay.c', '-lm', '-o', 'build/dclink_replay' + suffix])
        execute(flags + extra + ['tools/sizeof_dclink.c', '-o', 'build/sizeof_dclink' + suffix])
    compile_all([], '')
    execute(['./build/test_dclink'])
    execute([PYTHON, 'test/test_replay.py'])
    execute(['./build/sizeof_dclink'])
    compile_all(['-Wpedantic', '-Wconversion'], '_check')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
