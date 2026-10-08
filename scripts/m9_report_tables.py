"""Read sealed R8 summaries only; emit reproducible Markdown to stdout.

No fitting, prediction, acquisition replay, sign-flip enumeration, or file writes.
Uses stdlib, numpy and pandas only (no tabulate dependency).
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'lab/cases/magnet8'
SPECS = [
    ('H1', 'E1', 'X7', 'R', 'M', 'W_R−W_M'),
    ('H2', 'E1', 'X7', 'A', 'M', '1.10W_A−W_M'),
    ('H3', 'E2', 'XF', 'R', 'A', 'W_R−W_A'),
    ('H4', 'E2', 'XF', 'R', 'M', 'W_R−W_M'),
    ('H5', 'E2', 'XT', 'R', 'A', 'W_R−W_A'),
    ('H6', 'E2', 'XT', 'R', 'M', 'W_R−W_M'),
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(headers, rows):
    def line(row):
        return '| ' + ' | '.join(str(v).replace('|', '\\|') for v in row) + ' |'
    return '\n'.join([line(headers), line(['---'] * len(headers))] + [line(r) for r in rows])


def f(x):
    return f'{x:.6f}'


def pct(x):
    return f'{100*x:.2f}%'


def build_sections():
    p = read(STAGE / 'first/primary_evaluation.json')
    m = read(STAGE / 'first/metrics.json')
    c = read(STAGE / 'first/calibration.json')
    r = read(STAGE / 'first_recompute/independent_recompute.json')
    df = pd.read_csv(STAGE / 'first/arm_table.csv')
    final = df[df.checkpoint == df.checkpoint.max()].copy()
    final['method'] = final.arm.str[0]
    # Cross-check existing summaries, not independent scientific recomputation.
    for key in ('hypotheses', 'validity_pass_counts', 'conclusions', 'process_valid'):
        assert p[key] == m[key], key
    assert digest(STAGE / 'first/primary_evaluation.json') == m['primary_evaluation_sha256']
    assert digest(STAGE / 'first/calibration.json') == m['calibration_sha256']
    for name, expected in read(STAGE / 'first/EVALUATED').items():
        assert digest(STAGE / 'first' / name) == expected, name
    for row in df.itertuples():
        arm = m['arms'][row.exp][row.arm]
        cp = arm['checkpoints'][row.checkpoint]
        assert np.isclose(row.q, c['calibration'][row.exp][row.arm][row.checkpoint], rtol=0, atol=1e-12)
        for metric, value in cp['metrics'][row.set].items():
            assert np.isclose(getattr(row, metric), value, rtol=0, atol=1e-12), (row.exp, row.arm, metric)
    sections = {}
    sections['run'] = table(['封存字段', '值'], [
        ['生效预注册 SHA / H', f"{p['prereg_sha']} / {p['H']}"],
        ['完成臂数', sum(len(a) for a in m['arms'].values())],
        ['process_valid', p['process_valid']],
        ['A/M 采集重放臂数', len(p['replayed_arms'])],
        ['calibrate 封存时间', c['sealed_at']], ['evaluate 封存时间', p['sealed_at']],
    ])
    split=read(STAGE/'split_summary.json')
    sections['design']=table(['实验','集合','样本数','区域内族数'],[
        [exp,name,v['n'],v.get('families','—')]
        for exp,data in split['experiments'].items() for name,v in data['sets'].items()
        if not name.startswith(('S0_','R_')) and not name.endswith('_families') and name!='family_permutation'])
    sizes=final.groupby(['exp','set']).n.first()
    sections['thresholds']=table(['实验','集合','80% 覆盖数底线','90% 覆盖数参考'],[
        [exp,region,math.ceil(.8*n),math.ceil(.9*n)] for (exp,region),n in sizes.items()])
    rows = []
    for h, exp, region, baseline, target, definition in SPECS:
        v = p['hypotheses'][h]
        d = np.asarray(v['d_k'])
        get = lambda method: np.array([m['arms'][exp][f'{method}{k}']['metrics'][region]['winkler'] for k in range(1, len(d)+1)])
        base, dest = get(baseline), get(target)
        np.testing.assert_allclose(d, (1.1 if h == 'H2' else 1)*base-dest, rtol=0, atol=1e-12)
        assert v['numerator'] == r['hypotheses'][h]['numerator']
        assert v['denominator'] == 2**len(d)
        np.testing.assert_allclose([d.mean(), np.median(d), np.percentile(d,75)-np.percentile(d,25)], [v['mean'],v['median'],v['IQR']], rtol=0, atol=1e-12)
        rows.append([h, exp+' '+region, definition, f(d.mean()), f(np.median(d)), f(v['IQR']),
                     f"{(d>0).sum()}/{(d==0).sum()}/{(d<0).sum()}",
                     f"{v['numerator']}/2^{len(d)} = {v['p']:.10g}",
                     '正式拒绝' if v['status']=='rejected' else v['status'],
                     f(d.mean()/d.std(ddof=1)), pct(1-dest.mean()/base.mean())])
    sections['hypotheses'] = table(['假设','区域','d_k','均值','中位','IQR 宽度','正/零/负','精确 p','状态','δ','相对降幅'], rows)
    sections['pairs'] = table(['k']+[s[0] for s in SPECS], [[k+1]+[f(p['hypotheses'][h]['d_k'][k]) for h,*_ in SPECS] for k in range(len(p['hypotheses']['H1']['d_k']))])
    rows=[]
    for exp, methods in p['validity_pass_counts'].items():
        for method, counts in methods.items():
            n=len(final[(final.exp==exp)&(final.method==method)].arm.unique())
            for key,value in counts.items():
                arms=final[(final.exp==exp)&(final.method==method)].drop_duplicates('arm')
                assert int(arms['final_'+key].sum())==value
            rows.append([exp,method]+[f'{counts[x]}/{n}' if x in counts else '—' for x in ['C1','C2','CV','V80_F','V80_T','HONEST90_F','HONEST90_T']])
    sections['validity']=table(['实验','方法','C1','C2','CV','V80-F','V80-T','HONEST90-F','HONEST90-T'],rows)
    conditions=['H1 ∧ CV-M','H2 ∧ CV-M ∧ CV-A','H3 ∧ V-A(F) ∧ HONEST90(A,F)','H4 ∧ V-M(F) ∧ HONEST90(M,F)','H5 ∧ V-A(T) ∧ HONEST90(A,T)','H6 ∧ V-M(T) ∧ HONEST90(M,T)']
    sections['conclusions']=table(['结论','条件（H 指正式拒绝）','结果'],[[key,cond,'成立' if p['conclusions'][key] else '不成立'] for key,cond in zip(['M-X7','M-NI10-X7','A-F','M-F','A-T','M-T'],conditions)])
    rows=[]; ranges=[]; bias=[]
    for (exp,method,region), g in final.groupby(['exp','method','set'],sort=True):
        rows.append([exp,method,region,len(g)]+[pct(g[x].mean()) if x in ['coverage_fraction','relative_error'] else f(g[x].mean()) for x in ['winkler','width','coverage_fraction','relative_error','mae','bias','q']])
        ranges.append([exp,method,region,int(g.n.iloc[0]),f'{g.coverage.min()}–{g.coverage.max()}',pct(g.coverage_fraction.min())+'–'+pct(g.coverage_fraction.max()),pct(g.nominal90_shortfall.mean()),pct(g.nominal90_shortfall.max())])
        if exp=='E2':
            bias.append([method,region,f(g.bias.mean()),f(10**g.bias.mean()),pct(1-10**g.bias.mean())])
    sections['means']=table(['实验','方法','集合','臂数','Winkler','宽度','覆盖率','中位相对误差均值','MAE','偏差','q'],rows)
    sections['ranges']=table(['实验','方法','集合','每臂样本数','覆盖数最小–最大','覆盖率最小–最大','欠覆盖均值','欠覆盖最大'],ranges)
    sections['bias']=table(['方法','集合','平均 log10 偏差','几何平均预测/实测比','相应低估比例'],bias)
    rows=[]
    for exp in ('E1','E2'):
        cols=['C1','C2','CV'] if exp=='E1' else ['C1','V80_F','V80_T','HONEST90_F','HONEST90_T']
        g=final[final.exp==exp].drop_duplicates('arm')
        for row in sorted(g.to_dict('records'),key=lambda v:(int(v['arm'][1:]),v['arm'][0])):
            rows.append([exp,row['arm'],', '.join(x for x in cols if row['final_'+x]),', '.join(x for x in cols if not row['final_'+x]) or '无'])
    sections['arm_validity']=table(['实验','臂','通过条件','未通过条件'],rows)
    rows=[]
    for exp in ('E1','E2'):
        for part in ('S0','additions'):
            for method in 'AMR':
                s=m['sampling_counts'][exp][method][part]
                rows.append([exp,method,'S0' if part=='S0' else '新增',s['n']]+[s[x] if exp=='E2' else '—' for x in ['boundary_282','boundary_70','boundary_both','boundary_either']])
    sections['boundaries']=table(['实验','方法','来源','总采点次数','282 kHz','70 °C','两者交集','两者并集'],rows)
    text=[]
    for exp in ('E1','E2'):
        for dimension,label in [('fset','频率设定点（kHz）'),('T','温度（°C）'),('dBdt_bin','dB/dt 档')]:
            keys=sorted(set().union(*(m['sampling_counts'][exp][method]['additions'][dimension] for method in 'AMR')),key=float)
            rows=[]
            for key in keys:
                rows.append([key]+[m['sampling_counts'][exp][method][part][dimension].get(key,0) for part in ('S0','additions') for method in 'AMR'])
            text.append(f'**{exp} {label}：跨臂采点次数**\n\n'+table([label,'S0 A','S0 M','S0 R','新增 A','新增 M','新增 R'],rows))
    sections['sampling']='\n\n'.join(text)
    rows=[]
    for (exp,method,region),g in df.assign(method=df.arm.str[0]).groupby(['exp','method','set']):
        for metric,label in [('winkler','Winkler'),('coverage_fraction','覆盖率'),('relative_error','中位相对误差')]:
            values=g.groupby('checkpoint')[metric].mean()
            rows.append([exp,method,region,label]+[(pct(x) if metric!='winkler' else f(x)) for x in values])
    sections['learning']=table(['实验','方法','集合','指标']+[f'b={b}' for b in sorted(df.checkpoint.unique())],rows)
    rows=[]
    for exp, arms in m['arms'].items():
        first=next(iter(arms.values()))
        for variable,pool in first['pool_extrema'].items():
            rows.append([exp,'池',variable,f(pool['min']),f(pool['max'])])
            for method in 'AMR':
                ext=[a['checkpoints'][-1]['training_extrema'][variable] for name,a in arms.items() if name.startswith(method)]
                rows.append([exp,method+' 最终训练',variable,f'{min(v["min"] for v in ext):.6f}–{max(v["min"] for v in ext):.6f}',f'{min(v["max"] for v in ext):.6f}–{max(v["max"] for v in ext):.6f}'])
    sections['extrema']=table(['实验','来源','变量','逐臂最小值范围','逐臂最大值范围'],rows)
    sections['igse']=table(['集合','iGSE 中位相对误差（仅描述性）'],[[k,pct(v)] for k,v in m['igse_baseline'].items()])
    summary=r['comparison_summary']
    # Raw terminal logs are omitted from the public copy; check the structured result.
    assert summary['verified'] and summary['mismatch_count']==0
    sections['recompute']=table(['复算项目','结果'],[['总比较数',summary['total_comparisons']],['不一致数',summary['mismatch_count']]]+[[k,f'{v:.12g}'] for k,v in summary['max_abs_diff_by_category'].items()])
    paths=['docs/prereg/M9_magnet_round8_prereg.md','lab/cases/magnet8/config_prerun.json','lab/cases/magnet8/split_summary.json']+[f'lab/cases/magnet8/first/{x}' for x in ['primary_evaluation.json','metrics.json','arm_table.csv','calibration.json','EVALUATED']]+['lab/cases/magnet8/first_recompute/independent_recompute.json','docs/discussion/m9/reviewer_b_review.md','docs/discussion/m9/moderator_rulings.md','scripts/m9_report_tables.py','scripts/magnet8_figures.py']
    sections['evidence']=table(['文件路径','SHA256（当前文件字节）'],[[f'`{x}`',f'`{digest(ROOT/x)}`'] for x in paths])
    return sections


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--section', help='Emit one named section; default: all sections')
    args=parser.parse_args()
    sections=build_sections()
    if args.section:
        print(sections[args.section])
    else:
        for name,body in sections.items():
            print(f'<!-- BEGIN AUTO:{name} -->\n{body}\n<!-- END AUTO:{name} -->\n')


if __name__=='__main__':
    main()
