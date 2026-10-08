#!/usr/bin/env python3
"""第二轮中文图；数据全部读取冻结第一次评估。"""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'data/dclink2/mplcache'))
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager

def main():
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK SC','font.size':10,'axes.unicode_minus':True})
    out=ROOT/'data/dclink2'; m=json.loads((out/'surrogate_metrics.json').read_text())
    dest=ROOT/'docs/figures'; dest.mkdir(exist_ok=True)
    methods=[f'm{i}' for i in range(6)]; pos=np.arange(6)
    fig,axs=plt.subplots(1,2,figsize=(14,5.5),layout='constrained')
    groups=[('test','分布内测试','#4477AA'),('ood_dt3','E-dt3','#EE7733'),('ood_corner','E-corner','#228833')]
    for j,(g,label,color) in enumerate(groups):
        for ax,key in zip(axs,['coverage','mean_width']):
            vals=[m[f'{k}.{g}.{key}']*(100 if key=='coverage' else 1) for k in methods]
            ax.bar(pos+(j-1)*.24,vals,.23,label=label,color=color)
    axs[0].axhline(90,color='gray',ls=':',label='名义覆盖 90%')
    axs[0].axhline(62/75*100,color='#882255',ls='--',label='C1：62/75')
    axs[0].axhline(80,color='black',ls='-.',label='C2：24/30')
    axs[0].set(ylabel='覆盖率（%）',ylim=(0,115),title='各方法覆盖率（判据仅用于 M2）')
    limits=[3*m[f'{k}.test.mean_width'] for k in methods]
    axs[1].plot(pos,limits,'k_',ms=26,mew=2,label='各方法 3 倍 test 宽度（判据仅用于 M2）')
    axs[1].set_yscale('log')  # 交叉评审 D-09：对数轴，避免 M3/M5 压扁 M0–M2 的差异
    axs[1].set(ylabel='平均区间宽度（百分点，对数轴）',title='区间宽度与对应上限',ylim=(0.3,60))
    for ax in axs:
        ax.set_xticks(pos,['M0\nGP 标准','M1\nGP 归一化','M2\n解析＋GP','M3\nreviewer_b 解析','M4\nMLP','M5\nresearcher_a 解析'])
        ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True); ax.legend(fontsize=8,loc='upper left',ncol=2)
    fig.savefig(dest/'m3_round2_methods.png',dpi=150); plt.close(fig)
    ideal=pd.read_csv(out/'sweep_ideal.csv').set_index('case_id')
    nonideal=pd.read_csv(out/'sweep_nonideal.csv').set_index('case_id').loc[ideal.index]
    fig,axs=plt.subplots(1,2,figsize=(14,5.5),layout='constrained')
    for g,label,color in groups:
        group={'test':'E-in','ood_dt3':'E-dt3','ood_corner':'E-corner'}[g]
        mask=ideal.group==group
        axs[0].scatter(ideal.loc[mask,'y'],nonideal.loc[mask,'y'],s=18,alpha=.75,color=color,label=group)
    lo=min(ideal.y.min(),nonideal.y.min()); hi=max(ideal.y.max(),nonideal.y.max())
    axs[0].plot([lo,hi],[lo,hi],'k--',lw=1,label='相等线')
    axs[0].set(xlabel='理想传感器 y（%）',ylabel='非理想传感器 y（%）',title='相同参数点的目标值对照')
    axs[0].legend(fontsize=9); axs[0].grid(alpha=.2)
    pos=np.arange(3); width_ax=axs[1].twinx()
    widths={}
    for offset,sensor,label,color in [(-.15,'','理想','#4477AA'),(.15,'nonideal_','非理想','#EE7733')]:
        cov=[100*m[f'm2.{sensor}{g}.coverage'] for g,_,_ in groups]
        widths[sensor]=[m[f'm2.{sensor}{g}.mean_width'] for g,_,_ in groups]
        axs[1].bar(pos+offset,cov,.28,color=color,alpha=.75,label=label+'覆盖率')
    # 交叉评审 D-07：输入点相同，两组区间宽度严格相等，只画一次、不连线
    assert np.allclose(widths[''],widths['nonideal_'])
    width_ax.plot(pos,widths[''],'kD',ms=8,ls='none',label='区间宽度（两组输入相同，宽度相等）')
    axs[1].set(xticks=pos,xticklabels=[label for _,label,_ in groups],ylabel='覆盖率（%）',ylim=(0,115),
               title='M2：沿用理想数据的拟合与校准')
    width_ax.set_ylabel('平均区间宽度（百分点）'); width_ax.set_ylim(0,1.25)
    h,l=axs[1].get_legend_handles_labels(); h2,l2=width_ax.get_legend_handles_labels()
    axs[1].legend(h+h2,l+l2,fontsize=8,loc='upper left',ncol=2)
    axs[1].grid(axis='y',alpha=.2); axs[1].set_axisbelow(True)
    fig.savefig(dest/'m3_round2_nonideal.png',dpi=150); plt.close(fig)
if __name__=='__main__': main()
