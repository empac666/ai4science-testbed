"""Unique commit-bound, input-only R9 preflight and immutable masks."""
from magnet9_common import *
import argparse


def family_features(df):
    df = df.copy()
    f = np.sort(df.frequency_Hz.unique())
    assert (f > 0).all()
    groups = np.split(f, np.flatnonzero(np.log(f[1:]/f[:-1]) > .01)+1)
    mapping = {x: int(round(float(np.median(g))/1000)) for g in groups for x in g}
    df['fset'] = df.frequency_Hz.map(mapping)
    df['family'] = [f'{f}_{w}_{round(10*d)}_{round(20*p)}'
                    for f,w,d,p in zip(df.fset,df.waveform,df.duty,df.plateau)]
    df['v'] = np.log10(4*df.frequency_Hz*df.amplitude_T)
    return df.sort_values('sample_id').set_index('sample_id', drop=False)


def subsets(df, ids, direction):
    rows = df.loc[ids]
    core = rows.fset <= 199 if direction == 'F' else rows.T_C <= 50
    return rows.loc[core, 'sample_id'].astype(int).tolist(), rows.loc[~core, 'sample_id'].astype(int).tolist()


def describe(df, ids):
    rows = df.loc[ids]
    return dict(n=len(ids), families=int(rows.family.nunique()), fsets=sorted(map(int, rows.fset.unique())),
                temperatures=sorted(map(int, rows.T_C.unique())), sha256=digest(ids))


def build():
    c = config()
    source_checks = verify_sources()  # byte hashing only, no label parsing
    df = family_features(pd.read_csv(FEATURE_PATH, usecols=c['data']['design_columns']))
    ids = lambda mask: df.loc[mask, 'sample_id'].astype(int).tolist()
    low, cool = df.fset < 300, df.T_C <= 70
    split = dict(S=ids(low & cool), XF=ids(~low & cool), XT=ids(low & ~cool), XFT=ids(~low & ~cool))
    families = sorted(df.loc[split['S'], 'family'].unique())
    permutation = np.random.default_rng(seed(0, 0)).permutation(families).tolist()
    split['family_permutation'] = permutation
    for name, fs in (('G9', permutation[:30]), ('CAL9', permutation[30:50])):
        split[name+'_families'] = fs
        split[name] = ids(df.index.isin(split['S']) & df.family.isin(fs))
    split['pool'] = sorted(set(split['S'])-set(split['G9'])-set(split['CAL9']))
    split['pseudo'] = {j: dict(zip(('core', 'edge'), subsets(df, split['S'], j))) for j in ('F', 'T')}
    summary = dict(prereg_sha=PREREG_SHA, H=H, gp_seed=GP_SEED,
        approval='User R9c explicitly authorized direct offline execution on feat/r9-honest-extrap.',
        deliverables={p: sha(ROOT/p) for p in c['freeze']['effective_deliverables']},
        sources=source_checks, versions=versions(), seed_audit=seed_audit(),
        family_seed=seed(0, 0), S0_seeds=[seed(1,k) for k in range(1,31)],
        sets={z: describe(df, split[z]) for z in ('S','G9','CAL9','pool','XF','XT','XFT')},
        assertions=[], label_reads=0, model_fits=0, created_at=now())
    def check(name, actual, expected):
        summary['assertions'].append(dict(name=name, actual=actual, expected=expected, passed=actual == expected))
    check('unique rows', [len(df), int(df.sample_id.nunique()), int(df.family.nunique())], [40616,40616,291])
    check('temperatures', sorted(map(int,df.T_C.unique())), [25,50,70,90])
    check('fsets', sorted(map(int,df.fset.unique())), c['expected_design_counts']['frequency_setpoints_kHz'])
    check('raw boundary mismatch', int(((df.fset>=300)!=(df.frequency_Hz>=300000)).sum()), 0)
    for z in ('S','XF','XT','XFT'):
        check(z, [len(split[z]), int(df.loc[split[z],'family'].nunique())], [c['regions'][z]['n'],c['regions'][z]['families']])
    for z,n in [('G9',30),('CAL9',20),('pool',170)]:
        check(z+' families', int(df.loc[split[z],'family'].nunique()), n)
    groups = [set(split[z]) for z in ('pool','G9','CAL9','XF','XT','XFT')]
    check('disjoint partition', sum(map(len,groups)) == len(set.union(*groups)) == len(df), True)
    check('P minimum', len(split['pool']) >= 12892, True)
    summary['cal_edges'] = {}
    summary['pool_strata'] = {}
    strata = []
    for prefix, edge in [('core',False),('edge',True)]:
        for t, quota in [(25,16),(50,17),(70,17)]:
            mask = (df.fset>199 if edge else df.fset<=199) & (df.T_C==t)
            name = f'{prefix}_{t}'
            support = ids(mask & df.index.isin(split['S']))
            pool = ids(mask & df.index.isin(split['pool']))
            check('S '+name, len(support), c['expected_design_counts']['support_six_strata'][name])
            check('P '+name+' quota feasible', len(pool) >= quota, True)
            summary['pool_strata'][name] = dict(n=len(pool), quota=quota)
            strata.append((set(pool),quota))
    for j in ('F','T'):
        core, edge = subsets(df, split['S'], j)
        cc = c['pseudo_extrapolation']['directions'][j]
        check('pseudo '+j, [len(core),len(edge),int(df.loc[core,'family'].nunique()),int(df.loc[edge,'family'].nunique())],
              [cc['core_n'],cc['edge_n'],cc['core_families'],cc['edge_families']])
        caledge = subsets(df, split['CAL9'], j)[1]
        summary['cal_edges'][j] = describe(df, caledge)
        check('CAL edge '+j+' >=20 points >=2 families', len(caledge)>=20 and df.loc[caledge,'family'].nunique()>=2, True)
    failed = [x for x in summary['assertions'] if not x['passed']]
    split['S0'], split['common_permutations'] = {}, {}
    # A failing split is archived immediately without further random design or fits.
    if not failed:
        for k in range(1,31):
            order = np.random.default_rng(seed(1,k)).permutation(split['pool']).tolist()
            split['common_permutations'][str(k)] = order
            split['S0'][f'U{k:02d}'] = order[:100]
            selected = set().union(*(set([i for i in order if i in pool][:quota]) for pool,quota in strata))
            split['S0'][f'S{k:02d}'] = [i for i in order if i in selected]
            assert len(selected) == 100
        lo, hi = df.loc[split['pool'],'v'].min(), df.loc[split['pool'],'v'].max()
        assert hi > lo
        df['v_bin'] = np.clip(np.floor(8*(df.v-lo)/(hi-lo)),0,7).astype(int)
        summary['v_edges'] = np.linspace(lo,hi,9).tolist()
    summary.update(status='infeasible_design_abort' if failed else 'input_preflight_passed',
                   failed_assertions=failed, split_sha256=digest(split))
    return df, split, summary


