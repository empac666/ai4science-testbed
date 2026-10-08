"""Round-eight provenance, isolated numerical adapter, and label permissions."""
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '1'
import copy
import hashlib
import importlib.util
import json
import platform
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/magnet8'
STAGE = ROOT / 'lab/cases/magnet8'
SOURCE = ROOT / 'data/magnet/igse_predictions.csv'
FEATURE_PATH = ROOT / 'data/magnet6/features.csv'
PREREG_SHA = '1e767b17c6195e01bceb5bf20dcd4189df3b9571'
H = int(PREREG_SHA[:8], 16)
CONFIG_SHA = '9519cc2a3a372ee20e96b381e3aac2728cecfe14214e8f3d6ccd531952a9ca0a'
MODEL_SHA = 'b13d4a663df242b91f18853cd0d58333ee892f9a9263ccf39b50bc4d4744109e'
CAL = {'E1': 'CAL7r', 'E2': 'CAL8'}
EVAL = {'E1': ('X7', 'G7r'), 'E2': ('XF', 'XT', 'XFT', 'G8')}
ARMS = [f'{m}{k}' for k in range(1, 31) for m in 'AMR']
CST = timezone(timedelta(hours=8), 'Asia/Shanghai')


def now():
    return datetime.now(CST).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_bytes(content)
    os.replace(tmp, path)


def freeze(path, content):
    """Idempotent checkpoints: never replace different frozen bytes."""
    path = Path(path)
    if path.exists():
        assert path.read_bytes() == content, f'Frozen artifact mismatch: {path}'
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(content)


def write_json(path, value):
    atomic(path, encoded(value))


def append(path, line):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(line + '\n')


def config():
    assert sha(STAGE / 'config_prerun.json') == CONFIG_SHA, 'Frozen config changed'
    assert sha(ROOT / 'scripts/magnet6_model.py') == MODEL_SHA, 'Frozen model changed'
    from public_release import verify_file
    verify_file('docs/prereg/M9_magnet_round8_prereg.md')
    return read_json(STAGE / 'config_prerun.json')


def verify_sources(allow_missing_sources=False):
    c = config()
    pairs = [(FEATURE_PATH, c['reuse']['features_csv_sha256'], False),
             (SOURCE, c['data']['scalars_csv_sha256'], True),
             (ROOT / c['data']['b_waveform_npy'], c['data']['b_waveform_npy_sha256'], True)]
    checks = {}
    for path, expected, optional in pairs:
        if not path.exists() and optional and allow_missing_sources:
            checks[str(path.relative_to(ROOT))] = 'missing (explicit input/smoke waiver)'
        else:
            assert sha(path) == expected, f'Source hash mismatch: {path}'
            checks[str(path.relative_to(ROOT))] = expected
    return checks


def seed(e, r, k):
    assert e in (1, 2) and ((r == 0 and k == 0) or (r in (1, 2) and 1 <= k <= 30))
    return 2**64 + H * 2**16 + e * 4096 + r * 256 + k


def gp_seed(e):
    assert e in (1, 2)
    return 2**31 + 2 * (H % 2**29) + e - 1


def adapter(e, random_state=None):
    """New module and deep CONFIG for every arm; no legacy global mutation."""
    spec = importlib.util.spec_from_file_location('_magnet8_isolated', ROOT / 'scripts/magnet6_model.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CONFIG = copy.deepcopy(module.CONFIG)
    module.CONFIG['model']['gp_random_state'] = gp_seed(e) if random_state is None else random_state
    return module


def code_hashes():
    paths = sorted((ROOT / 'scripts').glob('magnet8_*.py'))
    paths += [ROOT / 'scripts/magnet6_model.py', ROOT / 'scripts/magnet6_design.py']
    return {p.name: sha(p) for p in paths}


def versions():
    import scipy
    import sklearn
    return dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                sklearn=sklearn.__version__, pandas=pd.__version__)


def holdouts(exp, split):
    return set().union(*(set(split[name]) for name in (*EVAL[exp], CAL[exp])))


def read_targets(ids, allowed, forbidden=()):
    """Check permissions BEFORE parsing any target; skip all unrequested rows."""
    ids = list(map(int, ids))
    assert len(ids) == len(set(ids)) and set(ids) <= set(allowed), 'Undeclared label request'
    assert not set(ids) & set(forbidden), 'Holdout labels forbidden'
    header = pd.read_csv(SOURCE, usecols=['sample_id'])
    assert header.sample_id.is_unique
    mask = header.sample_id.isin(ids).to_numpy()
    assert int(mask.sum()) == len(ids), 'Unknown id'
    table = pd.read_csv(SOURCE, usecols=['sample_id', 'measured_W_m3'],
                        skiprows=(np.flatnonzero(~mask) + 1).tolist()).set_index('sample_id')
    values = table.loc[ids, 'measured_W_m3'].to_numpy()
    assert np.isfinite(values).all() and (values > 0).all()
    return np.log10(values)


class PoolReader:
    """Arm-local authorization; only S0 and subsequently frozen batches become readable."""
    def __init__(self, exp, arm, split, real=None):
        assert exp in CAL and arm in ARMS
        self.exp, self.arm = exp, arm
        self.pool = set(split['pool'])
        self.forbidden = holdouts(exp, split)
        if real is not None:
            assert self.pool <= set(real['pool'])
            self.forbidden |= holdouts(exp, real)
        self.support = set((real or split).get('S', split['pool']))
        self.authorized = set(split[f'S0_{int(arm[1:])}'])

    def authorize(self, ids):
        assert len(ids) == len(set(ids)) and not set(ids) & self.authorized
        self._guard(ids)
        self.authorized.update(ids)

    def _guard(self, ids):
        assert set(ids) <= self.pool and not set(ids) & self.forbidden, 'Pool isolation failed'
        if self.exp == 'E2':
            assert set(ids) <= self.support, 'E2 outside support'

    def read(self, ids):
        self._guard(ids)
        assert set(ids) <= self.authorized, 'Unqueried candidate labels forbidden'
        return read_targets(ids, self.authorized, self.forbidden)


def require_box():
    if platform.system() != 'Linux':
        raise RuntimeError('Formal execution requires Linux box; use --smoke or --dry-run on local_machine')
