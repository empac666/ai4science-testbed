#!/usr/bin/env python3
"""Frozen, label-free round-six features and ordered random allocations."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from magnet_igse import classify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/magnet6'
STAGE = ROOT / 'lab/cases/magnet6'
SOURCE = ROOT / 'data/magnet/igse_predictions.csv'
B_PATH = ROOT / 'data/magnet/N87/B.npy'
PREREG_SHA = 'd8a805bb540f3b4bb479fed77cd1f35120720c26'
H = int(PREREG_SHA[:8], 16)
CONFIG_SHA = 'eba77b4c9ba020225ecd41fea76972b6a09c328d0c09151115d0db1485b0fdb5'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_bytes(content)
    os.replace(tmp, path)


def write_json(path, value):
    atomic(path, encoded(value))


def config():
    assert sha(STAGE / 'config_prerun.json') == CONFIG_SHA, 'Frozen config changed'
    from public_release import verify_file
    verify_file('docs/prereg/M7_magnet_round6_prereg.md')
    return json.loads((STAGE / 'config_prerun.json').read_text())


def verify_sources():
    c = config()
    assert sha(SOURCE) == c['data']['scalars_csv_sha256'], 'Scalar source changed'
    assert sha(B_PATH) == c['data']['b_waveform_npy_sha256'], 'B source changed'
    return c


def features():
    c = verify_sources()
    df = pd.read_csv(SOURCE, usecols=['sample_id', 'frequency_Hz', 'temperature_C', 'amplitude_T', 'waveform'])
    assert df.sample_id.tolist() == list(range(c['data']['n_total']))
    b = np.load(B_PATH, mmap_mode='r')
    assert b.shape == (len(df), 1024) and b.dtype == np.float64
    parts = []
    for start in range(0, len(df), 512):
        x = np.asarray(b[start:start + 512])
        rows = df.iloc[start:start + len(x)]
        labels, _, plateau = classify(x)
        assert np.array_equal(labels, rows.waveform.to_numpy()), 'Classification mismatch'
        pk = np.ptp(x, axis=1) / 2
        assert np.allclose(pk, rows.amplitude_T, rtol=1e-10, atol=0)
        f = rows.frequency_Hz.to_numpy()
        diff = np.roll(x, -1, axis=1) - x
        part = rows.rename(columns={'temperature_C': 'T_C'}).copy()
        part['log10_f'] = np.log10(f)
        part['log10_Bpk'] = np.log10(pk)
        part['duty'] = np.mean(diff > 0, axis=1)
        part['plateau'] = plateau
        part['shape'] = np.log10(np.mean((np.abs(diff) * 1024 * f[:, None]) ** 1.5, axis=1) / (4 * f * pk) ** 1.5)
        part['cell'] = [f'{w}_T{t:g}' for w, t in zip(labels, rows.temperature_C)]
        # Retain source scalars for the exact frozen corner threshold.
        part['corner'] = (rows.frequency_Hz >= 200000) & (rows.amplitude_T >= .10)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def generate_split(df):
    ids = sorted(map(int, df.sample_id))
    corners = sorted(map(int, df.loc[df.corner, 'sample_id']))
    non = sorted(set(ids) - set(corners))
    assert len(corners) == 632
    rng = np.random.default_rng(H)
    split = dict(C6=rng.permutation(corners)[:200].tolist())
    perm = rng.permutation(non)
    split.update(T6=perm[:300].tolist(), CAL6=perm[300:400].tolist())
    held = set().union(*(set(v) for v in split.values()))
    pool = sorted(set(ids) - held)
    split['pool'] = pool
    assert len(held) == 600 and len(pool) == 40016
    assert sum(i in corners for i in pool) == 432
    for k in range(1, 9):
        s0 = np.random.default_rng(H + k).choice(sorted(set(pool) & set(non)), 100, replace=False).tolist()
        r = np.random.default_rng(H + 100 + k).choice(sorted(set(pool) - set(s0)), 120, replace=False).tolist()
        assert set(s0) <= set(pool) & set(non) and set(r) <= set(pool) - set(s0)
        split[f'S0_{k}'], split[f'R_{k}'] = s0, r
    return split


def load_design():
    verify_sources()
    summary = json.loads((STAGE / 'split_summary.json').read_text())
    assert sha(OUT / 'features.csv') == summary['features_sha256']
    split = json.loads((OUT / 'split.json').read_text())
    assert digest(split) == summary['split_sha256']
    df = pd.read_csv(OUT / 'features.csv')
    assert generate_split(df) == split
    return df.set_index('sample_id', drop=False), split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    df = features()
    content = df.to_csv(index=False, float_format='%.17g').encode()
    split = generate_split(df)
    summary = dict(H=H, prereg_sha=PREREG_SHA, config_sha256=CONFIG_SHA,
                   features_sha256=hashlib.sha256(content).hexdigest(), split_sha256=digest(split),
                   sets={k: dict(n=len(v), sha256=digest(v)) for k, v in split.items()})
    for path, data in [(OUT / 'features.csv', content), (OUT / 'split.json', encoded(split)), (STAGE / 'split_summary.json', encoded(summary))]:
        if args.verify or path.exists():
            assert path.read_bytes() == data, f'Frozen design mismatch: {path}'
        else:
            atomic(path, data)
    print('Round-six label-free design verified.' if args.verify else 'Round-six label-free design generated.')


if __name__ == '__main__':
    main()
