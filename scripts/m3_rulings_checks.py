#!/usr/bin/env python3
"""M3 主持人裁定的复核计算（只读已有数据，不改预注册判定）。
输出 docs/reports/M3_rulings_checks.json。
MagNet 部分需要本地 data/magnet（N87.zip 与 B.npy 缓存，不入库）；DC-link 部分只读 lab/cases/dclink2。
标注 exploratory 的量是事后探索，只作为下一轮预注册候选。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import integrate, stats
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from magnet_igse import ki_from_steinmetz, igse, classify, error_stats
out={}

# ---- 第 1 条：k_i 闭式与数值积分；正弦 iGSE 与 Steinmetz
d=[]
for a in (1.2,1.366345023,1.5,1.8,1.976349369,2.0):
    num,_=integrate.quad(lambda t: abs(np.cos(t))**a,0,2*np.pi,limit=400,points=[np.pi/2,3*np.pi/2])
    from scipy.special import beta as B
    d.append(abs(2*B(.5,(a+1)/2)-num))
out['igse.beta_closed_form_max_abs_diff']=float(max(d))
th=2*np.pi*np.arange(1024)/1024; rel=[]
for T,(k,a,b) in {'25':(10.27930741,1.366345023,2.585621173),'90':(0.00392010164,1.976349369,2.603857953)}.items():
    for f,bh in ((5e4,0.02),(2e5,0.1),(4.4e5,0.28)):
        p=igse(bh*np.sin(th),f,k,a,b); rel.append(abs(p/(k*f**a*bh**b)-1))
out['igse.sine_vs_steinmetz_max_rel_err']=float(max(rel))

# ---- 第 8.1 条：理想正弦的平台占比
_,res,pl=classify(np.sin(th)); out['classify.pure_sine_1024.plateau_fraction']=float(pl[0]); out['classify.pure_sine_1024.residual']=float(res[0])
for r in (0.03,0.05,0.08):  # 叠加三次谐波的“失真正弦”
    lab,res,pl=classify(np.sin(th)+r*np.sin(3*th))
    out[f'classify.sine_plus_{r}_3rd.label']=str(lab[0]); out[f'classify.sine_plus_{r}_3rd.residual']=float(res[0]); out[f'classify.sine_plus_{r}_3rd.plateau']=float(pl[0])

# ---- MagNet 实际数据
pred=pd.read_csv(ROOT/'data/magnet/igse_predictions.csv')
committed=json.loads((ROOT/'lab/cases/magnet/igse_metrics.json').read_text())
ev=pred[pred.split=='eval']
# 复算入库指标
mx=0.0
for wave,g in ev.groupby('waveform'):
    for key,v in error_stats(g.relative_error).items(): mx=max(mx,abs(v-committed[f'{wave}.all.{key}']))
    for t,tg in g.groupby('temperature_C'):
        for key,v in error_stats(tg.relative_error).items(): mx=max(mx,abs(v-committed[f'{wave}.T{t:g}.{key}']))
out['magnet.recompute_vs_committed_max_abs_diff']=mx
out['magnet.eval_n']=int(len(ev))
Bm=np.load(ROOT/'data/magnet/N87/B.npy',mmap_mode='r')
n=Bm.shape[0]; out['magnet.n']=int(n)
# 用 B 缓存重跑分类，核对与入库标签一致
labels=[];two_seg=[];seg_count=[]
for s in range(0,n,2048):
    b=np.asarray(Bm[s:s+2048],dtype=float)
    lab,_,_=classify(b); labels.extend(lab)
    # 两段折线拟合：在 argmin、argmax 之间各作直线（周期），残差 RMS / 去均值 RMS
    N=b.shape[1]; idx=np.arange(N)
    for row in b:
        i0=int(np.argmin(row)); i1=int(np.argmax(row))
        r=np.roll(row,-i0); j=(i1-i0)%N
        fit=np.empty(N)
        fit[:j+1]=np.linspace(r[0],r[j],j+1)
        fit[j:]=np.linspace(r[j],r[0],N-j+1)[:-1]
        c=r-r.mean(); two_seg.append(np.sqrt(np.mean((r-fit)**2)/np.mean(c**2)))
labels=np.asarray(labels); two_seg=np.asarray(two_seg)
out['magnet.reclassify_matches_committed']=bool(np.all(labels==pred.waveform.to_numpy()))
pred['two_seg_residual']=two_seg
# 8.1：残差略超 0.05 的近正弦样本是否被判为梯形
ns=pred[pred.waveform!='sine']
for lo,hi in ((0.05,0.08),(0.05,0.10)):
    m=(ns.sine_residual>lo)&(ns.sine_residual<=hi)
    out[f'classify.residual_{lo}_{hi}.n']=int(m.sum()); out[f'classify.residual_{lo}_{hi}.trapezoid']=int((m&(ns.waveform=='trapezoid')).sum())
tz=pred[pred.waveform=='trapezoid']
out['classify.trapezoid.plateau_min']=float(tz.plateau_fraction.min())
out['classify.trapezoid.plateau_quantiles_5_50_95']=[float(x) for x in np.quantile(tz.plateau_fraction,[.05,.5,.95])]
for thr in (0.08,0.10,0.12,0.15):
    out[f'classify.trapezoid.below_{thr}']=int((tz.plateau_fraction<thr).sum())
tr=pred[pred.waveform=='triangle']
out['classify.triangle.plateau_max']=float(tr.plateau_fraction.max())
out['classify.nonsine.plateau_between_0.05_0.15']=int(((ns.plateau_fraction>=.05)&(ns.plateau_fraction<.15)).sum())
# D-06（exploratory）：三角类内部按两段折线残差分层
out['triangle.two_seg_residual_quantiles_10_50_90']=[float(x) for x in np.quantile(tr.two_seg_residual,[.1,.5,.9])]
hist,edges=np.histogram(tr.two_seg_residual,bins=[0,.02,.04,.06,.08,.10,.12,.15,.2,.3,1])
out['triangle.two_seg_residual_hist']=dict(edges=[float(e) for e in edges],counts=[int(c) for c in hist])
out['triangle.two_seg_le_0.10.n_all']=int((tr.two_seg_residual<=.10).sum())
out['triangle.two_seg_gt_0.10.n_all']=int((tr.two_seg_residual>.10).sum())
out['triangle.two_seg_in_gap_0.08_0.12']=int(((tr.two_seg_residual>.08)&(tr.two_seg_residual<.12)).sum())
tre=pred[(pred.waveform=='triangle')&(pred.split=='eval')]
for name,mask in (('two_seg',tre.two_seg_residual<=.10),('multi_seg',tre.two_seg_residual>.10)):
    g=tre[mask]; out[f'triangle.{name}.all']=error_stats(g.relative_error)
    for t,tg in g.groupby('temperature_C'): out[f'triangle.{name}.T{t:g}']=error_stats(tg.relative_error)
sn=pred[pred.waveform=='sine']
out['classify.sine.plateau_min_max']=[float(sn.plateau_fraction.min()),float(sn.plateau_fraction.max())]
out['classify.sine.residual_gt_0.02']=int((sn.sine_residual>.02).sum())
out['classify.sine.residual_gt_0.02_and_plateau_ge_0.05']=int(((sn.sine_residual>.02)&(sn.plateau_fraction>=.05)).sum())
# 梯形：平台占比与有符号误差（exploratory）
tze=pred[(pred.waveform=='trapezoid')&(pred.split=='eval')]
rho=stats.spearmanr(tze.plateau_fraction,tze.relative_error)
out['trapezoid.spearman_plateau_vs_signed_error']=dict(rho=float(rho.statistic),p=float(rho.pvalue))
for lo,hi in ((0,.3),(.3,.5),(.5,1.01)):
    g=tze[(tze.plateau_fraction>=lo)&(tze.plateau_fraction<hi)]
    if len(g): out[f'trapezoid.plateau_{lo}_{hi}']=error_stats(g.relative_error)
for t,g in tze.groupby('temperature_C'):
    out[f'trapezoid.T{t:g}.fraction_negative']=float(np.mean(g.relative_error<0))

# ---- DC-link 第二轮
p=pd.read_csv(ROOT/'lab/cases/dclink2/predictions.csv')
m2=p[(p.method=='m2')&(p.sensor=='ideal')]
for s in ('test','ood_dt3','ood_corner'):
    g=m2[m2.split==s]; r=np.abs(g.y-g.prediction)
    out[f'dclink2.m2.{s}.abs_resid_median']=float(r.median()); out[f'dclink2.m2.{s}.sigma_median']=float(g.sigma.median())
    out[f'dclink2.m2.{s}.sigma_mean']=float(g.sigma.mean()); out[f'dclink2.m2.{s}.score_median']=float((r/g.sigma).median())
    out[f'dclink2.m2.{s}.score_p90']=float(np.quantile(r/g.sigma,.9))
    out[f'dclink2.m2.{s}.covered_recount']=int(((g.y>=g.lower)&(g.y<=g.upper)).sum())
    out[f'dclink2.m2.{s}.mean_width_recount']=float((g.upper-g.lower).mean())
mn=p[(p.method=='m2')&(p.sensor=='nonideal')]
for s in ('test','ood_dt3','ood_corner'):
    a=m2[m2.split==s].set_index('case_id'); b_=mn[mn.split==s].set_index('case_id').loc[a.index]
    out[f'dclink2.m2.width_identical_ideal_vs_nonideal.{s}']=float(np.max(np.abs((a.upper-a.lower)-(b_.upper-b_.lower))))
# 失覆盖点在 corner 中的孔径分布
c=m2[m2.split=='ood_corner'].copy()
design=pd.read_csv(ROOT/'lab/cases/dclink2/sweep_ideal.csv').set_index('case_id')
c=c.join(design[['load','dead_time_us','bw_iac_khz','aperture_delay_us']],on='case_id')
miss=c[(c.y<c.lower)|(c.y>c.upper)]
out['dclink2.m2.corner.miss_n']=int(len(miss)); out['dclink2.m2.corner.miss_below_lower']=int((miss.y<miss.lower).sum())
out['dclink2.m2.corner.miss_aperture_lt10']=int((miss.aperture_delay_us<10).sum()); out['dclink2.m2.corner.all_aperture_lt10']=int((c.aperture_delay_us<10).sum())
# 74/75 在可交换下的概率：覆盖数 ~ BetaBinomial(75; 69, 76-69+1=7)
bb=stats.betabinom(75,69,7)
out['dclink2.C1.P_cov_ge_74']=float(bb.sf(73)); out['dclink2.C1.P_cov_le_61']=float(bb.cdf(61))
out['dclink2.C2.P_cov_le_23_of_30']=float(stats.betabinom(30,69,7).cdf(23))
out['dclink2.C2corner.P_cov_le_20_of_30']=float(stats.betabinom(30,69,7).cdf(20))
(ROOT/'docs/reports/M3_rulings_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=1)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=1))
