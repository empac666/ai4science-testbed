"""Render only sealed R9 results; no target reads or model calls."""
from magnet9_common import ROOT,STAGE,read_json,verify_seal,sha,encoded,freeze
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

COLORS={'B':'#56718C','E':'#D29937','D':'#178C7E'}


def main():
    root=STAGE/'first';verify_seal(root,'EVALUATED');verify_seal(root,'RECOMPUTED')
    m=read_json(root/'metrics.json');out=ROOT/'docs/figures';out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'savefig.dpi':180,'figure.facecolor':'white','axes.titleweight':'bold'})
    outputs=[]
    for metric,filename,ylabel in [('c','r9_coverage.png','Empirical coverage'),('W','r9_winkler.png','Mean Winkler score (log10 units)')]:
        fig,axes=plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
        for i,s in enumerate(('U','S')):
            for j,z in enumerate(('XF','XT')):
                ax=axes[i,j]
                for k in range(1,31):
                    values=[m['arms'][f'{s}{k:02d}'][method][z][metric] for method in ('B','E','D')]
                    ax.plot(range(3),values,color='#ADB5BD',alpha=.28,lw=.65,zorder=1)
                for x,method in enumerate(('B','E','D')):
                    values=np.array([m['arms'][f'{s}{k:02d}'][method][z][metric] for k in range(1,31)])
                    ax.scatter(np.full(30,x),values,color=COLORS[method],alpha=.65,s=16,zorder=2)
                    ax.scatter(x,values.mean(),marker='D',color='black',s=40,zorder=3)
                ax.set_xticks(range(3),['B: global q','E: directional q','D: shift + q'])
                ax.set_title(f'{s} / {z}  (30 paired trajectories)');ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.2)
                if metric=='c':
                    ax.axhline(.9,color='#9E354A',ls='--',lw=1,label='90% target')
                    ax.axhline(.8,color='#999999',ls=':',lw=1);ax.set_ylim(0,1.03)
                else:ax.set_yscale('log')
        fig.suptitle('R9 | '+('Coverage: dots are arms, black diamonds are means' if metric=='c' else 'Winkler comparison (log axis; smaller is better)'))
        path=out/filename;fig.savefig(path);plt.close(fig);outputs.append(path)
    fig,axes=plt.subplots(2,2,figsize=(11,7.5),constrained_layout=True)
    for ax,h in zip(axes.flat,('H1','H2','H3','H4')):
        test=m['hypotheses'][h];d=np.array(test['differences']['values'])
        ax.axhline(0,color='#777777',lw=1)
        ax.scatter(np.arange(1,31),d,c=np.where(d>=0,COLORS['D'],'#B04956'),s=28)
        ax.axhline(d.mean(),color='#222222',ls='--',lw=1,label=f'mean={d.mean():.4g}')
        ax.set_title(f"{h} / {test['region']}: p={test['p']:.4g} ({test['status']})")
        ax.set_xlabel('Matched group k');ax.set_ylabel('g_B - g_D' if h in ('H1','H2') else '1.10 W_B - W_D')
        ax.legend(frameon=False);ax.grid(axis='y',alpha=.2)
    fig.suptitle('R9 | Prespecified paired differences (U only; positive favors D)')
    path=out/'r9_pairs.png';fig.savefig(path);plt.close(fig);outputs.append(path)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
    for ax,z in zip(axes,('XF','XT')):
        for k in range(1,31):
            ax.plot([0,1],[m['arms'][f'{s}{k:02d}']['D'][z]['c'] for s in ('U','S')],color=COLORS['D'],alpha=.35,marker='o',ms=3)
        ax.set_xticks([0,1],['U: uniform S0','S: boundary-balanced S0']);ax.set_ylim(0,1.02)
        ax.axhline(.9,color='#9E354A',ls='--',lw=1)
        v=m['S0'][z];ax.set_title(f"{z}: variance ratio S/U = {v['ratio']:.3g}")
        ax.set_ylabel('D empirical coverage');ax.grid(axis='y',alpha=.2)
    fig.suptitle('R9 | S0 policy intervention (descriptive only)')
    path=out/'r9_s0.png';fig.savefig(path);plt.close(fig);outputs.append(path)
    freeze(root/'figure_manifest.json',encoded(dict(metrics_sha256=sha(root/'metrics.json'),
        script_sha256=sha(ROOT/'scripts/magnet9_figures.py'),figures={str(p.relative_to(ROOT)):sha(p) for p in outputs})))
    print('\n'.join(str(p.relative_to(ROOT)) for p in outputs))


if __name__=='__main__':main()
