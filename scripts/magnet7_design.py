#!/usr/bin/env python3
"""Round-seven frozen input-only design. Family key: fset_waveform_duty_plateau."""
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
from magnet6_design import atomic, encoded, digest, sha, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/magnet7'
STAGE = ROOT / 'lab/cases/magnet7'
SOURCE = ROOT / 'data/magnet/igse_predictions.csv'
FEATURE_PATH = ROOT / 'data/magnet6/features.csv'
PREREG_SHA = '6f71603dc6de31604b51b7c0c147b2421d8c0eaa'
H = int(PREREG_SHA[:8], 16)
CONFIG_SHA = 'ddf3b11be39d5458a7b0df0b9f788f7525fbf985edc65b5d2e6856ac4163e843'
FEATURE_SHA = '781a7048e54bf7c517120b28efa450dbc584192d7faaa6fc4c3c7a2ccf47931c'
MODEL_SHA = 'b13d4a663df242b91f18853cd0d58333ee892f9a9263ccf39b50bc4d4744109e'


def config():
    assert sha(STAGE / 'config_prerun.json') == CONFIG_SHA, 'Frozen config changed'
    from public_release import verify_file
    verify_file('docs/prereg/M8_magnet_round7_prereg.md')
    assert sha(ROOT / 'scripts/magnet6_model.py') == MODEL_SHA, 'Frozen model changed'
    return json.loads((STAGE / 'config_prerun.json').read_text())


def verify_sources():
    c = config()
    for path, expected in [(FEATURE_PATH, FEATURE_SHA), (SOURCE, c['data']['scalars_csv_sha256']),
                           (ROOT / 'data/magnet/N87/B.npy', c['data']['b_waveform_npy_sha256'])]:
        assert sha(path) == expected, f'Frozen source changed: {path}'
    return c


def family_features(df):
    """Cluster UNIQUE sorted frequencies; Python round uses ties-to-even."""
    df = df.copy()
    frequencies = np.sort(df.frequency_Hz.unique())
    assert np.all(frequencies > 0)
    groups = np.split(frequencies, np.flatnonzero(np.log(frequencies[1:] / frequencies[:-1]) > .01) + 1)
    mapping = {f: int(round(float(np.median(group)) / 1000)) for group in groups for f in group}
    df['fset'] = df.frequency_Hz.map(mapping)
    df['family'] = [f'{f}_{w}_{round(10*d)}_{round(20*p)}'
                    for f, w, d, p in zip(df.fset, df.waveform, df.duty, df.plateau)]
    df['dBdt'] = np.log10(4 * df.frequency_Hz * df.amplitude_T)
    df['in_X7'] = (df.frequency_Hz >= 200000) & (df.amplitude_T >= .10)
    df['frontier'] = ~df.in_X7 & (df.frequency_Hz >= 150000) & (df.amplitude_T >= .07)
    return df


def equal_bins(values, pool_values):
    lo, hi = float(np.min(pool_values)), float(np.max(pool_values))
    assert hi > lo
    bins = np.clip(np.floor(8 * (np.asarray(values) - lo) / (hi - lo)), 0, 7).astype(int)
    return bins, np.linspace(lo, hi, 9).tolist()


def validate_split(df, split):
    groups = [set(split[key]) for key in ('X7', 'G7', 'CAL7', 'pool')]
    assert sum(map(len, groups)) == len(set.union(*groups)) == len(df)
    assert set.union(*groups) == set(map(int, df.sample_id))
    assert len(groups[0]) == 632
    for key in ('X7', 'G7', 'CAL7', 'pool'):
        assert len(split[key]) == len(set(split[key]))
    for key, n in [('G7', 40), ('CAL7', 20)]:
        families = set(split[key + '_families'])
        assert len(families) == n
        assert set(df.loc[df.family.isin(families), 'sample_id']) == set(split[key])
    assert not set(split['G7_families']) & set(split['CAL7_families'])
    for k in range(1, 21):
        s, r = split[f'S0_{k}'], split[f'R_{k}']
        assert len(s) == len(set(s)) == 100 and set(s) <= groups[3]
        assert len(r) == len(set(r)) == 120 and set(r) <= groups[3] - set(s)


def generate_split(df):
    excluded = set(df.loc[df.in_X7, 'family'])
    ok = sorted(set(df.family) - excluded)
    perm = np.random.default_rng(H).permutation(ok).tolist()
    split = dict(X7=sorted(map(int, df.loc[df.in_X7, 'sample_id'])),
                 G7_families=perm[:40], CAL7_families=perm[40:60])
    for key in ('G7', 'CAL7'):
        split[key] = sorted(map(int, df.loc[df.family.isin(split[key + '_families']), 'sample_id']))
    held = set().union(*(set(split[key]) for key in ('X7', 'G7', 'CAL7')))
    split['pool'] = sorted(set(map(int, df.sample_id)) - held)
    for k in range(1, 21):
        s0 = np.random.default_rng(H + k).choice(split['pool'], 100, replace=False).tolist()
        split[f'S0_{k}'] = s0
        split[f'R_{k}'] = np.random.default_rng(H + 100 + k).choice(sorted(set(split['pool']) - set(s0)), 120, replace=False).tolist()
    validate_split(df, split)
    return split


def build():
    c = verify_sources()
    df = family_features(pd.read_csv(FEATURE_PATH))
    assert len(df) == c['data']['n_total'] and df.sample_id.is_unique
    assert df.fset.nunique() == 20 and df.family.nunique() == 291
    split = generate_split(df)
    df['dBdt_bin'], edges = equal_bins(df.dBdt, df.loc[df.sample_id.isin(split['pool']), 'dBdt'])
    df['cell'] = df.dBdt_bin.astype(str)  # reused believer's category API
    design = df[['sample_id', 'fset', 'family', 'dBdt', 'dBdt_bin', 'in_X7', 'frontier']]
    content = design.to_csv(index=False, float_format='%.17g').encode()
    summary = dict(H=H, prereg_sha=PREREG_SHA, config_sha256=CONFIG_SHA, features_sha256=FEATURE_SHA,
                   model_sha256=MODEL_SHA, design_sha256=hashlib.sha256(content).hexdigest(),
                   split_sha256=digest(split), dBdt_edges=edges,
                   family_key_format='fset_waveform_round(10*duty)_round(20*plateau)',
                   sets={key: dict(n=len(value), sha256=digest(value)) for key, value in split.items()})
    return df.set_index('sample_id', drop=False), split, content, summary


def load_design():
    df, split, content, summary = build()
    assert (OUT / 'design.csv').read_bytes() == content
    assert (OUT / 'split.json').read_bytes() == encoded(split)
    assert (STAGE / 'split_summary.json').read_bytes() == encoded(summary)
    return df, split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    _, split, content, summary = build()
    for path, data in [(OUT / 'design.csv', content), (OUT / 'split.json', encoded(split)),
                       (STAGE / 'split_summary.json', encoded(summary))]:
        if args.verify or path.exists():
            assert path.read_bytes() == data, f'Frozen design mismatch: {path}'
        else:
            atomic(path, data)
    print('Round-seven label-free design verified.' if args.verify else 'Round-seven label-free design generated.')


if __name__ == '__main__':
    main()
