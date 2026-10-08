#!/usr/bin/env python3
"""只读输入参数；冻结 train/calib/test/OOD 划分，不读取 y。"""
import hashlib
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
GROUPS=('train','calib','test','ood_dt3','ood_corner','supplement_ood')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def make_split(new, old):
    train=sorted(p['case_id'] for p in old if p['dead_time_us']<3 and not (p['load']<=.35 and p['bw_iac_khz']<=75))
    seen={p['case_id'] for p in old}-set(train)
    ind=[p['case_id'] for p in new if p['group']=='E-in']
    perm=np.random.default_rng(20261005).permutation(len(ind))
    ind=[ind[i] for i in perm]
    split=dict(seed=20261005,train=train,calib=sorted(ind[:75]),test=sorted(ind[75:]),
               ood_dt3=sorted(p['case_id'] for p in new if p['group']=='E-dt3'),
               ood_corner=sorted(p['case_id'] for p in new if p['group']=='E-corner'),supplement_ood=sorted(seen))
    assert [len(split[g]) for g in GROUPS]==[200,75,75,30,30,40]
    return split

def expected():
    new=ROOT/'data/dclink2/design.json'; old=ROOT/'data/dclink/design.json'
    split=make_split(json.loads(new.read_text()),json.loads(old.read_text()))
    return dict(split,split_sha256=digest(split),design_sha256=sha(new),round1_design_sha256=sha(old))

def verify():
    obj=expected()
    for path in (ROOT/'data/dclink2/split.json',ROOT/'lab/cases/dclink2/split_manifest.json'):
        if json.loads(path.read_text())!=obj: raise ValueError(f'Frozen manifest mismatch: {path}')
    return obj

def main():
    import sys
    if '--verify' in sys.argv:
        print(json.dumps(verify())); return
    obj=expected()
    for path in (ROOT/'data/dclink2/split.json',ROOT/'lab/cases/dclink2/split_manifest.json'):
        path.parent.mkdir(parents=True,exist_ok=True)
        text=json.dumps(obj,indent=2,ensure_ascii=False)+'\n'
        if path.exists() and path.read_text()!=text: raise ValueError('Refusing to replace frozen split')
        path.write_text(text)
    print(json.dumps(obj))
if __name__=='__main__': main()
