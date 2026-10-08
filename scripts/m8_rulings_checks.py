#!/usr/bin/env python3
"""主持人独立复算（第七轮）。不 import 任何 magnet6_*/magnet7_* 代码；复用主持人第六轮独立实现 m7_rulings_checks 的
features()/fit()/metrics()（同为主持人独立代码）。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from m7_rulings_checks import features, fit, metrics
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/magnet7'
SHA='6f71603dc6de31604b51b7c0c147b2421d8c0eaa'; H=int(SHA[:8],16); K=20; ALPHA=.1

def design(F):
    f=F.index.to_series().map(lambda i: None)  # placeholder
    s=pd.read_csv(ROOT/'data/magnet/igse_predictions.csv',usecols=['sample_id','frequency_Hz','waveform','amplitude_T']).set_index('sample_id')
    fs=np.sort(s.frequency_Hz.unique()); cid=np.cumsum(np.r_[True,np.diff(np.log(fs))>0.01])-1
    setp={v:int(round(np.median(fs[cid==c])/1000)) for v,c in zip(fs,cid)}
    fset=s.frequency_Hz.map(setp); assert fset.nunique()==20
    fam=fset.astype(str)+'_'+s.waveform+'_d'+(F.duty*10).round().astype(int).astype(str)+'_p'+(F.plateau*20).round().astype(int).astype(str)
    assert fam.nunique()==291
    X=(s.frequency_Hz>=2e5)&(s.amplitude_T>=.10); assert X.sum()==632
    ok=sorted(set(fam[~X])-set(fam[X]))
    perm=np.random.default_rng(H).permutation(ok); gf,cf=list(perm[:40]),list(perm[40:60])
    G=np.sort(F.index[fam.isin(gf)].to_numpy()); C=np.sort(F.index[fam.isin(cf)].to_numpy()); Xi=np.sort(F.index[X].to_numpy())
    pool=np.array(sorted(set(F.index)-set(G)-set(C)-set(Xi)))
    S0={k:np.random.default_rng(H+k).choice(pool,100,replace=False) for k in range(1,K+1)}
    R={k:np.random.default_rng(H+100+k).choice(np.array(sorted(set(pool)-set(S0[k]))),120,replace=False) for k in range(1,K+1)}
    dbdt=np.log10(4*s.frequency_Hz*s.amplitude_T); lo,hi=dbdt[pool].min(),dbdt[pool].max()
    b=np.clip(np.floor(8*(dbdt-lo)/(hi-lo)),0,7).astype(int)
    frontier=(~X)&(s.frequency_Hz>=1.5e5)&(s.amplitude_T>=.07)
    return dict(X7=Xi,G7=G,CAL7=C,pool=pool,S0=S0,R=R,gf=gf,cf=cf,bin=b,frontier=frontier)

def signflip(d):
    d=np.asarray(d,float); n=len(d); m=d.mean(); cnt=0
    hi=n-10; lowS=((np.arange(1024)[:,None]>>np.arange(10))&1)*2-1  # 1024 x 10
    lowsum=lowS@d[:10]
    for j in range(2**hi):
        s=((j>>np.arange(hi))&1)*2-1; tot=(lowsum+s@d[10:])/n; cnt+=int(np.sum(tot>=m-1e-12))
    return cnt/2**n

def arm_ids(arm,D):
    m,k=arm[0],int(arm[1:])
    if m=='R': return [int(x) for x in D['R'][k]]
    ids=[]
    for b in range(1,7):
        ids+=[int(p['sample_id']) for p in json.loads((OUT/'arms'/arm/f'batch_{b}.json').read_text())['points']]
    assert len(ids)==120==len(set(ids)); return ids

def main():
    F=features(); D=design(F); js=json.loads((OUT/'split.json').read_text()); diffs=[]
    for key in ('X7','G7','CAL7','pool'):
        if sorted(map(int,js[key]))!=list(map(int,D[key])): diffs.append(key)
    for k in range(1,K+1):
        if list(map(int,js[f'S0_{k}']))!=list(map(int,D['S0'][k])): diffs.append(f'S0_{k}')
        if list(map(int,js[f'R_{k}']))!=list(map(int,D['R'][k])): diffs.append(f'R_{k}')
    hold=set(D['X7'])|set(D['G7'])|set(D['CAL7']); res={}
    cal=F.loc[D['CAL7']]; n=len(cal); rank=int(np.ceil((n+1)*(1-ALPHA)))
    for arm in [f'{m}{k}' for k in range(1,K+1) for m in 'AMR']:
        k=int(arm[1:]); add=arm_ids(arm,D); tr=[int(x) for x in D['S0'][k]]+add
        assert not set(tr)&hold and len(set(tr))==220
        pred=fit(F.loc[tr]); mu,s=pred(cal); q=float(np.sort(np.abs(cal.y.to_numpy()-mu)/s)[rank-1])
        r=dict(q=q,frontier=int(D['frontier'].loc[add].sum()),bins=np.bincount(D['bin'].loc[add],minlength=8).tolist())
        for name in ('X7','G7'):
            X=F.loc[D[name]]; mu,s=pred(X); r[name]=metrics(X.y.to_numpy(),X.P.to_numpy(),mu,s,q)
        res[arm]=r; print(arm,json.dumps(r),flush=True)
    W=lambda m,S,k,f='winkler': res[f'{m}{k}'][S][f]; ks=range(1,K+1)
    Dd={'H1':[W('R','X7',k)-W('A','X7',k) for k in ks],'H2':[W('R','G7',k)-W('A','G7',k) for k in ks],
        'H3':[W('R','X7',k,'re')-W('A','X7',k,'re') for k in ks],'H4':[W('R','X7',k)-W('M','X7',k) for k in ks],
        'H5':[1.1*W('A','X7',k)-W('M','X7',k) for k in ks]}
    tests={}; stop=False
    for h,d in Dd.items():
        p=signflip(d); st='not_tested' if stop else ('rejected' if p<=.05 else 'not_rejected')
        if st!='rejected': stop=True
        tests[h]=dict(d=d,mean=float(np.mean(d)),median=float(np.median(d)),npos=int(np.sum(np.array(d)>0)),p=p,status=st)
    nG=len(D['G7'])
    ok=lambda a: res[a]['G7']['covered']>=int(np.ceil(.8*nG)) and res[a]['X7']['covered']>=506 and res[a]['X7']['width']<=3*res[a]['G7']['width']
    cv={m:sum(ok(f'{m}{k}') for k in ks) for m in 'AMR'}
    st=lambda h: tests[h]['status']=='rejected'
    claims={'A-X':st('H1') and cv['A']>=17,'A-G':st('H2') and cv['A']>=17,'A-RE':st('H3'),'M-X':st('H4') and cv['M']>=17,'M≈A':st('H5')}
    out=dict(split_diffs=diffs,n=dict(X7=len(D['X7']),G7=nG,CAL7=n,pool=len(D['pool'])),arms=res,tests=tests,cv_pass_counts=cv,claims=claims)
    (ROOT/'docs/reports/M8_rulings_checks_raw.json').write_text(json.dumps(out,ensure_ascii=False,indent=1,default=float))
    print(json.dumps(dict(split_diffs=diffs,n=out['n'],tests={h:(t['p'],t['status']) for h,t in tests.items()},cv=cv,claims=claims),ensure_ascii=False))
if __name__=='__main__': main()
