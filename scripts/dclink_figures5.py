#!/usr/bin/env python3
"""第五轮中文配对图与隔离冒烟图；不把冒烟数据用于正式判定。"""
from dclink_active5 import ROOT,OUT,verify,FEATURES,load_training,fit_m2
from dclink_surrogate4 import sampling
from dclink_figures4 import setup
from dclink_surrogate2 import reviewer_b_features
import argparse
import json
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

def plot(m,dest):
    setup(dest)
    for group,methods,hypotheses,name in [('C5','AMR',[1,2,3],'corner'),('D5','AM',[4],'dt3')]:
        fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
        for k in range(1,7):
            ax.plot(range(len(methods)),[m[f'{x}{k}.m2.{group}.mean_winkler'] for x in methods],'-o',label=f'第{k}组')
        ax.set(xticks=range(len(methods)),xticklabels=list(methods),ylabel=f'{group} 平均 Winkler（越低越好）',ylim=(0,None))
        annotation='；'.join(f'H{h} p={m[f"H{h}.pvalue"]:.5g} ({m[f"H{h}.status"]})' for h in hypotheses)
        ax.set_title('第五轮：组内配对\n'+annotation,fontsize=11); ax.legend(ncol=3)
        fig.savefig(dest/f'r5_{name}.png'); plt.close(fig)
    arms=[f'{x}{k}' for k in range(1,7) for x in 'AMR']; x=np.arange(18)
    fig,axes=plt.subplots(2,1,figsize=(13,8),layout='constrained')
    for j,(g,n) in enumerate([('C5',40),('D5',40),('T5',60)]):
        axes[0].plot(x,[m[f'{a}.m2.{g}.covered']/n for a in arms],'-o',label=g)
    axes[0].axhline(.8,ls='--',c='black',label='门限：32/40 或 48/60')
    axes[0].set(ylabel='覆盖率',ylim=(0,1.05)); axes[0].legend(ncol=4)
    for j,(key,label) in enumerate([('corner','角落'),('dt3','dt=3')]):
        axes[1].bar(x+(j-.5)*.36,[m[f'{a}.sampled.{key}'] for a in arms],width=.36,label=label)
    axes[1].set(ylabel='新增采点数'); axes[1].legend()
    for ax in axes: ax.set_xticks(x,arms)
    fig.suptitle('第五轮：各臂覆盖与新增采点数（M2）'); fig.savefig(dest/'r5_coverage_sampling.png'); plt.close(fig)

def smoke_plot(split):
    out=ROOT/'data/dclink5_smoke'; dest=out/'figures'; setup(dest)
    base=pd.read_csv(out/'sweep_base.csv'); adaptive=pd.read_csv(out/'sweep_adaptive.csv')
    frame=pd.concat([base,adaptive],ignore_index=True)
    scaler,coef,gp=fit_m2(load_training(split,'A1',[],smoke=True)); x=frame[FEATURES].to_numpy()
    residual,sigma=gp.predict(scaler.transform(x),return_std=True); pred=reviewer_b_features(x)@coef+residual
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained'); idx=np.arange(len(frame))
    ax.errorbar(idx,pred,yerr=sigma,fmt='o',label='S0 前40例预测 ±1σ（未校准）')
    ax.scatter(idx,frame.y,marker='x',label='4秒仿真 y'); ax.set(xticks=idx,xticklabels=frame.case_id,ylabel='目标 y',title='冒烟，不作评估：六例目标与预测')
    ax.legend(); fig.savefig(dest/'r5_smoke_diagnostic.png'); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for arm,rows in adaptive.groupby('group'):
        counts=sampling(rows); cats=np.arange(0,3.5,.5)
        axes[0].plot(cats,[counts[f'dead_time_{c:.1f}'] for c in cats],'-o',label=arm)
        axes[1].scatter(arm,counts['corner'],label=arm)
    axes[0].set(xlabel='dead_time（微秒）',ylabel='采点数',xticks=cats); axes[0].legend()
    axes[1].set(ylabel='角落采点数',ylim=(-.2,2.2)); fig.suptitle('冒烟，不作评估：A1/M1 各两例采点')
    fig.savefig(dest/'r5_smoke_sampling.png'); plt.close(fig)

def main():
    split=verify(); ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--smoke',action='store_true'); a=ap.parse_args()
    if a.smoke: smoke_plot(split); return
    from dclink_surrogate5 import run
    assert (ROOT/'lab/cases/dclink5/first').exists(); run(split)
    plot(json.loads((OUT/'surrogate_metrics.json').read_text()),ROOT/'docs/figures')
if __name__=='__main__': main()
