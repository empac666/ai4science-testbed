#!/usr/bin/env python3
"""18 臂独立拟合、K=6 精确符号翻转及固定顺序检验；首次评估原子封存。"""
from dclink_active5 import (ROOT,OUT,STAGE,R3,SOURCE,FEATURES,CONFIG,MODEL_CONFIG,ADAPTIVE,
                         verify,fit_m2,sha,digest,freeze,freeze_bytes,encoded)
import argparse
import fcntl
import itertools
import json
import numpy as np
import pandas as pd
from dclink_surrogate2 import reviewer_b_features,gp_fit,normalized_quantile,interval_metrics,evidence_metrics
from dclink_surrogate3 import winkler,load_new,SETS as OLD_SETS
from dclink_surrogate4 import sampling
ARMS=[f'{x}{k}' for k in range(1,7) for x in ('A','M','R')]
SETS=['T5','C5','D5',*OLD_SETS]
NAMES=['surrogate_metrics.json','surrogate_evidence_metrics.json','predictions.csv','surrogate_metadata.json']

def sign_flip(d):
    d=np.asarray(d,dtype=float)
    assert d.shape==(6,) and np.isfinite(d).all()
    observed=float(d.mean())
    values=np.asarray(list(itertools.product((-1.,1.),repeat=6)))@d/6
    return float(np.count_nonzero(values>=observed-1e-12)/64)

def fixed_sequence(pvalues):
    assert len(pvalues)==4
    enabled=True; statuses=[]
    for p in pvalues:
        assert 0<=p<=1
        status=('rejected' if p<.05 else 'not_rejected') if enabled else 'not_tested'
        statuses.append(status); enabled=enabled and status=='rejected'
    return statuses

def criteria(m,arm):
    values={}; width=m[f'{arm}.m2.T5.mean_width']
    for label,g,n,threshold in [('C1','T5',60,48),('C2-corner','C5',40,32),('C2-dt3','D5',40,32)]:
        assert m[f'{arm}.m2.{g}.n']==n
        values[f'{arm}.criterion.{label}.pass']=bool(m[f'{arm}.m2.{g}.covered']>=threshold and
                                                    (g=='T5' or m[f'{arm}.m2.{g}.mean_width']<=3*width))
    values[f'{arm}.criterion.overall']=all(values.values())
    return values

def decision(m):
    out={}
    for arm in ARMS: out.update(criteria(m,arm))
    for x in ('A','M','R'):
        n=sum(out[f'{x}{k}.criterion.overall'] for k in range(1,7))
        out[f'CV-{x}.count']=n; out[f'CV-{x}.pass']=n>=5
    get=lambda a,g:np.array([m[f'{a}{k}.m2.{g}.mean_winkler'] for k in range(1,7)])
    ac,mc,rc,ad,md=get('A','C5'),get('M','C5'),get('R','C5'),get('A','D5'),get('M','D5')
    differences=[rc-ac,rc-mc,1.10*ac-mc,ad-md]; pvalues=[sign_flip(d) for d in differences]
    for h,d,p,status in zip(('H1','H2','H3','H4'),differences,pvalues,fixed_sequence(pvalues)):
        out[f'{h}.pvalue']=p; out[f'{h}.status']=status; out[f'{h}.rejected']=status=='rejected'
        out[f'{h}.mean_difference']=float(d.mean())
        for k,v in enumerate(d,1): out[f'{h}.d{k}']=float(v)
    out.update({'claim_A':out['H1.rejected'] and out['CV-A.pass'],
                'claim_M':out['H2.rejected'] and out['CV-M.pass'],
                'claim_M_noninf':out['H3.rejected'],'claim_M_dt3':out['H4.rejected']})
    return out

