"""Deterministic input-only R8 design; never parses labels."""
from magnet8_common import *
import argparse


def family_features(df):
    df = df.copy()
    frequencies = np.sort(df.frequency_Hz.unique())
    assert (frequencies > 0).all()
    groups = np.split(frequencies, np.flatnonzero(np.log(frequencies[1:] / frequencies[:-1]) > .01) + 1)
    mapping = {f: int(round(float(np.median(g)) / 1000)) for g in groups for f in g}
    df['fset'] = df.frequency_Hz.map(mapping)
    df['family'] = [f'{f}_{w}_{round(10*d)}_{round(20*p)}'
                    for f, w, d, p in zip(df.fset, df.waveform, df.duty, df.plateau)]
    df['dBdt'] = np.log10(4 * df.frequency_Hz * df.amplitude_T)
    return df


def equal_bins(values, pool_values):
    lo, hi = float(np.min(pool_values)), float(np.max(pool_values))
    assert hi > lo
    return np.clip(np.floor(8 * (np.asarray(values)-lo)/(hi-lo)), 0, 7).astype(int), np.linspace(lo, hi, 9).tolist()


def generate_split(df):
    df = df.sort_values('sample_id').set_index('sample_id', drop=False)
    ids = lambda mask: df.loc[mask, 'sample_id'].astype(int).tolist()
    x = ids((df.frequency_Hz >= 200000) & (df.amplitude_T >= .10))
    low, cool = df.fset < 300, df.T_C <= 70
    s = ids(low & cool)
    split = {'E1': {'X7': x}, 'E2': dict(S=s, XF=ids(~low & cool), XT=ids(low & ~cool), XFT=ids(~low & ~cool))}
    for e, exp in enumerate(('E1', 'E2'), 1):
        item = split[exp]
        domain = df if e == 1 else df.loc[s]
        families = sorted(set(df.family) - set(df.loc[x, 'family'])) if e == 1 else sorted(set(domain.family))
        assert len(families) == (252 if e == 1 else 220)
        item['eligible_families'] = families
        perm = np.random.default_rng(seed(e, 0, 0)).permutation(families).tolist()
        item['family_permutation'] = perm
        n = 40 if e == 1 else 30
        g, cal = EVAL[exp][-1], CAL[exp]
        for name, fs in ((g, perm[:n]), (cal, perm[n:n+20])):
            item[name + '_families'] = fs
            item[name] = sorted(domain.loc[domain.family.isin(fs), 'sample_id'].astype(int))
        item['pool'] = sorted(set(domain.sample_id) - holdouts(exp, item))
        for k in range(1, 31):
            s0 = np.random.default_rng(seed(e, 1, k)).choice(item['pool'], 100, replace=False).tolist()
            item[f'S0_{k}'] = s0
            item[f'R_{k}'] = np.random.default_rng(seed(e, 2, k)).choice(sorted(set(item['pool'])-set(s0)), 120, replace=False).tolist()
    validate_split(df, split)
    return split


def validate_split(df, split):
    all_ids = set(df.sample_id)
    assert len(df) == len(all_ids) == 40616 and df.family.nunique() == 291
    assert sorted(df.T_C.unique()) == [25, 50, 70, 90]
    assert sorted(df.fset.unique()) == config()['expected_design_counts']['frequency_setpoints_kHz']
    assert ((df.fset >= 300) == (df.frequency_Hz >= 300000)).all()
    for exp in CAL:
        item = split[exp]
        groups = [set(item[n]) for n in (*EVAL[exp], CAL[exp], 'pool')]
        assert sum(map(len, groups)) == len(set.union(*groups)) == len(df)
        assert set.union(*groups) == all_ids
        for name in (*EVAL[exp], CAL[exp], 'pool'):
            assert item[name] == sorted(set(item[name]))
        g, cal = EVAL[exp][-1], CAL[exp]
        domain = df if exp == 'E1' else df[df.sample_id.isin(item['S'])]
        for name, n in ((g, 40 if exp == 'E1' else 30), (cal, 20)):
            assert len(set(item[name+'_families'])) == n
            assert set(domain.loc[domain.family.isin(item[name+'_families']), 'sample_id']) == set(item[name])
        assert not set(item[g+'_families']) & set(item[cal+'_families'])
        assert len(item['pool']) >= (21972 if exp == 'E1' else 12892)
        for k in range(1, 31):
            s0, r = item[f'S0_{k}'], item[f'R_{k}']
            assert len(s0) == len(set(s0)) == 100 and set(s0) <= set(item['pool'])
            assert len(r) == len(set(r)) == 120 and set(r) <= set(item['pool'])-set(s0)
    indexed = df.set_index('sample_id', drop=False)
    assert len(split['E1']['X7']) == 632
    assert indexed.loc[split['E1']['X7'], 'family'].nunique() == 39
    for name, n, families in [('S', 25122, 220), ('XF', 5361, 69), ('XT', 8345, 217), ('XFT', 1788, 67)]:
        assert len(split['E2'][name]) == n and indexed.loc[split['E2'][name], 'family'].nunique() == families
    assert indexed.loc[split['E2']['pool'], 'family'].nunique() == 170


def build(allow_missing_sources=False):
    verify_sources(allow_missing_sources)
    c = config()
    df = family_features(pd.read_csv(FEATURE_PATH, usecols=c['data']['feature_design_columns'])).sort_values('sample_id')
    split = generate_split(df)
    summary = dict(H=H, prereg_sha=PREREG_SHA, config_sha256=CONFIG_SHA,
                   prereg_sha256=sha(ROOT/'docs/prereg/M9_magnet_round8_prereg.md'),
                   model_sha256=MODEL_SHA, features_sha256=sha(FEATURE_PATH), experiments={})
    for e, exp in enumerate(CAL, 1):
        item = split[exp]
        df[f'{exp}_bin'], edges = equal_bins(df.dBdt, df.loc[df.sample_id.isin(item['pool']), 'dBdt'])
        sets = {}
        indexed = df.set_index('sample_id', drop=False)
        for name, values in item.items():
            sets[name] = dict(n=len(values), sha256=digest(values))
            if values and isinstance(values[0], int):
                sets[name]['families'] = int(indexed.loc[values, 'family'].nunique())
        summary['experiments'][exp] = dict(sets=sets, dBdt_edges=edges, gp_seed=gp_seed(e),
            family_seed=seed(e, 0, 0), S0_seeds=[seed(e, 1, k) for k in range(1, 31)],
            R_seeds=[seed(e, 2, k) for k in range(1, 31)])
    content = df.to_csv(index=False, float_format='%.17g', lineterminator='\n').encode('utf-8')
    summary.update(design_sha256=hashlib.sha256(content).hexdigest(), split_sha256=digest(split))
    return df.set_index('sample_id', drop=False), split, content, summary


def load_design(allow_missing_sources=False):
    df, split, content, summary = build(allow_missing_sources)
    for path, data in artifacts(split, content, summary):
        assert path.read_bytes() == data, f'Design mismatch: {path}'
    return df, split


def artifacts(split, content, summary):
    return [(OUT/'design.csv', content), (OUT/'split.json', encoded(split)), (STAGE/'split_summary.json', encoded(summary))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--allow-missing-sources', action='store_true')
    args = ap.parse_args()
    _, split, content, summary = build(args.allow_missing_sources)
    for path, data in artifacts(split, content, summary):
        if args.verify:
            assert path.read_bytes() == data, f'Design mismatch: {path}'
        else:
            freeze(path, data)
    print('R8 input-only design verified.' if args.verify else 'R8 input-only design frozen.')


if __name__ == '__main__':
    main()
