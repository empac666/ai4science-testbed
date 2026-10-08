#!/usr/bin/env python3
"""第四轮 evidence 接线及独立逐点核对；只在显式 --export 时导出。"""
from dclink_active4 import ROOT,OUT,STAGE,verify,freeze,freeze_bytes
from dclink_case3 import cli,record
import json
import sys
import subprocess
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

def independent_check(m,df):
    for (arm,method,group),rows in df.groupby(['arm','method','split']):
        key=f'{arm}.{method}.{group}'; q=m[f'{arm}.{method}.calib.q']
        np.testing.assert_allclose(rows.lower,rows.prediction-q*rows.sigma,atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(rows.upper,rows.prediction+q*rows.sigma,atol=1e-12,rtol=1e-12)
        if group=='calib':
            assert len(rows)==60 and np.isclose(np.sort(abs(rows.y-rows.prediction)/rows.sigma)[54],q,atol=1e-12)
        else:
            assert int(((rows.y>=rows.lower)&(rows.y<=rows.upper)).sum())==m[key+'.covered']
            assert np.isclose((rows.upper-rows.lower).mean(),m[key+'.mean_width'])
    random=[f'RS{i}' for i in range(1,6)]; scores={}
    for arm,rows in df[(df.method=='m2')&(df['split']=='ood_corner')].groupby('arm'):
        rows=rows.sort_values('case_id')
        scores[arm]=(rows.upper-rows.lower+20*np.maximum(rows.lower-rows.y,0)+20*np.maximum(rows.y-rows.upper,0)).to_numpy()
    cover=lambda arm:m[f'{arm}.m2.ood_corner.covered']
    mean_random=np.mean([scores[a] for a in random],axis=0)
    p=1. if np.array_equal(scores['A'],mean_random) else float(wilcoxon(scores['A'],mean_random,alternative='less',zero_method='wilcox',method='auto',correction=False).pvalue)
    c={}
    for arm in ['A','M','R',*random]:
        c[arm]=all(m[f'{arm}.m2.{g}.covered']>=n and (g=='test' or m[f'{arm}.m2.{g}.mean_width']<=3*m[f'{arm}.m2.test.mean_width']) for g,n in [('test',48),('ood_corner',32),('ood_dt3',32)])
        assert c[arm]==m[f'{arm}.criterion.overall']
    checks={'A-1':all(scores['A'].mean()<scores[a].mean() for a in random),
            'A-2':all(cover('A')>=cover(a) for a in random) and cover('A')-np.mean([cover(a) for a in random])>=4,
            'A-3':p<.05,'M-0':m['M.sampled.dt3']<=27,'M-1':c['M'],
            'M-2':cover('M')>=36 and all(scores['M'].mean()<scores[a].mean() for a in random)}
    checks['H-A']=all(checks[k] for k in ('A-1','A-2','A-3')); checks['H-M']=all(checks[k] for k in ('M-0','M-1','M-2'))
    for key,value in checks.items(): assert bool(value)==m[f'criterion.{key}.pass'],key
    assert np.isclose(p,m['criterion.A-3.pvalue'],atol=1e-14)
    return dict(verified=True,rows=len(df),hypotheses=checks)

def verify_results():
    from dclink_surrogate4 import run
    run(verify())
    m=json.loads((OUT/'surrogate_metrics.json').read_text()); df=pd.read_csv(OUT/'predictions.csv',float_precision='round_trip')
    random=pd.read_csv(OUT/'sweep_random.csv')
    from dclink_active4 import R3
    arms=dict(A=pd.read_csv(R3/'sweep_active.csv'),R=pd.read_csv(R3/'sweep_base.csv').query('group == \"R\"'),
              M=pd.read_csv(OUT/'sweep_mixed.csv'),**{f'RS{i}':random[random.group==f'RS{i}'] for i in range(1,6)})
    for arm,rows in arms.items():
        assert len(rows)==110
        assert int((rows.dead_time_us==3).sum())==m[f'{arm}.sampled.dt3']
        assert int(((rows.load<=.35)&(rows.bw_iac_khz<=75)).sum())==m[f'{arm}.sampled.corner']
        assert int((rows.load<=.35).sum())==m[f'{arm}.sampled.low_load']
        for c in np.arange(0,3.5,.5): assert int((rows.dead_time_us==c).sum())==m[f'{arm}.sampled.dead_time_{c:.1f}']
    result=independent_check(m,df)
    for name in ('surrogate_metrics.json','predictions.csv','surrogate_metadata.json'):
        assert (OUT/name).read_bytes()==(STAGE/'first'/name).read_bytes()
    print(json.dumps(result,default=bool,ensure_ascii=False))

def train():
    from dclink_surrogate4 import inputs
    marker=STAGE/'surrogate_training_run.json'
    if marker.exists():
        subprocess.run([sys.executable,'scripts/dclink_surrogate4.py'],cwd=ROOT,check=True); return
    paths=[str(p.relative_to(ROOT)) for p in inputs()]
    rid=record('dclink-round4-first',paths,[sys.executable,'scripts/dclink_surrogate4.py'],'data/dclink4/surrogate_evidence_metrics.json')
    freeze(marker,dict(run_id=rid))

def build_report(m,rid):
    claims=[]
    lines=['# DC-link 第四轮证据报告','','H-A：'+('通过' if m['criterion.H-A.pass'] else '不通过')+'；H-M：'+('通过' if m['criterion.H-M.pass'] else '不通过')+'。',
           '两项假设分别判定，不作总判定或多重比较校正。A 是已知固定比较对象；第三轮 R 已看过，仅报告。M0/M1 及第二轮补充集仅报告。','']
    for key,value in m.items():
        cid=f'c{len(claims)}'; claims.append(dict(id=cid,kind='metric',text=key,value=float(value),unit='原指标单位',run_id=rid,metric_key=key,tol_abs=0,tol_rel=1e-6))
        lines.append(f'- `{key}`：{float(value):.10g}⟦c:{cid}⟧')
    return claims,('\n'.join(lines)+'\n').encode()

def export():
    rid=json.loads((STAGE/'surrogate_training_run.json').read_text())['run_id']
    validation=record('dclink-round4-verification',['scripts/dclink_case4.py','data/dclink4/predictions.csv','data/dclink4/surrogate_metrics.json'],[sys.executable,'scripts/dclink_case4.py','--verify-results'])
    tests=record('dclink-round4-tests',['tests/test_dclink_round4.py'],[sys.executable,'-m','unittest','discover','-s','tests','-p','test_dclink_round4.py','-v'])
    artifacts=record('dclink-round4-artifacts',['scripts/dclink_sweep4.py','scripts/dclink_figures4.py','lab/cases/dclink4/first/provenance.json','docs/figures/r4_corner.png','docs/figures/r4_sampling.png','docs/figures/r4_test_dt3.png'],[sys.executable,'scripts/dclink_active4.py'])
    claims,report=build_report(json.loads((OUT/'surrogate_metrics.json').read_text()),rid)
    freeze(STAGE/'claims.json',claims); freeze_bytes(STAGE/'report.md',report)
    runs=[r for r in [rid,validation,tests,artifacts] if not (ROOT/'cases/dclink_surrogate4/runs'/r).exists()]
    cli('export-case','cases/dclink_surrogate4','--runs',*runs,'--claims','lab/cases/dclink4/claims.json','--report','lab/cases/dclink4/report.md')
    subprocess.run([sys.executable,'-m','lab.evidence','check','cases/dclink_surrogate4'],cwd=ROOT,check=True)

if __name__=='__main__':
    verify()
    if sys.argv[1:]==['--train']: train()
    elif sys.argv[1:]==['--verify-results']: verify_results()
    elif sys.argv[1:]==['--export']: export()
    else: raise SystemExit('Use --train, --verify-results or --export; no implicit formal export.')