def evaluate_arm(arm,train,evaluation,labels,sets):
    """Same model/interval primitives and operation order as R3; arbitrary held-out labels."""
    assert len(train)==260 and len(set(train.case_id))==260
    assert not set(train.case_id)&set(evaluation.case_id)
    assert set(evaluation.case_id)==set(labels) and not evaluation.case_id.duplicated().any()
    scaler,coef,rgp=fit_m2(train)
    x=evaluation[FEATURES].to_numpy(); z=scaler.transform(x); y=evaluation.y.to_numpy()
    residual,s2=rgp.predict(z,return_std=True); p2=reviewer_b_features(x)@coef+residual
    gp=gp_fit(scaler.transform(train[FEATURES].to_numpy()),train.y.to_numpy()); p0,s0=gp.predict(z,return_std=True)
    s0=np.maximum(s0,MODEL_CONFIG['normalized_sigma_floor']); s2=np.maximum(s2,MODEL_CONFIG['normalized_sigma_floor'])
    cal=np.array([labels[cid]=='calib' for cid in evaluation.case_id]); assert cal.sum()==60
    metrics={}; records=[]
    for method,pred,sigma in [('m0',p0,np.ones(len(y))),('m1',p0,s0),('m2',p2,s2)]:
        q=normalized_quantile(y[cal],pred[cal],sigma[cal]); half=q*sigma
        assert q==float(np.sort(abs(y[cal]-pred[cal])/sigma[cal])[54])
        metrics[f'{arm}.{method}.calib.q']=q
        for group in [*sets,'supplement_ood']:
            groups=['supplement_corner','supplement_dt3'] if group=='supplement_ood' else [group]
            mask=np.array([labels[cid] in groups for cid in evaluation.case_id])
            metrics.update({f'{arm}.{method}.{group}.{k}':v for k,v in interval_metrics(y[mask],pred[mask],half[mask]).items()})
        records.extend(dict(arm=arm,method=method,case_id=cid,split=labels[cid],y=y[i],prediction=pred[i],
                            sigma=sigma[i],lower=pred[i]-half[i],upper=pred[i]+half[i]) for i,cid in enumerate(evaluation.case_id))
    pred=pd.DataFrame(records)
    for group in [g for g in ('C5','D5','ood_corner','ood_dt3') if g in sets]:
        rows=pred[(pred.method=='m2')&(pred['split']==group)].sort_values('case_id')
        metrics[f'{arm}.m2.{group}.mean_winkler']=float(winkler(rows.y.to_numpy(),rows.lower.to_numpy(),rows.upper.to_numpy()).mean())
    meta=dict(training_ids=train.case_id.tolist(),linear_coef=coef.tolist(),gp_kernel=str(gp.kernel_),
              residual_kernel=str(rgp.kernel_),scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist())
    return metrics,pred,meta

def numeric_metrics(metrics):
    return {k:v for k,v in metrics.items() if isinstance(v,(int,float,bool))}

def evaluate(split,base,arms,old_base,old,checkpoint=None):
    evaluation=pd.concat([old_base[old_base.group!='R'],old[old.group!='E-in'],base[base.group.isin(['T5','C5','D5'])]],ignore_index=True)
    labels={cid:g for g in ['calib',*OLD_SETS] for cid in split[g]}
    labels.update({r.case_id:r.group for r in base[base.group.isin(['T5','C5','D5'])].itertuples()})
    assert set(arms)==set(ARMS)
    metrics={}; predictions=[]; metadata={}
    for arm in ARMS:
        new=arms[arm]; assert len(new)==110
        train=pd.concat([old[old.case_id.isin(split['s0'])],new],ignore_index=True)
        cache=checkpoint/f'{arm}.json' if checkpoint else None
        fp=digest(dict(train=train[['case_id',*FEATURES,'y']].to_dict('records'),
                       evaluation=evaluation[['case_id',*FEATURES,'y']].to_dict('records'),labels=labels))
        if cache and cache.exists():
            data=json.loads(cache.read_text()); assert data['fingerprint']==fp
            assert data['sha256']==digest({k:v for k,v in data.items() if k!='sha256'})
            m,p,meta=data['metrics'],pd.DataFrame(data['predictions']),data['metadata']
        else:
            m,p,meta=evaluate_arm(arm,train,evaluation,labels,SETS)
            if cache:
                data=dict(fingerprint=fp,metrics=m,predictions=p.to_dict('records'),metadata=meta)
                data['sha256']=digest(data); freeze(cache,data)
        metrics.update(m); metadata[arm]=meta; predictions.append(p)
        metrics.update({f'{arm}.sampled.{k}':v for k,v in sampling(new).items()})
    metrics.update(decision(metrics))
    metrics['report.M.dt3_le27_count']=sum(metrics[f'M{k}.sampled.dt3']<=27 for k in range(1,7))
    covered=[metrics[f'R{k}.m2.C5.covered'] for k in range(1,7)]
    metrics['report.R.C5.covered.mean']=float(np.mean(covered)); metrics['report.R.C5.covered.std']=float(np.std(covered,ddof=1))
    return metrics,pd.concat(predictions,ignore_index=True),metadata

def regression_check(split):
    """Refit R4 A and RS1 using this exact evaluator; require bit-for-bit M2 values."""
    old=pd.read_csv(SOURCE); base=pd.read_csv(R3/'sweep_base.csv')
    evaluation=pd.concat([base[base.group!='R'],old[old.group!='E-in']],ignore_index=True)
    labels={cid:g for g in ['calib',*OLD_SETS] for cid in split[g]}
    reference=json.loads((ROOT/'lab/cases/dclink4/first/surrogate_metrics.json').read_text())
    random=pd.read_csv(ROOT/'lab/cases/dclink4/sweep_random.csv')
    new_arms={'A':pd.read_csv(R3/'sweep_active.csv'),'RS1':random[random.group=='RS1']}
    checked=[]
    for arm,new in new_arms.items():
        train=pd.concat([old[old.case_id.isin(split['s0'])],new],ignore_index=True)
        metrics,_,_=evaluate_arm(arm,train,evaluation,labels,OLD_SETS)
        for key,value in reference.items():
            if key.startswith(arm+'.m2.'):
                assert metrics[key]==value, f'R4 bitwise regression: {key}: {metrics[key]} != {value}'
                checked.append(key)
    return dict(verified=True,checked_keys=checked,n=len(checked))

