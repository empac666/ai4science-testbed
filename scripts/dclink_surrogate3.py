#!/usr/bin/env python3
"""预注册双臂评估；封存第一次结果，重复运行仅验证。"""
from dclink_design3 import ROOT,OUT,STAGE,SOURCE,FEATURES,verify,sha,freeze,freeze_bytes,encoded,digest
from dclink_active3 import CONFIG as ACTIVE_CONFIG,fit_m2
from dclink_surrogate2 import (CONFIG as MODEL_CONFIG,reviewer_b_features,gp_fit,interval_metrics,
                            conformal_quantile,normalized_quantile,evidence_metrics)
import argparse
import json
import os
import shutil
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
CONFIG=dict(model=MODEL_CONFIG,active=ACTIVE_CONFIG,methods=['m0','m1','m2'],
            design_seed=20261010,split_seed=20261011,calibration_n=60,calibration_rank=55,
            criteria={'test':48,'ood_corner':32,'ood_dt3':32},width_factor=3.,
            winkler_alpha=.1,wilcoxon_alternative='less',wilcoxon_zero_method='wilcox',
            wilcoxon_method='auto',wilcoxon_correction=False,p_threshold=.05,
            joint_simulations=100000,joint_seed=20261012,simulation_chunk=1000,
            duration_s=6,startup_s=1,solver_dt_ns=50,nonideal_seed_base=20270000,
            lhs_dimensions=4,smoke_duration_s=4,source_snapshot='be9a0f4')
SETS=['test','ood_corner','ood_dt3','supplement_corner','supplement_dt3']
NAMES=['surrogate_metrics.json','surrogate_evidence_metrics.json','predictions.csv','surrogate_metadata.json']

def verify_config():
    if json.loads((STAGE/'config_prerun.json').read_text())!=CONFIG: raise ValueError('Frozen CONFIG mismatch')

def winkler(y,lower,upper,alpha=.1):
    return upper-lower+2/alpha*(np.maximum(lower-y,0)+np.maximum(y-upper,0))

def paired(a,r):
    a=np.asarray(a); r=np.asarray(r)
    if np.array_equal(a,r): return dict(statistic=0.,pvalue=1.)
    test=wilcoxon(a,r,alternative=CONFIG['wilcoxon_alternative'],zero_method=CONFIG['wilcoxon_zero_method'],
                  method=CONFIG['wilcoxon_method'],correction=CONFIG['wilcoxon_correction'])
    return dict(statistic=float(test.statistic),pvalue=float(test.pvalue))

def criteria(metrics,arm):
    out={}; w=metrics[f'{arm}.m2.test.mean_width']
    for label,g in [('C1','test'),('C2-corner','ood_corner'),('C2-dt3','ood_dt3')]:
        p=f'{arm}.criterion.{label}'; q=f'{arm}.m2.{g}'
        out[p+'.covered']=metrics[q+'.covered']; out[p+'.n']=metrics[q+'.n']
        out[p+'.required_covered']=CONFIG['criteria'][g]
        out[p+'.coverage_pass']=metrics[q+'.covered']>=CONFIG['criteria'][g]
        out[p+'.mean_width']=metrics[q+'.mean_width']
        out[p+'.width_pass']=g=='test' or metrics[q+'.mean_width']<=CONFIG['width_factor']*w
        if g!='test': out[p+'.width_limit']=CONFIG['width_factor']*w
        out[p+'.pass']=out[p+'.coverage_pass'] and out[p+'.width_pass']
    out[f'{arm}.criterion.overall']=all(out[f'{arm}.criterion.{c}.pass'] for c in ('C1','C2-corner','C2-dt3'))
    return out

def joint_simulation():
    # Exchangeability specifies coverage ranks, not interval widths; simulate coverage only.
    rng=np.random.default_rng(CONFIG['joint_seed']); failed=0; counts=np.zeros(3,dtype=int)
    for start in range(0,CONFIG['joint_simulations'],CONFIG['simulation_chunk']):
        n=min(CONFIG['simulation_chunk'],CONFIG['joint_simulations']-start)
        q=np.sort(rng.uniform(size=(n,60)),axis=1)[:,54]
        bad=np.column_stack([(rng.uniform(size=(n,m))<=q[:,None]).sum(axis=1)<limit for m,limit in [(60,48),(40,32),(40,32)]])
        counts+=bad.sum(axis=0); failed+=int(bad.any(axis=1).sum())
    return {'joint_simulation.n':CONFIG['joint_simulations'],'joint_simulation.coverage_failed':failed,
            'joint_simulation.coverage_false_rejection':failed/CONFIG['joint_simulations'],
            **{f'joint_simulation.{g}.failed':int(c) for g,c in zip(['test','ood_corner','ood_dt3'],counts)}}

