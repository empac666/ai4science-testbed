#!/usr/bin/env python3
"""正式数据出图；--smoke 使用实际冒烟预测，仅输出隔离目录。"""
from dclink_design3 import ROOT,OUT,SOURCE,FEATURES,generate,make_split
import argparse
import json
import numpy as np
import pandas as pd
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/dclink3-matplotlib')
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from matplotlib.patches import Rectangle
from dclink_surrogate3 import winkler
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'

def plot(metrics,predictions,s0,random,active,dest,smoke=False):
    font_manager.fontManager.addfont(FONT)
    plt.rcParams.update({'font.family':'Noto Sans CJK SC','axes.unicode_minus':False,'figure.dpi':150,'savefig.dpi':150})
    dest.mkdir(parents=True,exist_ok=True)
    groups=['test','ood_corner','ood_dt3']; labels=['测试集','低负载低带宽角落','死区 3 微秒']
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained'); x=np.arange(3)
    for j,(arm,label) in enumerate([('active','主动臂'),('random','随机臂')]):
        bars=axes[0].bar(x+(j-.5)*.32,[metrics[f'{arm}.m2.{g}.coverage'] for g in groups],width=.32,label=label)
        axes[0].bar_label(bars,[f"{metrics[f'{arm}.m2.{g}.covered']}/{metrics[f'{arm}.m2.{g}.n']}" for g in groups],fontsize=8)
        axes[1].bar(x+(j-.5)*.32,[metrics[f'{arm}.m2.{g}.mean_width'] for g in groups],width=.32,label=label)
        axes[1].axhline(3*metrics[f'{arm}.m2.test.mean_width'],ls='--',color=f'C{j}',label=f'{label} 3×测试宽度上限')
    for i in range(3): axes[0].plot([i-.4,i+.4],[.8,.8],color='black',ls='--')
    axes[0].set(ylabel='覆盖率',ylim=(0,1.05)); axes[1].set(ylabel='平均区间宽度（百分点）')
    for ax in axes: ax.set_xticks(x,labels); ax.legend(fontsize=8)
    fig.suptitle('冒烟绘图检查：重复使用同一小样本，不作评估' if smoke else '第三轮：覆盖率与区间宽度（虚线为判据门限）')
    fig.savefig(dest/'r3_coverage_width.png'); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
    for df,label,color in [(s0,'初始训练 S0','gray'),(random,'随机新增 R','tab:blue')]:
        ax.scatter(df.load,df.bw_iac_khz,s=14,alpha=.55,c=color,label=f'{label}（dt=3：{int((df.dead_time_us==3).sum())}）')
    for b,df in active.groupby('batch'):
        ax.scatter(df.load,df.bw_iac_khz,s=35,marker='x',label=f'主动批 {b}（dt=3：{int((df.dead_time_us==3).sum())}）')
    ax.add_patch(Rectangle((.3,50),.05,25,fill=False,color='red',lw=2,label='角落区域'))
    ax.set(yscale='log',xlabel='负载比例',ylabel='电流传感器带宽（kHz，对数）',xlim=(.29,1.01),ylim=(45,430))
    from matplotlib.ticker import FixedLocator,NullLocator,ScalarFormatter
    ax.yaxis.set_major_locator(FixedLocator([50,75,100,150,200,300,400])); ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.set_title('冒烟点示意：蓝色为两例 E-in，不代表随机臂' if smoke else '第三轮采样分布')
    ax.legend(fontsize=8,loc='upper left',bbox_to_anchor=(1.01,1),title='括号内为 dt=3 µs 点数',title_fontsize=8)
    fig.savefig(dest/'r3_sampling_map.png'); plt.close(fig)
    p=predictions[(predictions.method=='m2')&(predictions['split']=='ood_corner')]
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    values=[]
    for arm,label in [('active','主动臂'),('random','随机臂')]:
        r=p[p.arm==arm].sort_values('case_id'); score=winkler(r.y.to_numpy(),r.lower.to_numpy(),r.upper.to_numpy())
        values.append(score); ax.scatter(np.arange(len(r)),score,s=18,label=label)
    ax.vlines(np.arange(len(values[0])),np.minimum(*values),np.maximum(*values),color='gray',alpha=.5)
    title='冒烟数据绘图检查' if smoke else '角落逐点配对区间分数（越低越好）'
    if not smoke and 'paired.ood_corner.pvalue' in metrics:
        title+=(f"\n平均：主动 {metrics['paired.ood_corner.active_mean_winkler']:.2f}，随机 {metrics['paired.ood_corner.random_mean_winkler']:.2f}；"
                f"单侧 Wilcoxon p = {metrics['paired.ood_corner.pvalue']:.4f}")
    ax.set(xlabel='角落案例（按 case_id 排序配对）',ylabel='Winkler 区间分数（百分点）',title=title)
    ax.legend(); fig.savefig(dest/'r3_corner_winkler.png'); plt.close(fig)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--smoke',action='store_true'); a=ap.parse_args()
    old=pd.read_csv(SOURCE); s0=old[old.group=='E-in']
    if a.smoke:
        from dclink_active3 import fit_m2
        from dclink_surrogate2 import reviewer_b_features,interval_metrics
        out=ROOT/'data/dclink3_smoke'; base=pd.read_csv(out/'sweep_base.csv'); active=pd.read_csv(out/'sweep_active.csv')
        sc,coef,gp=fit_m2(s0.iloc[:40]); x=base[FEATURES].to_numpy(); r,s=gp.predict(sc.transform(x),return_std=True)
        p=reviewer_b_features(x)@coef+r; half=1.645*s; metrics={}; rows=[]
        for arm in ('active','random'):
            for group in ('test','ood_corner','ood_dt3'):
                metrics.update({f'{arm}.m2.{group}.{k}':v for k,v in interval_metrics(base.y.to_numpy(),p,half).items()})
                rows.extend(dict(arm=arm,method='m2',split=group,case_id=base.case_id.iloc[i],y=base.y.iloc[i],lower=p[i]-half[i],upper=p[i]+half[i]) for i in range(len(base)))
        plot(metrics,pd.DataFrame(rows),s0,base,active,out/'figures',True)
    else:
        plot(json.loads((OUT/'surrogate_metrics.json').read_text()),pd.read_csv(OUT/'predictions.csv'),s0,
             pd.read_csv(OUT/'sweep_base.csv').query('group == "R"'),pd.read_csv(OUT/'sweep_active.csv'),ROOT/'docs/figures')
if __name__=='__main__': main()