def inputs():
    paths=[SOURCE,R3/'sweep_base.csv',R3/'sweep_active.csv',R3/'pool.json',ROOT/'data/dclink3/split.json',
           ROOT/'lab/cases/dclink4/sweep_random.csv',ROOT/'lab/cases/dclink4/first/surrogate_metrics.json',
           STAGE/'config_prerun.json',STAGE/'design.json',STAGE/'design_manifest.json',OUT/'design.json',
           OUT/'sweep_base.csv',OUT/'sweep_adaptive.csv',OUT/'runtime/replay_provenance.json',
           ROOT/'docs/prereg/M6_surrogate_round5_prereg.md']
    paths += [OUT/'adaptive'/arm/f'batch_{b}.json' for arm in ADAPTIVE for b in range(1,6)]
    paths += [ROOT/'scripts'/name for name in ('dclink_active5.py','dclink_surrogate5.py','dclink_sweep5.py','dclink_design5.py',
              'dclink_active3.py','dclink_active4.py','dclink_surrogate3.py','dclink_surrogate4.py','dclink_surrogate2.py','dclink_surrogate.py',
              'dclink_sweep4.py','dclink_sweep3.py','dclink_sweep2.py','dclink_sweep.py')]
    paths += sorted((ROOT/'data/dclink_src/simsw/dclink_simsw').glob('*.py'))+[ROOT/'data/dclink_src/replay/run_replay.py']
    return paths

def load_inputs():
    design=json.loads((OUT/'design.json').read_text()); points=[]
    for arm in ADAPTIVE:
        own=[]
        for b in range(1,6):
            rec=json.loads((OUT/'adaptive'/arm/f'batch_{b}.json').read_text())
            assert rec['sha256']==digest({k:v for k,v in rec.items() if k!='sha256'})
            assert rec['fingerprint']['arm']==arm and rec['fingerprint']['batch']==b and not rec['fingerprint']['smoke']
            assert len(rec['points'])==22
            freeze(STAGE/'adaptive'/arm/f'batch_{b}.json',rec); own.extend(rec['points'])
        from dclink_active5 import assign
        assert all(p==assign(p,arm,j) for j,p in enumerate(own))
        assert len({p['pool_id'] for p in own})==110
        points.extend(own)
    base=load_new(OUT/'sweep_base.csv',design); adaptive=load_new(OUT/'sweep_adaptive.csv',points)
    arms={arm:(base if arm[0]=='R' else adaptive).query('group == @arm').copy() for arm in ARMS}
    return base,arms

def run(split):
    fingerprint=dict(config=CONFIG,input_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs()})
    first=STAGE/'first'
    if first.exists():
        assert json.loads((first/'provenance.json').read_text())==fingerprint
        hashes=json.loads((first/'artifact_hashes.json').read_text())
        for name in NAMES:
            assert sha(first/name)==hashes[name]
            for dest in (OUT,STAGE): freeze_bytes(dest/name,(first/name).read_bytes())
        print('首次评估及 provenance 核对通过；未重拟合。'); return
    checkpoint=OUT/'evaluation_checkpoint'; freeze(checkpoint/'provenance.json',fingerprint)
    regression=checkpoint/'regression.json'
    if regression.exists():
        checks=json.loads(regression.read_text()); assert checks['verified']
    else:
        checks=regression_check(split); freeze(regression,checks)
    base,arms=load_inputs(); old=pd.read_csv(SOURCE); old_base=pd.read_csv(R3/'sweep_base.csv')
    assert not old.ideal.any() and np.isfinite(old.y).all()
    metrics,pred,meta=evaluate(split,base,arms,old_base,old,checkpoint)
    meta.update(provenance=fingerprint,regression=checks,calibration_rank=55,
                inference='K=6 paired; conditional on S0; fixed H1→H2→H3→H4; old sets and M0/M1 report only')
    artifacts={'surrogate_metrics.json':encoded(metrics),'predictions.csv':pred.to_csv(index=False).encode(),
               'surrogate_evidence_metrics.json':encoded(evidence_metrics(numeric_metrics(metrics))),
               'surrogate_metadata.json':encoded(meta)}
    pending=STAGE/'first.pending'; pending.mkdir(exist_ok=True)
    for name,body in artifacts.items(): freeze_bytes(pending/name,body)
    freeze(pending/'provenance.json',fingerprint); freeze(pending/'artifact_hashes.json',{n:sha(pending/n) for n in NAMES})
    pending.rename(first)
    for name,body in artifacts.items():
        for dest in (OUT,STAGE): freeze_bytes(dest/name,body)
    print(json.dumps({k:v for k,v in metrics.items() if k.startswith('claim_')},ensure_ascii=False))

def main():
    split=verify(); ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--regression-only',action='store_true'); a=ap.parse_args()
    if a.regression_only:
        result=regression_check(split); freeze(ROOT/'data/dclink5_smoke/regression.json',result); print(json.dumps(result)); return
    with (OUT/'.evaluation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); run(split)
if __name__=='__main__': main()
