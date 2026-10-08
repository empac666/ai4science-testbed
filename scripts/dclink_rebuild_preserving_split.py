#!/usr/bin/env python3
"""Host-only rebuild entry: preserve exact frozen split bytes across destructive sweep."""
import hashlib
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'data/dclink/split.json'
    frozen=path.read_bytes()
    split=json.loads(frozen)
    manifest=json.loads((ROOT/'lab/cases/dclink/split_manifest.json').read_text())
    body={k:v for k,v in split.items() if k not in ('split_sha256','design_sha256')}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest != split['split_sha256'] or digest != manifest['split_sha256']:
        raise ValueError('Frozen split hash mismatch; rebuild aborted')
    try:
        subprocess.run(['bash','scripts/dclink_rebuild.sh'],cwd=ROOT,check=True)
    finally:
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            if path.read_bytes()!=frozen:
                raise ValueError('Unexpected changed split; refusing overwrite')
        else:
            path.write_bytes(frozen)
    design_hash=hashlib.sha256((ROOT/'data/dclink/design.json').read_bytes()).hexdigest()
    if design_hash != split['design_sha256'] or design_hash != manifest['design_sha256']:
        raise ValueError('Rebuilt design differs from frozen design; do not train')

if __name__=='__main__': main()
