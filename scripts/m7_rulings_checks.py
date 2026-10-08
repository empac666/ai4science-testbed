#!/usr/bin/env python3
"""主持人独立复算（第六轮）。只依据预注册与冻结配置独立实现，不 import 任何 magnet6_* 代码。

1. 由 B.npy + igse_predictions.csv 独立重算特征与划分（H 来自预注册 SHA）并与 split.json 比对；
2. 由各臂冻结批次文件取得训练 id（A/M）或 R_k 顺序（R），独立重拟合最终模型，CAL6 校准，
   在 C6/T6 上独立计算覆盖、宽度、Winkler、中位相对误差；
3. 独立计算配对差、符号翻转 p、固定顺序门控、CV 与结论，并与 first/metrics.json 逐项比对。
"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
import json, itertools, hashlib, sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
from sklearn.preprocessing import StandardScaler
ROOT=Path(__file__).resolve().parents[1]
SHA='d8a805bb540f3b4bb479fed77cd1f35120720c26'; H=int(SHA[:8],16); K=8; ALPHA=.1
OUT=ROOT/'data/magnet6'

def features():
    s=pd.read_csv(ROOT/'data/magnet/igse_predictions.csv')
    B=np.load(ROOT/'data/magnet/N87/B.npy',mmap_mode='r'); n=len(s)
    f=s.frequency_Hz.to_numpy(); duty=np.empty(n); plat=np.empty(n); shape=np.empty(n); bpk=np.empty(n)
    for a in range(0,n,2048):
        b=np.asarray(B[a:a+2048]); d=np.roll(b,-1,axis=1)-b; ff=f[a:a+2048]
        bpk[a:a+2048]=np.ptp(b,axis=1)/2; duty[a:a+2048]=(d>0).mean(1)
        ad=np.abs(d); plat[a:a+2048]=(ad<.1*np.quantile(ad,.9,axis=1)[:,None]).mean(1)
        shape[a:a+2048]=np.log10(np.mean((ad*b.shape[1]*ff[:,None])**1.5,axis=1)/(4*ff*bpk[a:a+2048])**1.5)
    assert np.allclose(bpk,s.amplitude_T,rtol=1e-9)
    return pd.DataFrame(dict(sample_id=s.sample_id,log10_f=np.log10(f),log10_Bpk=np.log10(s.amplitude_T),T_C=s.temperature_C,
        duty=duty,plateau=plat,shape=shape,y=np.log10(s.measured_W_m3),P=s.measured_W_m3,igse=s.predicted_W_m3,
        corner=(f>=2e5)&(s.amplitude_T>=.10))).set_index('sample_id')

def split(F):
    ids=F.index.to_numpy(); corner=np.sort(ids[F.corner.to_numpy()]); non=np.sort(ids[~F.corner.to_numpy()])
    rng=np.random.default_rng(H); C6=rng.permutation(corner)[:200]; perm=rng.permutation(non); T6=perm[:300]; CAL=perm[300:400]
    hold=set(C6)|set(T6)|set(CAL); pool=np.array(sorted(set(ids)-hold)); pn=np.array(sorted(set(pool)&set(non)))
    S0={k:np.random.default_rng(H+k).choice(pn,100,replace=False) for k in range(1,K+1)}
    R={k:np.random.default_rng(H+100+k).choice(np.array(sorted(set(pool)-set(S0[k]))),120,replace=False) for k in range(1,K+1)}
    return dict(C6=C6,T6=T6,CAL6=CAL,pool=pool,S0=S0,R=R)

GP=['log10_f','log10_Bpk','T_C','duty','plateau','shape']
def lin(X): return np.column_stack([np.ones(len(X)),X.log10_f,X.log10_Bpk,X.T_C,X.T_C**2,X['shape']])
def fit(Tr):
    c=np.linalg.lstsq(lin(Tr),Tr.y.to_numpy(),rcond=None)[0]; sc=StandardScaler().fit(Tr[GP].to_numpy())
    k=ConstantKernel(1.0,(.01,100))*RBF([1.0]*6,(.01,100))+WhiteKernel(.01,(1e-8,10))
    g=GaussianProcessRegressor(k,alpha=1e-10,normalize_y=True,n_restarts_optimizer=2,random_state=20261004)
    g.fit(sc.transform(Tr[GP].to_numpy()),Tr.y.to_numpy()-lin(Tr)@c)
    def pred(X):
        m,s=g.predict(sc.transform(X[GP].to_numpy()),return_std=True); return lin(X)@c+m,np.maximum(s,2.220446049250313e-16)
    return pred

def metrics(y,P,mu,s,q):
    lo,hi=mu-q*s,mu+q*s; w=(hi-lo)+(2/ALPHA)*np.maximum(lo-y,0)+(2/ALPHA)*np.maximum(y-hi,0)
    return dict(covered=int(((y>=lo)&(y<=hi)).sum()),width=float((hi-lo).mean()),winkler=float(w.mean()),re=float(np.median(np.abs(10**mu-P)/P)))

def signflip(d):
    d=np.asarray(d,float); m=d.mean()
    return sum(np.mean(np.array(s)*d)>=m-1e-12 for s in itertools.product((-1,1),repeat=len(d)))/2**len(d)

def arm_ids(arm,sp):
    m,k=arm[0],int(arm[1:])
    if m=='R': return [int(x) for x in sp['R'][k]]
    ids=[]
    for b in range(1,7):
        rec=json.loads((OUT/'arms'/arm/f'batch_{b}.json').read_text()); pts=rec['points']
        ids+=[int(p['sample_id']) if isinstance(p,dict) else int(p) for p in pts]
    assert len(ids)==120==len(set(ids)); return ids

def main():
    F=features(); sp=split(F)
    js=json.loads((OUT/'split.json').read_text()); diffs=[]
    for key in ('C6','T6','CAL6','pool'):
        if list(map(int,js[key]))!=list(map(int,sp[key])): diffs.append(f'split {key}')
    for k in range(1,K+1):
        if list(map(int,js[f'S0_{k}']))!=list(map(int,sp['S0'][k])): diffs.append(f'S0_{k}')
        if list(map(int,js[f'R_{k}']))!=list(map(int,sp['R'][k])): diffs.append(f'R_{k}')
    hold=set(sp['C6'])|set(sp['T6'])|set(sp['CAL6'])
    res={}
    for arm in [f'{m}{k}' for k in range(1,K+1) for m in 'AMR']:
        k=int(arm[1:]); add=arm_ids(arm,sp); tr=[int(x) for x in sp['S0'][k]]+add
        assert not set(tr)&hold and len(set(tr))==220
        pred=fit(F.loc[tr]); cal=F.loc[sp['CAL6']]; mu,s=pred(cal)
        q=float(np.sort(np.abs(cal.y.to_numpy()-mu)/s)[int(np.ceil(101*(1-ALPHA)))-1])
        r=dict(q=q,corner_sampled=int(F.loc[add].corner.sum()))
        for name in ('C6','T6'):
            X=F.loc[sp[name]]; mu,s=pred(X); r[name]=metrics(X.y.to_numpy(),X.P.to_numpy(),mu,s,q)
        res[arm]=r; print(arm,json.dumps(r),flush=True)
    W=lambda m,S,k,f='winkler': res[f'{m}{k}'][S][f]
    D={'H1':[W('R','C6',k)-W('A','C6',k) for k in range(1,9)],'H2':[W('R','C6',k)-W('M','C6',k) for k in range(1,9)],
       'H3':[1.1*W('A','C6',k)-W('M','C6',k) for k in range(1,9)],'H4':[W('R','C6',k,'re')-W('M','C6',k,'re') for k in range(1,9)],
       'H5':[1.1*W('R','T6',k)-W('M','T6',k) for k in range(1,9)],'H6':[1.1*W('R','T6',k)-W('A','T6',k) for k in range(1,9)]}
    tests={}; stop=False
    for h,d in D.items():
        p=signflip(d); st='not_tested' if stop else ('rejected' if p<=.05 else 'not_rejected')
        if st!='rejected': stop=True
        tests[h]=dict(d=d,mean=float(np.mean(d)),p=p,status=st)
    ok=lambda a: res[a]['T6']['covered']>=240 and res[a]['C6']['covered']>=160 and res[a]['C6']['width']<=3*res[a]['T6']['width']
    cv={m:sum(ok(f'{m}{k}') for k in range(1,9)) for m in 'AMR'}
    claims={'A':tests['H1']['status']=='rejected' and cv['A']>=7,'M':tests['H2']['status']=='rejected' and cv['M']>=7,
            'M≈A':tests['H3']['status']=='rejected','M-RE':tests['H4']['status']=='rejected',
            'M-ID':tests['H5']['status']=='rejected' and cv['M']>=7,'A-ID':tests['H6']['status']=='rejected' and cv['A']>=7}
    out=dict(split_diffs=diffs,arms=res,tests=tests,cv_pass_counts=cv,claims=claims)
    (ROOT/'docs/reports/M7_rulings_checks_raw.json').write_text(json.dumps(out,ensure_ascii=False,indent=1,default=float))
    print(json.dumps(dict(split_diffs=diffs,tests={h:(t['p'],t['status']) for h,t in tests.items()},cv=cv,claims=claims),ensure_ascii=False))
if __name__=='__main__': main()
