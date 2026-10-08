#!/usr/bin/env python3
"""M3 裁定后的修订图（新文件，不覆盖证据案例已登记哈希的原图）。
- m3_round2_methods_v2.png：宽度改对数轴（D-09）
- m3_round2_nonideal_v2.png：去掉跨组虚线，宽度以文字标注且注明理想/非理想严格相等（D-07）
- m3_triangle_split.png：三角类按两段/多段折线分层、梯形按平台占比分层（D-06、第 8.2 条；事后探索）
数据只读 lab/cases/dclink2/surrogate_metrics.json 与 docs/reports/M3_rulings_checks.json。"""
import os, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'data/dclink2/mplcache'))
import numpy as np, matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK SC','font.size':10,'axes.unicode_minus':False})
m=json.loads((ROOT/'lab/cases/dclink2/surrogate_metrics.json').read_text())
ck=json.loads((ROOT/'docs/reports/M3_rulings_checks.json').read_text())
dest=ROOT/'docs/figures'
groups=[('test','分布内测试','#4477AA'),('ood_dt3','E-dt3','#EE7733'),('ood_corner','E-corner','#228833')]
methods=[f'm{i}' for i in range(6)]; pos=np.arange(6)
names=['M0\nGP 标准','M1\nGP 归一化','M2（主）\n解析＋GP','M3\nreviewer_b 解析','M4\nMLP','M5\nresearcher_a 解析']
fig,axs=plt.subplots(1,2,figsize=(14,5.6),layout='constrained')
for j,(g,label,color) in enumerate(groups):
    cov=[100*m[f'{k}.{g}.coverage'] for k in methods]; wid=[m[f'{k}.{g}.mean_width'] for k in methods]
    axs[0].bar(pos+(j-1)*.26,cov,.25,label=label,color=color)
    axs[1].bar(pos+(j-1)*.26,wid,.25,label=label,color=color)
    for x,c in zip(pos+(j-1)*.26,cov): axs[0].text(x,c+1,f'{c:.0f}',ha='center',fontsize=7)
    for x,w in zip(pos+(j-1)*.26,wid): axs[1].text(x,w*1.06,f'{w:.2f}',ha='center',fontsize=7,rotation=90)
axs[0].axhline(62/75*100,color='#882255',ls='--',label='C1 门限 62/75')
axs[0].axhline(80,color='black',ls='-.',label='C2 门限 24/30')
axs[0].set(ylabel='覆盖率（%）',ylim=(0,128),title='覆盖率（判据只用于 M2）')
axs[1].plot(pos[2],3*m['m2.test.mean_width'],'k_',ms=34,mew=2.5,label='M2 宽度上限 = 3×test（1.92）')
axs[1].set_yscale('log'); axs[1].set_ylim(0.3,60)
axs[1].set(ylabel='平均区间宽度（百分点，对数轴）',title='区间宽度（对数轴）')
for ax in axs:
    ax.set_xticks(pos,names); ax.grid(axis='y',alpha=.25); ax.set_axisbelow(True)
axs[0].legend(fontsize=8,loc='upper center',ncol=5,framealpha=.95); axs[1].legend(fontsize=8,loc='upper center',ncol=4,markerscale=.4)
fig.savefig(dest/'m3_round2_methods_v2.png',dpi=150); plt.close(fig)

fig,ax=plt.subplots(figsize=(9,5.2),layout='constrained'); p3=np.arange(3)
for off,sensor,label,color in [(-.18,'','理想传感器','#4477AA'),(.18,'nonideal_','非理想传感器','#EE7733')]:
    cov=[100*m[f'm2.{sensor}{g}.coverage'] for g,_,_ in groups]
    cnt=[f"{m[f'm2.{sensor}{g}.covered']}/{m[f'm2.{sensor}{g}.n']}" for g,_,_ in groups]
    ax.bar(p3+off,cov,.34,color=color,label=label)
    for x,c,t in zip(p3+off,cov,cnt): ax.text(x,c+1.5,t,ha='center',fontsize=9)
ax.axhline(90,color='gray',ls=':',label='名义覆盖 90%')
ax.set_xticks(p3,[f"{lab}\n区间宽度 {m[f'm2.{g}.mean_width']:.3f}（两组相同）" for g,lab,_ in groups])
ax.set(ylabel='覆盖率（%）',ylim=(0,112),title='M2 沿用理想数据的拟合与校准：非理想传感器下覆盖率下降')
fig.text(0.5,-0.02,'输入参数相同，故理想/非理想两组的区间宽度严格相等；覆盖率差异只来自目标值 y 的移动',ha='center',fontsize=9,color='#444')
ax.legend(fontsize=9,loc='upper right'); ax.grid(axis='y',alpha=.25); ax.set_axisbelow(True)
fig.savefig(dest/'m3_round2_nonideal_v2.png',dpi=150,bbox_inches='tight',pad_inches=0.15); plt.close(fig)

fig,axs=plt.subplots(1,2,figsize=(14,5.2),layout='constrained')
temps=['all','T25','T50','T70','T90']; tl=['全温度','25 ℃','50 ℃','70 ℃','90 ℃']; p5=np.arange(5)
for j,(key,label,color) in enumerate([('two_seg','两段折线三角（n=13,190）','#4477AA'),('multi_seg','多段斜率（n=19,896）','#CC6677')]):
    med=[100*ck[f'triangle.{key}.{t}']['abs_median'] for t in temps]; p95=[100*ck[f'triangle.{key}.{t}']['abs_p95'] for t in temps]
    axs[0].bar(p5+(j-.5)*.38,p95,.36,color=color,alpha=.35,label=label+' p95')
    axs[0].bar(p5+(j-.5)*.38,med,.36,color=color,label=label+' 中位数')
    for x,v in zip(p5+(j-.5)*.38,med): axs[0].text(x,v+.8,f'{v:.1f}',ha='center',fontsize=8)
axs[0].set_xticks(p5,tl); axs[0].set(ylabel='|相对误差|（%）',ylim=(0,72),title='"三角类"内部分层：iGSE 绝对误差（留出集）')
axs[0].legend(fontsize=8,loc='upper left',ncol=2)
bins=[('trapezoid.plateau_0_0.3','平台占比 < 0.3'),('trapezoid.plateau_0.3_0.5','0.3–0.5'),('trapezoid.plateau_0.5_1.01','≥ 0.5')]
sm=[100*ck[k]['signed_median'] for k,_ in bins]; ns=[ck[k]['n'] for k,_ in bins]
axs[1].bar(np.arange(3),sm,.5,color=['#88CCEE','#44AA99','#117733'])
for x,v,n in zip(range(3),sm,ns): axs[1].text(x,v-2.2 if v<0 else v+.6,f'{v:+.1f}%\n(n={n})',ha='center',fontsize=9)
axs[1].axhline(0,color='k',lw=.8); axs[1].set_xticks(range(3),[l for _,l in bins])
axs[1].set(ylabel='有符号相对误差中位数（%）',ylim=(-28,6),title=f"梯形：平台越长越低估（Spearman ρ={ck['trapezoid.spearman_plateau_vs_signed_error']['rho']:.2f}）")
for ax in axs: ax.grid(axis='y',alpha=.25); ax.set_axisbelow(True)
fig.text(0.5,-0.06,'事后探索：分层规则（两段折线残差 ≤ 0.10）在看过整体误差后提出，只作下一轮预注册候选',ha='center',fontsize=8.5,color='#444')
fig.savefig(dest/'m3_triangle_split.png',dpi=150,bbox_inches='tight',pad_inches=0.15); plt.close(fig)
print('ok')
