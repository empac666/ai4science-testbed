#!/usr/bin/env python3
"""冻结 DC-link 扫描的数据划分（只依赖输入参数 design.json，不读取任何目标值 y）。
OOD = {dead_time == 3.0 µs} ∪ {load <= 0.35 且 bw_iac <= 75 kHz}；
其余分布内样本按固定种子 60/20/20 划分为 train/calib/test。"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
SEED = 20261003

def make_split(design):
    ids = sorted(d['case_id'] for d in design)
    by = {d['case_id']: d for d in design}
    ood_dt = [i for i in ids if abs(by[i]['dead_time_us'] - 3.0) < 1e-9]
    ood_corner = [i for i in ids if i not in ood_dt and by[i]['load'] <= 0.35 and by[i]['bw_iac_khz'] <= 75.0]
    ind = [i for i in ids if i not in ood_dt and i not in ood_corner]
    perm = np.random.default_rng(SEED).permutation(len(ind))
    ind = [ind[k] for k in perm]
    n_tr = round(0.6 * len(ind)); n_ca = round(0.2 * len(ind))
    split = dict(rule='OOD = {dead_time_us == 3.0} ∪ {load <= 0.35 and bw_iac_khz <= 75}; in-dist 60/20/20',
                 seed=SEED, train=sorted(ind[:n_tr]), calib=sorted(ind[n_tr:n_tr+n_ca]),
                 test=sorted(ind[n_tr+n_ca:]), ood_deadtime3=ood_dt, ood_lowload_lowbw=ood_corner)
    body = json.dumps(split, sort_keys=True, separators=(',', ':')).encode()
    return split, hashlib.sha256(body).hexdigest()

def main():
    design = json.loads((ROOT/'data/dclink/design.json').read_text())
    split, h = make_split(design)
    design_hash = hashlib.sha256((ROOT/'data/dclink/design.json').read_bytes()).hexdigest()
    out = dict(split, split_sha256=h, design_sha256=design_hash)
    (ROOT/'data/dclink/split.json').write_text(json.dumps(out, indent=2, ensure_ascii=False))
    man = dict(split_sha256=h, design_sha256=design_hash, seed=SEED, rule=split['rule'],
               counts={k: len(split[k]) for k in ('train','calib','test','ood_deadtime3','ood_lowload_lowbw')})
    (ROOT/'lab/cases/dclink').mkdir(parents=True, exist_ok=True)
    (ROOT/'lab/cases/dclink/split_manifest.json').write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(json.dumps(man, ensure_ascii=False))
    if len(sys.argv) > 1 and sys.argv[1] == '--verify':
        ref = json.loads((ROOT/'lab/cases/dclink/split_manifest.json').read_text())
        assert ref['split_sha256'] == h
if __name__ == '__main__': main()
