#!/usr/bin/env python3
"""独立复核逐点区间和配对判据；仅显式 --export 导出正式案例。"""
from dclink_active5 import ROOT,OUT,STAGE,verify,freeze,freeze_bytes
from dclink_case3 import cli,record
import json
import sys
import subprocess
import numpy as np
import pandas as pd

def independent_check(m,df):
    arms=[f'{x}{k}' for k in range(1,7) for x in 'AMR']
    assert set(df.arm)==set(arms) and set(df.method)=={'m0','m1','m2'}
    assert not df.duplicated(['arm','method','case_id']).any()
    primary={}; means={}
    for (arm,method),block in df.groupby(['arm','method']):
        assert set(block['split'])=={'calib','T5','C5','D5','test','ood_corner','ood_dt3','supplement_corner','supplement_dt3'}
        cal=block[block['split']=='calib']; assert len(cal)==60 and (block.sigma>0).all()
        q=float(np.sort(abs(cal.y-cal.prediction)/cal.sigma)[54])
        assert np.isclose(q,m[f'{arm}.{method}.calib.q'],atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(block.lower,block.prediction-q*block.sigma,atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(block.upper,block.prediction+q*block.sigma,atol=1e-12,rtol=1e-12)
        groups=list(block.groupby('split'))
        groups.append(('supplement_ood',block[block['split'].isin(['supplement_corner','supplement_dt3'])]))
        for group,rows in groups:
            if group=='calib': continue
            key=f'{arm}.{method}.{group}'
            covered=int(((rows.y>=rows.lower)&(rows.y<=rows.upper)).sum())
            width=float((rows.upper-rows.lower).mean()); err=rows.prediction-rows.y
            calculated=dict(n=len(rows),covered=covered,mean_width=width,coverage=covered/len(rows),
                            mae=float(abs(err).mean()),bias=float(err.mean()),max_abs_error=float(abs(err).max()))
            for metric,v in calculated.items(): assert np.isclose(m[key+'.'+metric],v,rtol=1e-12,atol=1e-12),(key,metric)
            if method=='m2' and group in ('T5','C5','D5'): primary[arm,group]=(len(rows),covered,width)
            if method=='m2' and group in ('C5','D5','ood_corner','ood_dt3'):
                rows=rows.sort_values('case_id')
                score=rows.upper-rows.lower+20*(np.maximum(rows.lower-rows.y,0)+np.maximum(rows.y-rows.upper,0))
                means[arm,group]=float(score.mean())
                assert np.isclose(m[key+'.mean_winkler'],means[arm,group],atol=1e-12,rtol=1e-12)
    passes={}
    for arm in arms:
        c=[]
        for label,group,n,threshold in [('C1','T5',60,48),('C2-corner','C5',40,32),('C2-dt3','D5',40,32)]:
            size,covered,width=primary[arm,group]; assert size==n
            passed=covered>=threshold and (group=='T5' or width<=3*primary[arm,'T5'][2])
            assert passed==m[f'{arm}.criterion.{label}.pass']; c.append(passed)
        passes[arm]=all(c); assert passes[arm]==m[f'{arm}.criterion.overall']
    cv={}
    for x in 'AMR':
        count=sum(passes[f'{x}{k}'] for k in range(1,7)); cv[x]=count>=5
        assert count==m[f'CV-{x}.count'] and cv[x]==m[f'CV-{x}.pass']
    enabled=True; rejected=[]
    for h in range(1,5):
        diffs=[]
        for k in range(1,7):
            ac,mc,rc,ad,md=[means[f'{x}{k}',g] for x,g in [('A','C5'),('M','C5'),('R','C5'),('A','D5'),('M','D5')]]
            diffs.append([rc-ac,rc-mc,1.10*ac-mc,ad-md][h-1])
            assert np.isclose(diffs[-1],m[f'H{h}.d{k}'],atol=1e-12,rtol=1e-12)
        # Independent enumeration by bit masks, inclusive ties and identity.
        observed=sum(diffs)/6
        exceed=0
        for mask in range(64):
            perm=sum(d*(1 if mask&(1<<i) else -1) for i,d in enumerate(diffs))/6
            exceed+=perm>=observed-1e-12
        p=exceed/64
        status=('rejected' if p<.05 else 'not_rejected') if enabled else 'not_tested'
        assert p==m[f'H{h}.pvalue'] and status==m[f'H{h}.status']
        assert np.isclose(observed,m[f'H{h}.mean_difference'],atol=1e-12,rtol=1e-12)
        passed=status=='rejected'; assert passed==m[f'H{h}.rejected']
        rejected.append(passed); enabled=enabled and passed
    for key,value in zip(('claim_A','claim_M','claim_M_noninf','claim_M_dt3'),
                         (rejected[0] and cv['A'],rejected[1] and cv['M'],rejected[2],rejected[3])):
        assert m[key]==value,key
    return dict(verified=True,rows=len(df),arms=18)

def verify_sampling(m,arms):
    for arm,rows in arms.items():
        assert len(rows)==110
        expected={'corner':int(((rows.load<=.35)&(rows.bw_iac_khz<=75)).sum()),
                  'dt3':int((rows.dead_time_us==3).sum()),'low_load':int((rows.load<=.35).sum())}
        expected.update({f'dead_time_{c:.1f}':int((rows.dead_time_us==c).sum()) for c in np.arange(0,3.5,.5)})
        for key,value in expected.items(): assert m[f'{arm}.sampled.{key}']==value
    assert m['report.M.dt3_le27_count']==sum(m[f'M{k}.sampled.dt3']<=27 for k in range(1,7))
    cover=[m[f'R{k}.m2.C5.covered'] for k in range(1,7)]
    assert m['report.R.C5.covered.mean']==float(np.mean(cover))
    assert m['report.R.C5.covered.std']==float(np.std(cover,ddof=1))

def verify_results():
    from dclink_surrogate5 import run,load_inputs
    assert (STAGE/'first').exists(), 'No first results to verify'
    run(verify())
    m=json.loads((OUT/'surrogate_metrics.json').read_text())
    df=pd.read_csv(OUT/'predictions.csv',float_precision='round_trip')
    _,arms=load_inputs(); verify_sampling(m,arms)
    result=independent_check(m,df)
    for name in ('surrogate_metrics.json','predictions.csv','surrogate_metadata.json'):
        assert (OUT/name).read_bytes()==(STAGE/'first'/name).read_bytes()
    print(json.dumps(result,ensure_ascii=False))

def train():
    from dclink_surrogate5 import inputs
    marker=STAGE/'surrogate_training_run.json'
    if marker.exists():
        subprocess.run([sys.executable,'scripts/dclink_surrogate5.py'],cwd=ROOT,check=True); return
    rid=record('dclink-round5-first',[str(p.relative_to(ROOT)) for p in inputs()],
               [sys.executable,'scripts/dclink_surrogate5.py'],'data/dclink5/surrogate_evidence_metrics.json')
    freeze(marker,dict(run_id=rid))

def build_report(m,rid):
    claims=[]
    lines=['# DC-link 第五轮证据报告','','以 S0 为条件的六组配对比较；固定顺序 H1→H2→H3→H4。旧留出集、M0/M1 只报告。','']
    for h in range(1,5): lines.append(f'- H{h}：{m[f"H{h}.status"]}；名义 p={m[f"H{h}.pvalue"]}。')
    for key,value in m.items():
        if not isinstance(value,(bool,int,float)): continue
        cid=f'c{len(claims)}'
        claims.append(dict(id=cid,kind='metric',text=key,value=float(value),unit='原指标单位',run_id=rid,metric_key=key,tol_abs=0,tol_rel=1e-6))
        lines.append(f'- `{key}`：{float(value):.10g}⟦c:{cid}⟧')
    return claims,('\n'.join(lines)+'\n').encode()

def export():
    verify_results()
    rid=json.loads((STAGE/'surrogate_training_run.json').read_text())['run_id']
    validation=record('dclink-round5-verification',['scripts/dclink_case5.py','data/dclink5/predictions.csv','data/dclink5/surrogate_metrics.json'],[sys.executable,'scripts/dclink_case5.py','--verify-results'])
    tests=record('dclink-round5-tests',['tests/test_dclink_round5.py'],[sys.executable,'-m','unittest','discover','-s','tests','-p','test_dclink_round5.py','-v'])
    artifacts=record('dclink-round5-artifacts',['scripts/dclink_sweep5.py','scripts/dclink_figures5.py','lab/cases/dclink5/first/provenance.json',
                     'docs/figures/r5_corner.png','docs/figures/r5_dt3.png','docs/figures/r5_coverage_sampling.png'],[sys.executable,'scripts/dclink_active5.py'])
    claims,report=build_report(json.loads((OUT/'surrogate_metrics.json').read_text()),rid)
    freeze(STAGE/'claims.json',claims); freeze_bytes(STAGE/'report.md',report)
    runs=[r for r in [rid,validation,tests,artifacts] if not (ROOT/'cases/dclink_surrogate5/runs'/r).exists()]
    cli('export-case','cases/dclink_surrogate5','--runs',*runs,'--claims','lab/cases/dclink5/claims.json','--report','lab/cases/dclink5/report.md')
    subprocess.run([sys.executable,'-m','lab.evidence','check','cases/dclink_surrogate5'],cwd=ROOT,check=True)

if __name__=='__main__':
    verify()
    if sys.argv[1:]==['--train']: train()
    elif sys.argv[1:]==['--verify-results']: verify_results()
    elif sys.argv[1:]==['--export']: export()
    else: raise SystemExit('Use --train, --verify-results or --export.')
