#!/usr/bin/env python3
"""Chinese figures and reproducible waveform audit panels."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/magnet-mplcache')
os.environ['OPENBLAS_NUM_THREADS']='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
ROOT=Path(__file__).resolve().parents[1]
LABELS={'sine':'正弦','triangle':'三角','trapezoid':'梯形'}
COLORS={'sine':'#4477AA','triangle':'#228833','trapezoid':'#EE7733'}

def main():
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK SC','font.size':11,'axes.unicode_minus':True})
    data=ROOT/'data/magnet';dest=ROOT/'docs/figures';dest.mkdir(parents=True,exist_ok=True)
    metrics=json.loads((data/'igse_metrics.json').read_text());meta=json.loads((data/'igse_metadata.json').read_text())
    temps=meta['temperatures_C'];waves=list(LABELS)
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    for ax,key,title in zip(axes,['abs_median','abs_p95'],['绝对相对误差中位数（%）','绝对相对误差 p95（%）']):
        values=np.array([[metrics[f'{wave}.T{t:g}.{key}']*100 for t in temps] for wave in waves])
        im=ax.imshow(values,cmap='YlOrRd',aspect='auto',vmin=0,vmax=max(values.max(),1))
        ax.set_xticks(range(len(temps)),[f'{t:g} ℃' for t in temps]);ax.set_yticks(range(len(waves)),[LABELS[w] for w in waves])
        ax.set(xlabel='温度',ylabel='波形类型',title=title)
        for y in range(len(waves)):
            for x in range(len(temps)):
                ax.text(x,y,f'{values[y,x]:.1f}',ha='center',va='center',color='white' if values[y,x]>.6*values.max() else 'black')
        fig.colorbar(im,ax=ax,label='误差（%）',shrink=.85)
    fig.savefig(dest/'m3_igse_error.png',dpi=150);plt.close(fig)
    frame=pd.read_csv(data/'igse_predictions.csv');frame=frame[frame.split=='eval']
    fig,ax=plt.subplots(figsize=(7,6.2),layout='constrained')
    for wave in waves:
        g=frame[frame.waveform==wave]
        ax.scatter(g.measured_W_m3,g.predicted_W_m3,s=6,alpha=.24,color=COLORS[wave],label=LABELS[wave],rasterized=True)
    low=min(frame.measured_W_m3.min(),frame.predicted_W_m3.min())*.75
    high=max(frame.measured_W_m3.max(),frame.predicted_W_m3.max())*1.25
    x=np.array([low,high]);ax.plot(x,x,'k-',lw=1,label='预测 = 实测')
    ax.plot(x,.8*x,'k--',lw=.9,label='±20% 参考线');ax.plot(x,1.2*x,'k--',lw=.9)
    ax.set(xscale='log',yscale='log',xlim=(low,high),ylim=(low,high),xlabel='实测体积损耗（W/m³）',ylabel='iGSE 预测体积损耗（W/m³）',title='N87：正弦留出集与全部非正弦样本')
    ax.grid(alpha=.15,which='both');ax.legend(markerscale=3,loc='upper left')
    fig.savefig(dest/'m3_igse_scatter.png',dpi=150);plt.close(fig)
    audit=np.load(data/'classification_audit.npz');count=len(audit['ids'])
    audit_labels=pd.read_csv(data/'classification_audit.csv').waveform.to_numpy()
    # Separate panels keep every trace readable for visual inspection.
    for start in range(0,count,12):
        fig,axes=plt.subplots(3,4,figsize=(12,8),layout='constrained')
        for j,ax in enumerate(axes.ravel()):
            i=start+j
            if i>=count:ax.set_visible(False);continue
            b=audit['b'][i]; ax.plot(np.arange(len(b))/len(b),b,lw=1)
            ax.set_title(f"样本 {audit['ids'][i]} · {LABELS[str(audit_labels[i])]}",fontsize=10)
            ax.set(xlabel='归一化周期',ylabel='B（T）');ax.grid(alpha=.2)
        fig.savefig(data/f'classification_audit_{start//12+1}.png',dpi=120);plt.close(fig)
    print('Saved Chinese error/scatter figures and classification audit panels')
if __name__=='__main__':main()
