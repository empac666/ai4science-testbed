#!/usr/bin/env python3
"""第三轮事后探索（只报告，不进入判定）：
(a) 主动臂去掉其 12 个角落点后重拟合 M2，角落覆盖是否仍达标——区分"角落点本身"与"低负载边/其余边缘点"的贡献；
(b) 复核 reviewer_b 的 LHS 角落点数分布模拟（110 点、角落体积占比）。输出 docs/reports/M4_explore_ablation.json。"""
import json, numpy as np, pandas as pd
from scipy.stats import qmc
exec(open(__file__.replace('m4_explore_ablation.py','m4_rulings_checks.py')).read().split("split=json.loads")[0])
split=json.loads((D/'split.json').read_text())
base=pd.read_csv(D/'sweep_base.csv'); act=pd.read_csv(D/'sweep_active.csv'); old=pd.read_csv(ROOT/'lab/cases/dclink2/sweep_nonideal.csv')
allp=pd.concat([base,act,old],ignore_index=True).set_index('case_id'); s0=old[old.case_id.isin(split['s0'])]
def run(new):
    tr=pd.concat([s0,new]); beta,mu,sd,gp=fit(tr); res={'n_train':len(tr)}
    P={}
    for g in ['calib','test','ood_corner','ood_dt3']:
        e=allp.loc[split[g]]; x=e[F].to_numpy(float); r,s=gp.predict((x-mu)/sd,return_std=True); P[g]=(e.y.to_numpy(),feats(x)@beta+r,s)
    y,p,s=P['calib']; q=np.sort(np.abs(y-p)/s)[54]; res['q']=float(q)
    for g in ['test','ood_corner','ood_dt3']:
        y,p,s=P[g]; res[g]=dict(covered=int((np.abs(y-p)<=q*s).sum()),n=len(y),mean_width=float(2*q*s.mean()),mae=float(np.abs(y-p).mean()))
    return res
corner=(act.load<=.35)&(act.bw_iac_khz<=75); lowload=act.load<=.35
out={'active_full':run(act),'active_minus_corner12':run(act[~corner]),'active_minus_lowload38':run(act[~lowload])}
rng=np.random.default_rng(0); vol=(.05/.70)*(np.log(1.5)/np.log(8)); cnt=[]
for _ in range(10000):
    u=qmc.LatinHypercube(d=4,seed=rng).random(110); cnt.append(int(((u[:,0]<=.05/.70)&(u[:,2]<=np.log(1.5)/np.log(8))).sum()))
cnt=np.array(cnt); out['lhs_corner_count']=dict(volume_fraction=float(vol),expected=float(110*vol),p_le2=float((cnt<=2).mean()),p_ge5=float((cnt>=5).mean()),
    dist={int(k):float((cnt==k).mean()) for k in range(0,7)})
(ROOT/'docs/reports/M4_explore_ablation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(out,ensure_ascii=False,indent=1))