def load_design():
    verify_seal(STAGE/'design','EVALUATED')
    summary = read_json(STAGE/'design/summary.json')
    assert summary['status'] == 'input_preflight_passed'
    config()
    assert sha(FEATURE_PATH) == summary['sources']['data/magnet6/features.csv']
    df = family_features(pd.read_csv(FEATURE_PATH, usecols=config()['data']['design_columns']))
    split = read_json(STAGE/'design/split.json')
    assert digest(split) == summary['split_sha256']
    lo,hi = summary['v_edges'][0],summary['v_edges'][-1]
    df['v_bin'] = np.clip(np.floor(8*(df.v-lo)/(hi-lo)),0,7).astype(int)
    return df,split


def main():
    df, split, summary = build()
    folder = STAGE/'design'
    freeze(folder/'split.json', encoded(split))
    freeze(folder/'summary.json', encoded(summary))
    # Full global family mapping and input masks retained independently of labels.
    freeze(folder/'inputs.csv', df.to_csv(index=False,float_format='%.17g').encode())
    seal(folder,'EVALUATED',[folder/'split.json',folder/'summary.json',folder/'inputs.csv'],stage='input_only')
    append('./ai4s_r9_status.md', f"{summary['status']} H={H} failures={summary['failed_assertions']}")
    print(json.dumps({k:summary[k] for k in ('H','gp_seed','status','sets','cal_edges','failed_assertions')},ensure_ascii=False,indent=2))
    if summary['failed_assertions']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
