#!/usr/bin/env python3
"""第四轮主持人独立复算：不调用 dclink_surrogate4 / dclink_active4 的评估与采集代码，直接按预注册重算 H-A 与 H-M。
输出 docs/reports/M5_rulings_checks.json。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
import json, numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import wilcoxon
ROOT=Path(__file__).resolve().parents[1]
exec(open(ROOT/'scripts/m4_rulings_checks.py').read().split("split=json.loads")[0])   # 复用 feats/kernel/fit/wink（主持人第三轮复算实现）
D3=ROOT/'data/dclink3'; D4=ROOT/'data/dclink4'
split=json.loads((D3/'split.json').read_text())
old=pd.read_csv(ROOT/'lab/cases/dclink2/sweep_nonideal.csv'); s0=old[old.case_id.isin(split['s0'])]
b3=pd.read_csv(D3/'sweep_base.csv'); a3=pd.read_csv(D3/'sweep_active.csv')
rs=pd.read_csv(D4/'sweep_random.csv'); mx=pd.read_csv(D4/'sweep_mixed.csv')
held=pd.concat([b3,old],ignore_index=True).set_index('case_id')
arms={'A':a3,'R3':b3[b3.group=='R'],**{f'RS{k}':rs[rs.group==f'RS{k}'] for k in range(1,6)},'M':mx}
out={'arms':{}}; W={}
for name,new in arms.items():
    assert len(new)==110, name
    beta,mu,sd,gp=fit(pd.concat([s0,new]))
    pr={}
    for g in ['calib','test','ood_corner','ood_dt3']:
        e=held.loc[split[g]]; x=e[F].to_numpy(float); r,s=gp.predict((x-mu)/sd,return_std=True); pr[g]=(e.y.to_numpy(),feats(x)@beta+r,s)
    y,p,s=pr['calib']; q=np.sort(np.abs(y-p)/s)[54]; res={'q':float(q)}
    for g in ['test','ood_corner','ood_dt3']:
        y,p,s=pr[g]; lo,hi=p-q*s,p+q*s; w=wink(y,lo,hi)
        res[g]=dict(covered=int(((y>=lo)&(y<=hi)).sum()),mean_width=float((hi-lo).mean()),mae=float(np.abs(p-y).mean()),mean_winkler=float(w.mean()))
        W[(name,g)]=w
    tw=res['test']['mean_width']
    res['C1']=res['test']['covered']>=48
    res['C2-corner']=bool(res['ood_corner']['covered']>=32 and res['ood_corner']['mean_width']<=3*tw)
    res['C2-dt3']=bool(res['ood_dt3']['covered']>=32 and res['ood_dt3']['mean_width']<=3*tw)
    res['pass3']=bool(res['C1'] and res['C2-corner'] and res['C2-dt3'])
    res['sampled']=dict(corner=int(((new.load<=.35)&(new.bw_iac_khz<=75)).sum()),dt3=int((new.dead_time_us==3).sum()),
                        lowload=int((new.load<=.35).sum()),by_dt={str(k):int(v) for k,v in new.dead_time_us.value_counts().sort_index().items()})
    out['arms'][name]=res
A=out['arms']; RS=[f'RS{k}' for k in range(1,6)]
wc=lambda X: A[X]['ood_corner']['mean_winkler']; cc=lambda X: A[X]['ood_corner']['covered']
out['A-1']=dict(pass_=all(wc('A')<wc(k) for k in RS),active=wc('A'),random=[wc(k) for k in RS])
out['A-2']=dict(pass_=bool(all(cc('A')>=cc(k) for k in RS) and cc('A')-np.mean([cc(k) for k in RS])>=4),active=cc('A'),random=[cc(k) for k in RS],
               diff_vs_mean=float(cc('A')-np.mean([cc(k) for k in RS])))
Wt=np.mean([W[(k,'ood_corner')] for k in RS],axis=0); t=wilcoxon(W[('A','ood_corner')],Wt,alternative='less',zero_method='wilcox')
out['A-3']=dict(pass_=bool(t.pvalue<.05),p=float(t.pvalue),statistic=float(t.statistic))
out['H-A']=bool(out['A-1']['pass_'] and out['A-2']['pass_'] and out['A-3']['pass_'])
out['M-0']=dict(pass_=A['M']['sampled']['dt3']<=27,dt3=A['M']['sampled']['dt3'])
out['M-1']=dict(pass_=A['M']['pass3'])
out['M-2']=dict(pass_=bool(cc('M')>=36 and all(wc('M')<wc(k) for k in RS)),covered=cc('M'),winkler=wc('M'))
out['H-M']=bool(out['M-0']['pass_'] and out['M-1']['pass_'] and out['M-2']['pass_'])
for g in ['ood_corner','ood_dt3']:
    t=wilcoxon(W[('M',g)],W[('A',g)],alternative='two-sided',zero_method='wilcox'); out[f'M_vs_A.{g}']=dict(p_two_sided=float(t.pvalue),
        M_better=int((W[('M',g)]<W[('A',g)]).sum()),A_better=int((W[('M',g)]>W[('A',g)]).sum()))
out['random_corner_cov_mean_sd']=[float(np.mean([cc(k) for k in RS])),float(np.std([cc(k) for k in RS],ddof=1))]
out['random_pass3_count']=int(sum(A[k]['pass3'] for k in RS))
# 混合臂分数复核（第 1 批只依赖 S0，可完全独立重算）
pool=pd.DataFrame(json.loads((D3/'pool.json').read_text())); b1=json.loads((D4/'mixed/batch_1.json').read_text())
s0o=s0.set_index('case_id').loc[split['s0']].reset_index(); beta,mu,sd,gp=fit(s0o); k_=gp.kernel_; ystd=gp._y_train_std
Z=(pool[F].to_numpy(float)-mu)/sd; X=gp.X_train_.copy(); rem=list(range(len(Z))); chosen=[]; counts={}
for _ in range(22):
    K=k_(X)+CFG['gp_alpha']*np.eye(len(X)); Ks=k_(X,Z[rem]); var=np.maximum(k_.diag(Z[rem])-np.einsum('ij,ij->j',Ks,np.linalg.solve(K,Ks)),0)
    sig=np.sqrt(var)*ystd; ac=np.array([counts.get(float(pool.dead_time_us[i]),0) for i in rem]); s=sig/np.sqrt(1+ac)
    j=int(np.argmax(s)); i=rem.pop(j); chosen.append(pool.pool_id[i]); counts[float(pool.dead_time_us[i])]=counts.get(float(pool.dead_time_us[i]),0)+1; X=np.vstack([X,Z[i]])
out['mixed_batch1_independent']=dict(ids_match=chosen==[p['pool_id'] for p in b1['points']],dt_counts=counts)
(ROOT/'docs/reports/M5_rulings_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda o: bool(o) if isinstance(o,np.bool_) else str(o))+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='arms'},ensure_ascii=False,indent=1,default=str))
