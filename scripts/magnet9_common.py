"""R9 immutable provenance and stage-scoped label permissions (no legacy imports)."""
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '1'
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'lab/cases/magnet9'
DATA = ROOT / 'data/magnet9'
SOURCE = ROOT / 'data/magnet/igse_predictions.csv'
FEATURE_PATH = ROOT / 'data/magnet6/features.csv'
PREREG_SHA = 'cb912d916b76a055680794f1ac4e5b7e0e8765ca'
H = int(PREREG_SHA[:8], 16)
GP_SEED = 2**30 + H % 2**29
REGIONS = ('G9', 'XF', 'XT', 'XFT')
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(x):
    return (json.dumps(x, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def digest(x):
    return hashlib.sha256(encoded(x)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def freeze(path, content):
    path = Path(path)
    if path.exists():
        assert path.read_bytes() == content, f'Frozen bytes differ: {path}'
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f:
            f.write(content)


def write_json(path, x):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_bytes(encoded(x))
    os.replace(tmp, path)


def append(path, message):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(f'{now()} {message}\n')


def seal(folder, name, files, **extra):
    folder = Path(folder)
    manifest = dict(files={str(Path(p).relative_to(folder)): sha(p) for p in files}, **extra)
    freeze(folder/f'{name}.json', encoded(manifest))
    freeze(folder/name, (sha(folder/f'{name}.json')+'\n').encode())
    return manifest


def verify_seal(folder, name):
    folder = Path(folder)
    assert (folder/name).read_text().strip() == sha(folder/f'{name}.json')
    manifest = read_json(folder/f'{name}.json')
    for p, checksum in manifest['files'].items():
        assert sha(folder/p) == checksum, f'Seal mismatch: {folder/p}'
    return manifest


def config():
    c = read_json(STAGE/'config_prerun.json')
    from public_release import verify_file
    for p in c['freeze']['effective_deliverables']:
        verify_file(p)
    return c


def verify_sources():
    c = config()
    pairs = [(c['data']['features_csv'], c['data']['features_sha256']),
             (c['data']['target_csv'], c['data']['target_csv_sha256']),
             (c['data']['waveform_npy'], c['data']['waveform_sha256']),
             ('scripts/magnet6_model.py', '9f8e3f66b2d991a4929d57944a1a3c1f20ca70a1a4c1aa98c6e75911a0993436'),
             ('scripts/magnet7_design.py', c['family_definition']['reference_sha256'])]
    for p, checksum in pairs:
        assert sha(ROOT/p) == checksum, f'Source mismatch: {p}'
    return dict(pairs)


def seed(r, k):
    assert (r == 0 and k == 0) or (r == 1 and 1 <= k <= 30)
    return 2**96 + H*2**16 + r*256 + k


def seed_audit():
    old = {20261004, 3169646126, 3169646127}
    for h, n in ((3634890171, 8), (1869701181, 20)):
        old |= {h} | {h+k for k in range(1, n+1)} | {h+100+k for k in range(1, n+1)}
    old |= {2**64+511081239*2**16+e*4096+r*256+k for e in (1, 2)
            for r, k in [(0, 0)]+[(r, k) for r in (1, 2) for k in range(1, 31)]}
    new = {seed(0, 0)} | {seed(1, k) for k in range(1, 31)} | {GP_SEED}
    assert len(new) == 32 and not new & old
    return dict(historical=sorted(old), current=sorted(new), intersection=[],
                sharing='GP seed across all fits; common permutation within U/S pair; B/E/D share trajectory')


def code_hashes():
    paths=sorted((ROOT/'scripts').glob('magnet9_*.py'))+sorted((ROOT/'tests').glob('test_magnet9_*.py'))
    return {str(p.relative_to(ROOT)): sha(p) for p in paths
            if p.name not in ('magnet9_figures.py', 'magnet9_report.py')}


def versions():
    import scipy
    import sklearn
    return dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                sklearn=sklearn.__version__, pandas=pd.__version__)


def trajectories(smoke=False):
    return [f'{s}{k:02d}' for k in range(1, (1 if smoke else 30)+1) for s in ('U', 'S')]


def read_targets(ids, allowed, forbidden=()):
    """Permission assertion precedes CSV parser; skip every unrequested target row."""
    ids = list(map(int, ids))
    assert len(ids) == len(set(ids)) and set(ids) <= set(allowed)
    assert not set(ids) & set(forbidden), 'Forbidden label request'
    header = pd.read_csv(SOURCE, usecols=['sample_id'])
    assert header.sample_id.is_unique
    mask = header.sample_id.isin(ids).to_numpy()
    assert int(mask.sum()) == len(ids)
    table = pd.read_csv(SOURCE, usecols=['sample_id', 'measured_W_m3'],
                        skiprows=(np.flatnonzero(~mask)+1).tolist()).set_index('sample_id')
    y = table.loc[ids, 'measured_W_m3'].to_numpy()
    assert np.isfinite(y).all() and (y > 0).all()
    return np.log10(y)


class LabelReader:
    def __init__(self, split, arm, phase, log, df=None, smoke=False):
        assert arm in trajectories(smoke) and phase in ('acquire', 'calibrate', 'evaluate')
        self.split, self.arm, self.phase, self.log = split, arm, phase, log
        self.df, self.smoke = df, smoke
        self.allowed = set(split['S0'][arm]) if phase == 'acquire' else (
            set(split['CAL9']) if phase == 'calibrate' else set().union(*(set(split[z]) for z in REGIONS)))
        self.forbidden = set().union(*(set(split[z]) for z in ('CAL9',)+REGIONS)) if phase == 'acquire' else (
            set(split['pool']) | set().union(*(set(split[z]) for z in REGIONS)) if phase == 'calibrate' else
            set(split['pool']) | set(split['CAL9']))

    def authorize(self, ids):
        assert self.phase == 'acquire' and len(ids) == len(set(ids))
        assert set(ids) <= set(self.split['pool']) and not set(ids) & self.allowed
        assert not set(ids) & self.forbidden
        self.allowed.update(ids)
        append(self.log, json.dumps(dict(arm=self.arm, phase=self.phase, event='authorize', ids=ids)))

    def read(self, ids):
        assert set(ids) <= self.allowed and not set(ids) & self.forbidden
        append(self.log, json.dumps(dict(arm=self.arm, phase=self.phase, event='read', ids=ids,
                                        synthetic=self.smoke)))
        if self.smoke:
            x = self.df.loc[ids]
            # Deterministic input-only smoke targets; never open real labels in smoke.
            return (1.3*x.log10_f + 2.1*x.log10_Bpk - .003*x.T_C +
                    .08*np.sin(17*x.log10_f + 13*x.log10_Bpk) + .02*x['shape']).to_numpy()
        return read_targets(ids, self.allowed, self.forbidden)
