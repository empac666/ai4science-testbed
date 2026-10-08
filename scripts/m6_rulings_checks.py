#!/usr/bin/env python3
"""第五轮主持人独立复算：不调用 dclink_surrogate5 / dclink_active5 的评估与检验代码，按预注册直接重算 18 臂指标、CV、H1–H4 置换 p 与固定顺序。
输出 docs/reports/M6_rulings_checks.json。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
import json, itertools, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
exec(open(ROOT/'scripts/m4_rulings_checks.py').read().split("split=json.loads")[0])   # feats/kernel/fit/wink
D5=ROOT/'data/dclink5'; split=json.loads((ROOT/'data/dclink3/split.json').read_text())
old=pd.read_csv(ROOT/'lab/cases/dclink2/sweep_nonideal.csv'); s0=old[old.case_id.isin(split['s0'])]
b3=pd.read_csv(ROOT/'data/dclink3/sweep_base.csv'); calib=b3.set_index('case_id').loc[split['calib']]
base=pd.read_csv(D5/'sweep_base.csv'); ad=pd.read_csv(D5/'sweep_adaptive.csv')
sets={g:base[base.group==g] for g in ('T5','C5','D5')}
arms={f'{a}{k}':(base if a=='R' else ad).query('group == @g',local_dict={'g':f'{a}{k}'}) for a in 'AMR' for k in range(1,7)}
out={'arms':{}}
for name,new in arms.items():
    assert len(new)==110,(name,len(new))
    beta,mu,sd,gp=fit(pd.concat([s0,new]))
    def pred(e):
        x=e[F].to_numpy(float); r,s=gp.predict((x-mu)/sd,return_std=True); return e.y.to_numpy(),feats(x)@beta+r,s
    y,p,s=pred(calib); q=np.sort(np.abs(y-p)/s)[54]; r={'q':float(q)}
    for g,e in sets.items():
        y,p,s=pred(e); lo,hi=p-q*s,p+q*s
        r[g]=dict(covered=int(((y>=lo)&(y<=hi)).sum()),n=len(y),mean_width=float((hi-lo).mean()),mean_winkler=float(wink(y,lo,hi).mean()),mae=float(np.abs(p-y).mean()))
    tw=r['T5']['mean_width']
    r['C1']=r['T5']['covered']>=48; r['C2c']=bool(r['C5']['covered']>=32 and r['C5']['mean_width']<=3*tw); r['C2d']=bool(r['D5']['covered']>=32 and r['D5']['mean_width']<=3*tw)
    r['pass3']=bool(r['C1'] and r['C2c'] and r['C2d'])
    r['sampled']=dict(corner=int(((new.load<=.35)&(new.bw_iac_khz<=75)).sum()),dt3=int((new.dead_time_us==3).sum()),lowload=int((new.load<=.35).sum()))
    out['arms'][name]=r
W=lambda a,k,g: out['arms'][f'{a}{k}'][g]['mean_winkler']
def perm_p(d):
    d=np.asarray(d,float); obs=d.mean(); n=sum(np.mean(np.array(s)*d)>=obs-1e-12 for s in itertools.product([1,-1],repeat=len(d))); return n/2**len(d)
D={'H1':[W('R',k,'C5')-W('A',k,'C5') for k in range(1,7)],'H2':[W('R',k,'C5')-W('M',k,'C5') for k in range(1,7)],
   'H3':[1.10*W('A',k,'C5')-W('M',k,'C5') for k in range(1,7)],'H4':[W('A',k,'D5')-W('M',k,'D5') for k in range(1,7)]}
alive=True
for h in ['H1','H2','H3','H4']:
    p=perm_p(D[h]); rej=alive and p<0.05
    out[h]=dict(d=D[h],p=p,status=('rejected' if rej else ('not_rejected' if alive else 'not_tested')))
    alive=rej
for X in 'AMR': out[f'CV-{X}']=dict(n_pass=int(sum(out['arms'][f'{X}{k}']['pass3'] for k in range(1,7))),pass_=bool(sum(out['arms'][f'{X}{k}']['pass3'] for k in range(1,7))>=5))
out['claims']={'A':out['H1']['status']=='rejected' and out['CV-A']['pass_'],'M':out['H2']['status']=='rejected' and out['CV-M']['pass_'],
               'M~A':out['H3']['status']=='rejected','M>A(dt3)':out['H4']['status']=='rejected'}
out['M_dt3_le27_groups']=int(sum(out['arms'][f'M{k}']['sampled']['dt3']<=27 for k in range(1,7)))
(ROOT/'docs/reports/M6_rulings_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda o: bool(o) if isinstance(o,np.bool_) else str(o))+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='arms'},ensure_ascii=False,indent=1,default=str))
