#!/usr/bin/env python3
"""事后探索（exploratory，不改变第二轮预注册判定）：检验 reviewer_b 评审第 5 条的推测——
M2 解析均值加入交互项 (f_grid/bw_iac)/load 后，E-corner 的偏差与覆盖是否改善。
只用第二轮已冻结的数据与划分；GP/保形配置与 M2 完全相同。E-corner 已被看过，结果只作为下一轮预注册候选。
输出 docs/reports/M3_explore_interaction.json。"""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from sklearn.preprocessing import StandardScaler
import dclink_surrogate2 as s2
split=s2.verify(); design=json.loads((s2.OUT/'design.json').read_text())
ideal=s2.load_sweep(s2.OUT/'sweep_ideal.csv',design,True)
old=pd.read_csv(ROOT/'data/dclink/sweep.csv').sort_values('case_id').reset_index(drop=True)
df=pd.concat([old,ideal],ignore_index=True)
x=df[['load','dead_time_us','bw_iac_khz','aperture_delay_us']].to_numpy(); y=df.y.to_numpy()
train=df.case_id.isin(split['train']).to_numpy(); calib=df.case_id.isin(split['calib']).to_numpy()
scale=StandardScaler().fit(x[train]); z=scale.transform(x)
base=s2.reviewer_b_features(x)
variants={'m2_reproduced':base,'m2_plus_bw_over_load':np.column_stack([base,base[:,3]/x[:,0]])}
out={'note':'exploratory; E-corner already seen; not a pre-registered result'}
for name,a in variants.items():
    c=np.linalg.lstsq(a[train],y[train],rcond=None)[0]; lin=a@c
    rgp=s2.gp_fit(z[train],y[train]-lin[train]); r,s=rgp.predict(z,return_std=True)
    s=np.maximum(s,s2.CONFIG['normalized_sigma_floor']); pred=lin+r
    q=s2.normalized_quantile(y[calib],pred[calib],s[calib]); out[f'{name}.q']=float(q)
    for g in ('test','ood_dt3','ood_corner','supplement_ood'):
        m=df.case_id.isin(split[g]).to_numpy()
        out.update({f'{name}.{g}.{k}':v for k,v in s2.interval_metrics(y[m],pred[m],q*s[m]).items()})
(ROOT/'docs/reports/M3_explore_interaction.json').write_text(json.dumps(out,ensure_ascii=False,indent=1)+'\n')
for k,v in out.items(): print(k,v)
