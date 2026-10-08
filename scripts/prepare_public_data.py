"""Restore small, published inputs for offline checks; never download or simulate."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def copy_once(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != source.read_bytes():
            raise ValueError('Refusing to overwrite runtime file: ' + str(target))
    else:
        shutil.copyfile(source, target)


def main():
    for case in ('dclink2', 'dclink3', 'dclink4', 'dclink5'):
        for filename in ('design.json', 'pool.json'):
            source = ROOT / 'lab/cases' / case / filename
            if source.exists():
                copy_once(source, ROOT / 'data' / case / filename)
    import dclink_design3 as design
    generated, pool, split, manifest = design.artifacts()
    assert generated == json.loads((design.STAGE / 'design.json').read_text())
    assert pool == json.loads((design.STAGE / 'pool.json').read_text())
    assert manifest == json.loads((design.STAGE / 'split_manifest.json').read_text())
    design.freeze(design.OUT / 'split.json', split)
    (ROOT / 'data/dclink5_smoke').mkdir(parents=True, exist_ok=True)
    print('Published input metadata restored; no raw waveform data or simulator copied.')


if __name__ == '__main__':
    main()