def load_new(path,design):
    df=pd.read_csv(path).set_index('case_id')
    assert not df.index.duplicated().any() and set(df.index)=={p['case_id'] for p in design}, 'Incomplete sweep'
    for p in design:
        r=df.loc[p['case_id']]
        assert r.group==p['group'] and not bool(r.ideal) and r.seed==p['nonideal_seed']
        assert np.allclose(r[FEATURES+['solver_dt_ns']].to_numpy(dtype=float),[p[k] for k in FEATURES+['solver_dt_ns']],rtol=1e-14,atol=1e-14)
    assert np.isfinite(df.y).all()
    return df.reset_index()

def evaluate(split,base,active,old):
    metrics={}; records=[]; metadata={}
    evaluation=pd.concat([base[base.group!='R'],old[old.group!='E-in']],ignore_index=True)
    labels={cid:g for g in ['calib',*SETS] for cid in split[g]}
    assert set(evaluation.case_id)==set(labels)
    for arm,new in [('active',active),('random',base[base.group=='R'])]:
        train=pd.concat([old[old.case_id.isin(split['s0'])],new],ignore_index=True)
        assert len(train)==260 and not set(train.case_id)&set(evaluation.case_id)
        scaler,coef,rgp=fit_m2(train)
        z=scaler.transform(evaluation[FEATURES].to_numpy()); y=evaluation.y.to_numpy()
        residual,s2=rgp.predict(z,return_std=True); p2=reviewer_b_features(evaluation[FEATURES].to_numpy())@coef+residual
        gp=gp_fit(scaler.transform(train[FEATURES].to_numpy()),train.y.to_numpy()); p0,s0=gp.predict(z,return_std=True)
        s0=np.maximum(s0,MODEL_CONFIG['normalized_sigma_floor']); s2=np.maximum(s2,MODEL_CONFIG['normalized_sigma_floor'])
        cal=evaluation.case_id.isin(split['calib']).to_numpy(); assert cal.sum()==60
        metadata[arm]=dict(training_ids=train.case_id.tolist(),linear_coef=coef.tolist(),gp_kernel=str(gp.kernel_),
                           residual_kernel=str(rgp.kernel_),scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist())
        for method,pred,sigma in [('m0',p0,np.ones(len(y))),('m1',p0,s0),('m2',p2,s2)]:
            q=normalized_quantile(y[cal],pred[cal],sigma[cal]); half=q*sigma
            metrics[f'{arm}.{method}.calib.q']=q
            for group in SETS:
                mask=evaluation.case_id.isin(split[group]).to_numpy()
                metrics.update({f'{arm}.{method}.{group}.{k}':v for k,v in interval_metrics(y[mask],pred[mask],half[mask]).items()})
            supplement=evaluation.case_id.isin(split['supplement_corner']+split['supplement_dt3']).to_numpy()
            metrics.update({f'{arm}.{method}.supplement_ood.{k}':v for k,v in interval_metrics(y[supplement],pred[supplement],half[supplement]).items()})
            for i,cid in enumerate(evaluation.case_id):
                records.append(dict(arm=arm,method=method,case_id=cid,split=labels[cid],y=y[i],prediction=pred[i],
                                    sigma=sigma[i],lower=pred[i]-half[i],upper=pred[i]+half[i]))
        metrics.update(criteria(metrics,arm))
    predictions=pd.DataFrame(records)
    for group in ('ood_corner','ood_dt3'):
        subset=predictions[(predictions.method=='m2')&(predictions['split']==group)]
        scores={arm:r.sort_values('case_id') for arm,r in subset.groupby('arm')}
        a,r=scores['active'],scores['random']; assert a.case_id.tolist()==r.case_id.tolist()
        sa=winkler(a.y.to_numpy(),a.lower.to_numpy(),a.upper.to_numpy()); sr=winkler(r.y.to_numpy(),r.lower.to_numpy(),r.upper.to_numpy())
        metrics.update({f'paired.{group}.{k}':v for k,v in paired(sa,sr).items()})
        metrics[f'paired.{group}.active_mean_winkler']=float(sa.mean()); metrics[f'paired.{group}.random_mean_winkler']=float(sr.mean())
    metrics['comparison.P-a.active_covered']=metrics['active.m2.ood_corner.covered']
    metrics['comparison.P-a.random_covered']=metrics['random.m2.ood_corner.covered']
    metrics['comparison.P-a.pass']=metrics['active.m2.ood_corner.covered']>=metrics['random.m2.ood_corner.covered']
    metrics['comparison.P-b.pvalue']=metrics['paired.ood_corner.pvalue']
    metrics['comparison.P-b.pass']=metrics['paired.ood_corner.pvalue']<CONFIG['p_threshold']
    metrics['comparison.P.pass']=metrics['comparison.P-a.pass'] and metrics['comparison.P-b.pass']
    metrics['criterion.overall']=metrics['active.criterion.overall'] and metrics['comparison.P.pass']
    metrics['active.sampled.corner']=int(((active.load<=.35)&(active.bw_iac_khz<=75)).sum())
    metrics['active.sampled.dt3']=int((active.dead_time_us==3).sum())
    metrics.update(joint_simulation())
    return metrics,predictions,metadata

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--freeze-config',action='store_true'); a=ap.parse_args()
    if a.freeze_config: freeze(STAGE/'config_prerun.json',CONFIG); verify_config(); return
    verify_config(); split=verify()
    paths=[OUT/'sweep_base.csv',OUT/'sweep_active.csv',SOURCE,OUT/'design.json',OUT/'pool.json',OUT/'split.json',
           STAGE/'config_prerun.json',ROOT/'scripts/dclink_surrogate.py',ROOT/'scripts/dclink_surrogate2.py',
           ROOT/'scripts/dclink_surrogate3.py',ROOT/'scripts/dclink_active3.py',ROOT/'data/dclink_src/simsw/dclink_simsw/common.py']
    paths += [OUT/'active'/f'batch_{b}.json' for b in range(1,6)]
    fingerprint=dict(config=CONFIG,input_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths})
    first=STAGE/'first'
    if first.exists():
        assert json.loads((first/'provenance.json').read_text())==fingerprint, 'First provenance changed'
        hashes=json.loads((first/'artifact_hashes.json').read_text())
        for name in NAMES:
            assert sha(first/name)==hashes[name]
            for dest in (OUT,STAGE): freeze_bytes(dest/name,(first/name).read_bytes())
        print('First evaluation verified; no refitting or overwrite.'); return
    design=json.loads((OUT/'design.json').read_text()); batches=[json.loads((OUT/'active'/f'batch_{b}.json').read_text()) for b in range(1,6)]
    active_design=[p for b in batches for p in b['points']]
    assert len(active_design)==110 and len({p['pool_id'] for p in active_design})==110
    for b in batches: assert b['sha256']==digest({k:v for k,v in b.items() if k!='sha256'})
    base=load_new(OUT/'sweep_base.csv',design); active=load_new(OUT/'sweep_active.csv',active_design)
    old=pd.read_csv(SOURCE); assert set(old.case_id)==set(split['s0']+split['supplement_corner']+split['supplement_dt3'])
    assert not old.ideal.any() and np.isfinite(old.y).all()
    metrics,pred,metadata=evaluate(split,base,active,old)
    metadata.update(provenance=fingerprint,batches=batches,
                    joint_simulation_scope='coverage counts only; exchangeability does not specify widths')
    artifacts={'surrogate_metrics.json':encoded(metrics),'surrogate_evidence_metrics.json':encoded(evidence_metrics(metrics)),
               'predictions.csv':pred.to_csv(index=False).encode(),'surrogate_metadata.json':encoded(metadata)}
    pending=STAGE/'first.pending'; pending.mkdir(exist_ok=True)
    for n,body in artifacts.items(): (pending/n).write_bytes(body)
    (pending/'provenance.json').write_bytes(encoded(fingerprint))
    (pending/'artifact_hashes.json').write_bytes(encoded({n:sha(pending/n) for n in NAMES}))
    pending.rename(first)
    for n,body in artifacts.items():
        freeze_bytes(OUT/n,body); freeze_bytes(STAGE/n,body)
    print(json.dumps(metrics,ensure_ascii=False))
if __name__=='__main__': main()
