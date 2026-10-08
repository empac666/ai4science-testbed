#!/usr/bin/env python3
"""数据完成后经 lab.repro 记录、中文报告并导出第三轮证据。"""
import json
import sys
import subprocess
from dclink_design3 import ROOT,OUT,STAGE,freeze
PYTHON=sys.executable

def cli(*args):
    r=subprocess.run([PYTHON,'-m','lab.repro',*map(str,args)],cwd=ROOT,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stdout+'\n'+r.stderr)
    return r.stdout

def record(name,inputs,command,metrics=None):
    args=['run','--name',name,'--inputs',*inputs]
    if metrics: args+=['--metrics-from',metrics]
    return json.loads(cli(*args,'--',*command))['run_id']

def train():
    marker=STAGE/'surrogate_training_run.json'
    if marker.exists():
        subprocess.run([PYTHON,'scripts/dclink_surrogate3.py'],cwd=ROOT,check=True); return
    inputs=['scripts/dclink_surrogate3.py','scripts/dclink_surrogate2.py','scripts/dclink_surrogate.py','scripts/dclink_active3.py',
            'scripts/dclink_design3.py','data/dclink3/sweep_base.csv','data/dclink3/sweep_active.csv','lab/cases/dclink2/sweep_nonideal.csv',
            'data/dclink3/design.json','data/dclink3/pool.json','data/dclink3/split.json','lab/cases/dclink3/config_prerun.json',
            'lab/cases/dclink3/split_manifest.json','docs/prereg/M4_surrogate_round3_prereg.md']
    inputs += [f'data/dclink3/active/batch_{b}.json' for b in range(1,6)]
    rid=record('dclink-round3-first',inputs,[PYTHON,'scripts/dclink_surrogate3.py'],'data/dclink3/surrogate_evidence_metrics.json')
    freeze(marker,dict(run_id=rid))

def verify_results():
    import numpy as np
    import pandas as pd
    from dclink_surrogate3 import criteria,paired,winkler
    m=json.loads((OUT/'surrogate_metrics.json').read_text()); df=pd.read_csv(OUT/'predictions.csv')
    for (arm,method,group),r in df.groupby(['arm','method','split']):
        key=f'{arm}.{method}.{group}'
        if group=='calib':
            assert len(r)==60 and np.isclose(np.sort(abs(r.y-r.prediction)/r.sigma)[54],m[key+'.q'])
        else:
            assert int(((r.y>=r.lower)&(r.y<=r.upper)).sum())==m[key+'.covered']
            assert np.isclose((r.upper-r.lower).mean(),m[key+'.mean_width'])
    for arm in ('active','random'):
        for k,v in criteria(m,arm).items(): assert m[k]==v
    r=df[(df.method=='m2')&(df['split']=='ood_corner')]
    scores=[]
    for arm in ('active','random'):
        p=r[r.arm==arm].sort_values('case_id'); scores.append(winkler(p.y.to_numpy(),p.lower.to_numpy(),p.upper.to_numpy()))
    assert np.isclose(paired(*scores)['pvalue'],m['comparison.P-b.pvalue'])
    assert m['criterion.overall']==(m['active.criterion.overall'] and m['comparison.P-a.pass'] and m['comparison.P-b.pass'])
    for name in ('surrogate_metrics.json','predictions.csv','surrogate_metadata.json'):
        assert (OUT/name).read_bytes()==(STAGE/'first'/name).read_bytes()
    print('第三轮逐点区间、校准秩、配对检验及首次副本核对通过')

def main():
    rid=json.loads((STAGE/'surrogate_training_run.json').read_text())['run_id']
    validation=record('dclink-round3-verification',['scripts/dclink_case3.py','data/dclink3/predictions.csv','data/dclink3/surrogate_metrics.json'],
                      [PYTHON,'scripts/dclink_case3.py','--verify-results'])
    tests=record('dclink-round3-tests',['tests/test_dclink_round3.py'],[PYTHON,'-m','unittest','discover','-s','tests','-p','test_dclink_round3.py','-v'])
    art=record('dclink-round3-artifacts',['scripts/dclink_sweep3.py','scripts/dclink_figures3.py','lab/cases/dclink3/first/provenance.json',
               'docs/figures/r3_coverage_width.png','docs/figures/r3_sampling_map.png','docs/figures/r3_corner_winkler.png'],
               [PYTHON,'scripts/dclink_design3.py','--verify'])
    m=json.loads((OUT/'surrogate_metrics.json').read_text()); claims=[]
    lines=['# DC-link 第三轮证据报告','','总判定：'+('通过' if m['criterion.overall'] else '不通过')+'。',
           '主判据使用非理想数据 M2；两臂共用校准与评估集。M0/M1 与第二轮补充集只报告。',
           '共享校准的误杀模拟只涉及覆盖秩；可交换性本身不确定宽度分布，因此不冒称模拟了宽度条件。','']
    for key,value in m.items():
        cid=f'c{len(claims)}'
        claims.append(dict(id=cid,kind='metric',text=key,value=float(value),unit='原指标单位',run_id=rid,metric_key=key,tol_abs=0,tol_rel=1e-6))
        lines.append(f'- `{key}`：{float(value):.10g}⟦c:{cid}⟧')
    freeze(STAGE/'claims.json',claims)
    from dclink_design3 import freeze_bytes
    freeze_bytes(STAGE/'report.md',('\n'.join(lines)+'\n').encode())
    runs=[rid,validation,tests,art]; new=[r for r in runs if not (ROOT/'cases/dclink_surrogate3/runs'/r).exists()]
    cli('export-case','cases/dclink_surrogate3','--runs',*new,'--claims','lab/cases/dclink3/claims.json','--report','lab/cases/dclink3/report.md')
    subprocess.run([PYTHON,'-m','lab.evidence','check','cases/dclink_surrogate3'],cwd=ROOT,check=True)
if __name__=='__main__':
    if sys.argv[1:]==['--train']: train()
    elif sys.argv[1:]==['--verify-results']: verify_results()
    else: main()
