#!/usr/bin/env python3
import os
from dclink_surrogate import ROOT, METHODS
os.environ['MPLCONFIGDIR']=str(ROOT/'data/m2_mplcache')
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager

def main():
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK SC','axes.unicode_minus':True,'font.size':11})
    metrics=json.loads((ROOT/'data/dclink/surrogate_metrics.json').read_text())
    methods=METHODS[:5]; labels=['负载插值','解析模型','GP 保形','MLP 保形','GP 原生']
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    pos=np.arange(len(methods))
    for ax,key in zip(axs,['coverage','mae']):
        for offset,group,label,color in [(-.19,'test','分布内测试','#4477AA'),(.19,'ood','分布外 OOD','#EE7733')]:
            values=[metrics[f'{m}.{group}.{key}']*(100 if key=='coverage' else 1) for m in methods]
            bars=ax.bar(pos+offset,values,.36,label=label,color=color)
            ax.bar_label(bars,fmt='%.1f' if key=='coverage' else '%.2f',fontsize=9,padding=3)
        ax.set_xticks(pos,labels); ax.set_axisbelow(True); ax.grid(axis='y',alpha=.2)
        ax.set_ylabel('覆盖率（%）' if key=='coverage' else '平均绝对误差（百分点）')
        ax.set_title('预测区间覆盖率' if key=='coverage' else '点预测误差')
        ax.legend(loc='upper left',bbox_to_anchor=(0,1.02),fontsize=9)
    axs[0].axhspan(85,95,color='#228833',alpha=.12,label='85–95% 判据带')
    axs[0].axhline(90,color='#228833',ls='--',lw=1,label='90% 名义覆盖率')
    axs[0].legend(loc='upper left',ncol=2,fontsize=8)
    axs[0].set_ylim(0,125); axs[1].set_ylim(0,axs[1].get_ylim()[1]*1.25)
    fig.savefig(ROOT/'docs/figures/m2_methods.png',dpi=150); plt.close(fig)
    df=pd.read_csv(ROOT/'data/dclink/predictions.csv'); df=df[df.method=='gp_conformal']
    bias=df.prediction-df.y
    fig,axs=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    groups=[(df['split']=='train','o','训练集'),
            (df['split'].isin(['calib','test']),'s','校准集 / 测试集'),
            (df['split'].str.startswith('ood'),'^','分布外 OOD')]
    for index,(ax,values,title,unit) in enumerate(zip(axs,[df.y,bias],['扫描真值（全部点）','GP 预测偏差（样本外）'],['电容相对误差 y（%）','预测减真值（百分点）'])):
        visible=df['split']!='train' if index else np.ones(len(df),dtype=bool)
        vmax=max(float(np.max(abs(values[visible]))),1e-12)
        for mask,marker,label in groups:
            mask=mask & visible
            if not mask.any(): continue
            sc=ax.scatter(df.loc[mask,'load'],df.loc[mask,'dead_time_us'],c=values[mask],
                          cmap='coolwarm',vmin=-vmax,vmax=vmax,s=48,alpha=.9,
                          marker=marker,edgecolors='black',linewidths=.5)
            # Neutral handles keep the legend independent of the colour scale.
            ax.scatter([],[],marker=marker,c='#bbbbbb',edgecolors='black',s=48,label=label)
        ax.set(xlabel='负载比例',ylabel='死区时间（μs）')
        ax.legend(loc='lower center',bbox_to_anchor=(.5,1.01),fontsize=9,ncol=2)
        ax.set_title(title,pad=53)
        fig.colorbar(sc,ax=ax,label=unit,shrink=.85)
    fig.savefig(ROOT/'docs/figures/m2_bias_map.png',dpi=150); plt.close(fig)

if __name__=='__main__': main()
