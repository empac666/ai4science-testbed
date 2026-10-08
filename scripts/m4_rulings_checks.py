#!/usr/bin/env python3
"""第三轮主持人独立复算：不调用 dclink_surrogate3.evaluate / dclink_active3.fit_m2，直接按预注册重算判据。
只读 data/dclink3 与第二轮非理想数据；输出 docs/reports/M4_rulings_checks.json。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
import json, sys, math
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import wilcoxon, betabinom
from scipy.special import comb
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'data/dclink3'
sys.path.insert(0,str(ROOT/'data/dclink_src/simsw'))
from dclink_simsw.common import SimulationConfig
CFG=json.loads((ROOT/'lab/cases/dclink3/config_prerun.json').read_text())['model']
F=['load','dead_time_us','bw_iac_khz','aperture_delay_us']
sim=SimulationConfig()

def feats(x):  # 预注册第 4 节：β0 + β1·t_dead·f_c + β2·load + β3·f_grid/bw + β4·4π·f_grid·t_ap
    return np.column_stack([np.ones(len(x)),x[:,1]*1e-6*sim.f_carrier_Hz,x[:,0],sim.f_grid_Hz/(x[:,2]*1e3),4*np.pi*sim.f_grid_Hz*x[:,3]*1e-6])
def kernel():
    return (ConstantKernel(CFG['gp_constant'],CFG['gp_constant_bounds'])*RBF(CFG['gp_length_scales'],CFG['gp_length_bounds'])
            +WhiteKernel(CFG['gp_white'],CFG['gp_white_bounds']))
def fit(train):
    x=train[F].to_numpy(float); y=train.y.to_numpy(float); A=feats(x)
    beta=np.linalg.lstsq(A,y,rcond=None)[0]; mu=x.mean(0); sd=x.std(0)
    gp=GaussianProcessRegressor(kernel=kernel(),normalize_y=True,alpha=CFG['gp_alpha'],n_restarts_optimizer=CFG['gp_restarts'],
                                random_state=CFG['seed']).fit((x-mu)/sd,y-A@beta)
    return beta,mu,sd,gp
def wink(y,lo,hi,a=.1): return hi-lo+2/a*(np.maximum(lo-y,0)+np.maximum(y-hi,0))

split=json.loads((D/'split.json').read_text())
base=pd.read_csv(D/'sweep_base.csv'); act=pd.read_csv(D/'sweep_active.csv'); old=pd.read_csv(ROOT/'lab/cases/dclink2/sweep_nonideal.csv')
allp=pd.concat([base,act,old],ignore_index=True).set_index('case_id')
first=json.loads((ROOT/'lab/cases/dclink3/first/surrogate_metrics.json').read_text())
out={}; pred={}
for arm,new in [('active',act),('random',base[base.group=='R'])]:
    tr=pd.concat([old[old.case_id.isin(split['s0'])],new]); assert len(tr)==260
    beta,mu,sd,gp=fit(tr)
    for g in ['calib','test','ood_corner','ood_dt3','supplement_corner','supplement_dt3']:
        e=allp.loc[split[g]]; x=e[F].to_numpy(float)
        r,s=gp.predict((x-mu)/sd,return_std=True); pred[(arm,g)]=(e.y.to_numpy(),feats(x)@beta+r,s)
    y,p,s=pred[(arm,'calib')]; q=np.sort(np.abs(y-p)/s)[54]; out[f'{arm}.q']=q
    for g in ['test','ood_corner','ood_dt3','supplement_corner','supplement_dt3']:
        y,p,s=pred[(arm,g)]; lo,hi=p-q*s,p+q*s; cov=int(((y>=lo)&(y<=hi)).sum())
        out[f'{arm}.{g}']=dict(n=len(y),covered=cov,mean_width=float((hi-lo).mean()),mae=float(np.abs(p-y).mean()),
                               max_abs_error=float(np.abs(p-y).max()),bias=float((p-y).mean()),mean_winkler=float(wink(y,lo,hi).mean()))
        pred[(arm,g)]=(y,p,s,lo,hi)
    tw=out[f'{arm}.test']['mean_width']
    out[f'{arm}.C1']=out[f'{arm}.test']['covered']>=48
    for g,c in [('ood_corner','C2-corner'),('ood_dt3','C2-dt3')]:
        out[f'{arm}.{c}']=dict(coverage_pass=out[f'{arm}.{g}']['covered']>=32,width=out[f'{arm}.{g}']['mean_width'],
                              limit=3*tw,width_pass=out[f'{arm}.{g}']['mean_width']<=3*tw)
    out[f'{arm}.pass']=bool(out[f'{arm}.C1'] and all(out[f'{arm}.{c}']['coverage_pass'] and out[f'{arm}.{c}']['width_pass'] for c in ('C2-corner','C2-dt3')))
for g in ['ood_corner','ood_dt3']:
    ya,_,_,la,ha=pred[('active',g)]; yr,_,_,lr,hr=pred[('random',g)]; assert np.array_equal(ya,yr)
    sa,sr=wink(ya,la,ha),wink(yr,lr,hr); t=wilcoxon(sa,sr,alternative='less',zero_method='wilcox')
    out[f'paired.{g}']=dict(p_less=float(t.pvalue),p_greater=float(wilcoxon(sa,sr,alternative='greater').pvalue),
                           active_better_n=int((sa<sr).sum()),random_better_n=int((sa>sr).sum()),
                           median_diff=float(np.median(sa-sr)),active_mean=float(sa.mean()),random_mean=float(sr.mean()))
out['P-a']=out['active.ood_corner']['covered']>=out['random.ood_corner']['covered']
out['P-b']=out['paired.ood_corner']['p_less']<.05
out['overall']=bool(out['active.pass'] and out['P-a'] and out['P-b'])
# 与封存首次评估逐项对比
diff=[]
for arm in ('active','random'):
    if not np.isclose(out[f'{arm}.q'],first[f'{arm}.m2.calib.q'],rtol=1e-8): diff.append(f'{arm}.q')
    for g in ['test','ood_corner','ood_dt3']:
        for k in ('covered','mean_width','mae'):
            if not np.isclose(out[f'{arm}.{g}'][k],first[f'{arm}.m2.{g}.{k}'],rtol=1e-6): diff.append(f'{arm}.{g}.{k}')
out['mismatch_vs_first']=diff
# 可交换时的误杀概率（beta-binomial 精确值）
out['false_reject_exact']={'C1(<48/60)':float(betabinom.cdf(47,60,55,6)),'C2(<32/40)':float(betabinom.cdf(31,40,55,6))}
# 主动臂采到角落 / dt=3 的点数（按批），随机臂对照
act_b=act.assign(corner=(act.load<=.35)&(act.bw_iac_khz<=75),dt3=act.dead_time_us==3)
out['sampled']=dict(active_by_batch={int(b):dict(corner=int(r.corner.sum()),dt3=int(r.dt3.sum()),
                         low_bw75=int((r.bw_iac_khz<=75).sum()),low_load035=int((r.load<=.35).sum())) for b,r in act_b.groupby('batch')},
                    active_total=dict(corner=int(act_b.corner.sum()),dt3=int(act_b.dt3.sum())),
                    random_total=dict(corner=int(((base.group=='R')&(base.load<=.35)&(base.bw_iac_khz<=75)).sum()),
                                      dt3=int(((base.group=='R')&(base.dead_time_us==3)).sum())))
# kriging believer 直接矩阵复核（第 1 批：S0 上重拟合，逐步对完整条件集求逆）
b1=json.loads((D/'active/batch_1.json').read_text()); pool=pd.DataFrame(json.loads((D/'pool.json').read_text()))
s0=old[old.case_id.isin(split['s0'])].set_index('case_id').loc[split['s0']].reset_index()
beta,mu,sd,gp=fit(s0); k=gp.kernel_
same_theta=bool(np.allclose(k.theta,b1['kernel_theta'],rtol=1e-8,atol=1e-10))
Z=(pool[F].to_numpy(float)-mu)/sd; X=gp.X_train_.copy(); rem=list(range(len(Z))); chosen=[]
for _ in range(22):
    K=k(X)+CFG['gp_alpha']*np.eye(len(X)); Ks=k(X,Z[rem]); Kinv=np.linalg.inv(K)
    var=k.diag(Z[rem])-np.einsum('ij,ij->j',Ks,Kinv@Ks); j=int(np.argmax(var)); i=rem.pop(j); chosen.append(pool.pool_id[i]); X=np.vstack([X,Z[i]])
out['believer_batch1']=dict(theta_match=same_theta,theta_max_abs_diff=float(np.max(np.abs(k.theta-np.array(b1['kernel_theta'])))),theta_independent=k.theta.tolist(),ids_match=chosen==[p['pool_id'] for p in b1['points']])
# 批次产生顺序：batch_b 文件晚于上一批所有案例完成、早于本批首个案例完成
prog=[json.loads(l) for l in open(D/'progress.jsonl')]
t=lambda s: datetime.fromisoformat(s).timestamp()
order={}
for b in range(1,6):
    ids=[p['case_id'] for p in json.loads((D/f'active/batch_{b}.json').read_text())['points']]
    mt=(D/f'active/batch_{b}.json').stat().st_mtime
    mine=[t(r['recorded_at']) for r in prog if r['case_id'] in ids]
    prev=[t(r['recorded_at']) for r in prog if r['case_id'] in (order.get(b-1,{}).get('ids',[]) if b>1 else [c for c in split['calib']+split['test']+split['ood_corner']+split['ood_dt3']+split['random']])]
    order[b]=dict(ids=ids,file_after_prev=bool(mt>=max(prev)) if prev else None,file_before_own=bool(mt<=min(mine)))
out['batch_order']={b:{k:v for k,v in o.items() if k!='ids'} for b,o in order.items()}
out['failures']=[r['case_id'] for r in prog if r['status']!='ok']
(ROOT/'docs/reports/M4_rulings_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda o: bool(o) if isinstance(o,np.bool_) else str(o))+'\n')
print(json.dumps(out,ensure_ascii=False,indent=1,default=lambda o: bool(o) if isinstance(o,np.bool_) else str(o)))
