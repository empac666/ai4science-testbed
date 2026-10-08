#!/usr/bin/env bash
# 从零重建 DC-link 扫描数据集（删除旧输出与 numba 缓存），记录墙钟时间。
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf data/dclink data/numba_cache && mkdir -p data/dclink
t0=$(date +%s.%N)
python3 scripts/dclink_sweep.py --jobs "${JOBS:-4}" --n "${N:-240}" > data/dclink/sweep.log 2>&1
t1=$(date +%s.%N)
python3 -c "import json,sys;t0,t1=map(float,sys.argv[1:]);json.dump({'rebuild_wall_s':t1-t0,'started_epoch':t0},open('data/dclink/rebuild_timing.json','w'),indent=2)" "$t0" "$t1"
echo "rebuild done in $(python3 -c "import sys;print(round(float(sys.argv[2])-float(sys.argv[1]),1))" "$t0" "$t1") s"
