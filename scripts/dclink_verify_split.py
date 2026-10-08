#!/usr/bin/env python3
"""Execute the frozen --verify command while suppressing identical JSON rewrites."""
import json
import runpy
import sys
from pathlib import Path
from dclink_surrogate import ROOT, verify_split

def main():
    split=verify_split()
    original=Path.write_text
    allowed={ROOT/'data/dclink/split.json', ROOT/'lab/cases/dclink/split_manifest.json'}
    def readonly_write(path, data, *args, **kwargs):
        if path.resolve() not in allowed or json.loads(path.read_text()) != json.loads(data):
            raise ValueError('Frozen verifier attempted a nonidentical write: '+str(path))
        return len(data)
    Path.write_text=readonly_write
    sys.argv=[str(ROOT/'scripts/dclink_split.py'),'--verify']
    try:
        runpy.run_path(sys.argv[0],run_name='__main__')
    finally:
        Path.write_text=original
    print(json.dumps({'verified':1, **{g+'_n':len(split[g]) for g in ('train','calib','test','ood_deadtime3','ood_lowload_lowbw')}}))

if __name__=='__main__': main()
