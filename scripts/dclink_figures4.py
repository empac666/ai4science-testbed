#!/usr/bin/env python3
"""正式评估图与完全隔离的冒烟诊断图。"""
from dclink_active4 import ROOT,OUT,R3,FEATURES,verify,load_training,fit_m2
import argparse
import json
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/dclink4-matplotlib')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from dclink_surrogate4 import ARMS,sampling
from dclink_surrogate2 import reviewer_b_features

def setup(dest):
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK SC','axes.unicode_minus':False,'figure.dpi':150,'savefig.dpi':150})
    dest.mkdir(parents=True,exist_ok=True)

def sampling_plot(arms,dest,smoke=False):
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    cats=np.arange(0,3.5,.5)
    for i,(arm,frame) in enumerate(arms.items()):
        counts=sampling(frame); label='R（已看过）' if arm=='R' else arm
        axes[0].plot(cats,[counts[f'dead_time_{c:.1f}'] for c in cats],marker='o',mfc='none' if arm=='R' else f'C{i}',label=label)
        axes[1].scatter(i,counts['corner'],facecolors='none' if arm=='R' else f'C{i}',edgecolors=f'C{i}')
    axes[0].scatter([3],[27],marker='_',s=500,c='red',label='正式 M 的 dt=3 上限：27')
    axes[0].set(xlabel='dead_time（微秒）',ylabel='新增采点数',xticks=cats,ylim=(0,None)); axes[0].legend(fontsize=7,ncol=1,loc='upper left',bbox_to_anchor=(1.01,1))
    axes[1].set(xticks=np.arange(len(arms)),xticklabels=['R（已看过）' if a=='R' else a for a in arms],ylabel='角落新增采点数',ylim=(0,None))
    from matplotlib.ticker import MaxNLocator
    axes[1].set_ylim(-.25,max(1.25,max(sampling(frame)['corner'] for frame in arms.values())+1))
    axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
    fig.suptitle('冒烟，不作评估：仅展示本次四例采点' if smoke else '第四轮：各类别与角落采点数')
    fig.savefig(dest/'r4_sampling.png'); plt.close(fig)

def plot(metrics,arms,dest):
    setup(dest); fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    order=['A','M',*['RS'+str(i) for i in range(1,6)],'R']
    for i,arm in enumerate(order):
        for ax,key in zip(axes,['covered','mean_winkler']):
            v=metrics[f'{arm}.m2.ood_corner.{key}']
            ax.scatter(i,v,facecolors='none' if arm=='R' else f'C{i}',edgecolors=f'C{i}',s=55)
            ax.annotate(f'{v:d}' if key=='covered' else f'{v:.2f}',(i,v),textcoords='offset points',xytext=(0,7),ha='center',fontsize=8)
    axes[0].axhline(32,ls='--',c='gray',label='32/40'); axes[0].axhline(36,ls=':',c='red',label='36/40')
    axes[0].set(ylabel='角落覆盖数 / 40',ylim=(0,42)); axes[0].legend()
    axes[1].set(ylabel='角落平均 Winkler（百分点，越低越好）',ylim=(0,4.1))
    for ax in axes: ax.set_xticks(range(len(order)),['R（已看过）' if a=='R' else a for a in order])
    fig.suptitle('第四轮：A、M 与五个新随机臂；A 为已知固定比较对象')
    fig.savefig(dest/'r4_corner.png'); plt.close(fig); sampling_plot(arms,dest); heldout_plot(metrics,dest)

def heldout_plot(metrics,dest):
    order=['A','M',*['RS'+str(i) for i in range(1,6)],'R']; groups=[('test','测试集（门限 48/60）',48,60),('ood_dt3','死区 3 微秒（门限 32/40）',32,40)]
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained'); x=np.arange(len(order))
    for j,(g,label,thr,n) in enumerate(groups):
        cov=[metrics[f'{a}.m2.{g}.covered']/n for a in order]; wid=[metrics[f'{a}.m2.{g}.mean_width'] for a in order]
        bars=axes[0].bar(x+(j-.5)*.38,cov,width=.38,label=label,color=f'C{j}',alpha=.85)
        axes[0].bar_label(bars,[str(metrics[f'{a}.m2.{g}.covered']) for a in order],fontsize=7)
        axes[1].bar(x+(j-.5)*.38,wid,width=.38,label=label.split('（')[0],color=f'C{j}',alpha=.85)
    axes[0].axhline(.8,ls='--',c='black',lw=1,label='0.8（两门限均对应 80%）')
    axes[0].set(ylabel='覆盖率',ylim=(0,1.1)); axes[1].set(ylabel='平均区间宽度（百分点）',ylim=(0,None))
    for ax in axes: ax.set_xticks(x,['R（已看过）' if a=='R' else a for a in order]); ax.legend(fontsize=8,loc='lower right')
    fig.suptitle('第四轮：各臂在测试集与死区 3 微秒集上的覆盖与宽度（M2，各臂自行校准）')
    fig.savefig(dest/'r4_test_dt3.png'); plt.close(fig)

def smoke_plot(split):
    out=ROOT/'data/dclink4_smoke'; dest=out/'figures'; setup(dest)
    arms={key:pd.read_csv(out/name) for key,name in [('RS1','sweep_random.csv'),('M','sweep_mixed.csv')]}
    scaler,coef,gp=fit_m2(load_training(split,[],smoke=True))
    frame=pd.concat(arms.values(),ignore_index=True); x=frame[FEATURES].to_numpy()
    residual,sigma=gp.predict(scaler.transform(x),return_std=True); prediction=reviewer_b_features(x)@coef+residual
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained'); idx=np.arange(len(frame))
    ax.errorbar(idx,prediction,yerr=sigma,fmt='o',label='S0 前40例模型预测 ±1σ（未校准）')
    ax.scatter(idx,frame.y,marker='x',label='4秒冒烟仿真 y')
    ax.set(xticks=idx,xticklabels=frame.case_id,ylabel='目标 y',title='冒烟，不作评估：实测目标与预测诊断')
    ax.legend(); fig.savefig(dest/'r4_smoke_diagnostic.png'); plt.close(fig)
    sampling_plot(arms,dest,True)

def main():
    split=verify(); ap=argparse.ArgumentParser(); ap.add_argument('--smoke',action='store_true'); a=ap.parse_args()
    if a.smoke: smoke_plot(split); return
    from dclink_surrogate4 import run
    # Verify first artifacts/provenance before drawing formal results.
    assert (ROOT/'lab/cases/dclink4/first').exists(); run(split)
    random=pd.read_csv(OUT/'sweep_random.csv')
    arms=dict(A=pd.read_csv(R3/'sweep_active.csv'),M=pd.read_csv(OUT/'sweep_mixed.csv'),
              **{a:random[random.group==a] for a in ARMS if a.startswith('RS')},
              R=pd.read_csv(R3/'sweep_base.csv').query('group == "R"'))
    plot(json.loads((OUT/'surrogate_metrics.json').read_text()),arms,ROOT/'docs/figures')
if __name__=='__main__': main()
