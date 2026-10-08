#!/usr/bin/env python3
"""复用第三轮数学；八臂评估、两个独立假设与首次原子封存。"""
from dclink_active4 import ROOT,OUT,STAGE,R3,SOURCE,CONFIG,verify,sha,digest,freeze,freeze_bytes,encoded
import json
import argparse
import os
import fcntl
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
import dclink_surrogate3 as r3
from dclink_surrogate2 import evidence_metrics
ARMS=['A','R','RS1','RS2','RS3','RS4','RS5','M']
RANDOM=[f'RS{i}' for i in range(1,6)]
NAMES=['surrogate_metrics.json','surrogate_evidence_metrics.json','predictions.csv','surrogate_metadata.json']

def paired(a,b,alternative='less'):
    options=dict(CONFIG['wilcoxon'],alternative=alternative)
    if np.array_equal(a,b): return dict(statistic=0.,pvalue=1.)
    result=wilcoxon(a,b,**options)
    return dict(statistic=float(result.statistic),pvalue=float(result.pvalue))

def sampling(frame):
    return dict(corner=int(((frame.load<=.35)&(frame.bw_iac_khz<=75)).sum()),
                dt3=int((frame.dead_time_us==3).sum()),low_load=int((frame.load<=.35).sum()),
                **{f'dead_time_{c:.1f}':int((frame.dead_time_us==c).sum()) for c in np.arange(0,3.5,.5)})

def decision(metrics,scores,dt3,pvalue=None):
    cover=lambda arm: metrics[f'{arm}.m2.ood_corner.covered']
    means={arm:float(np.mean(scores[arm])) for arm in ['A','M',*RANDOM]}
    random_cov=[cover(arm) for arm in RANDOM]
    p=paired(scores['A'],np.mean([scores[a] for a in RANDOM],axis=0))['pvalue'] if pvalue is None else pvalue
    values={'A-1':all(means['A']<means[a] for a in RANDOM),
            'A-2':all(cover('A')>=c for c in random_cov) and cover('A')-np.mean(random_cov)>=4,
            'A-3':p<CONFIG['p_threshold'],'M-0':dt3<=27,
            'M-1':r3.criteria(metrics,'M')['M.criterion.overall'],
            'M-2':cover('M')>=36 and all(means['M']<means[a] for a in RANDOM)}
    values['H-A']=all(values[k] for k in ('A-1','A-2','A-3'))
    values['H-M']=all(values[k] for k in ('M-0','M-1','M-2'))
    result={f'criterion.{k}.pass':bool(v) for k,v in values.items()}
    result.update({'criterion.A-3.pvalue':float(p),'random.corner_covered.mean':float(np.mean(random_cov)),
                   'random.corner_covered.std':float(np.std(random_cov,ddof=1)),
                   'random.C_pass_count':sum(bool(r3.criteria(metrics,a)[f'{a}.criterion.overall']) for a in RANDOM)})
    return result

def reports(metrics,pred,arms):
    scores={}
    for group in ('ood_corner','ood_dt3'):
        block=pred[(pred.method=='m2')&(pred['split']==group)]; ids=None; group_scores={}
        for arm in ARMS:
            rows=block[block.arm==arm].sort_values('case_id')
            if ids is None: ids=rows.case_id.tolist()
            assert rows.case_id.tolist()==ids and len(rows)==40
            group_scores[arm]=r3.winkler(rows.y.to_numpy(),rows.lower.to_numpy(),rows.upper.to_numpy())
            metrics[f'{arm}.m2.{group}.mean_winkler']=float(group_scores[arm].mean())
        metrics.update({f'report.M_vs_A.{group}.{k}':v for k,v in paired(group_scores['M'],group_scores['A'],'two-sided').items()})
        if group=='ood_corner': scores=group_scores
    for arm,frame in arms.items():
        metrics.update({f'{arm}.sampled.{k}':v for k,v in sampling(frame).items()})
    metrics.update(decision(metrics,scores,metrics['M.sampled.dt3']))
    return metrics

def evaluate(split,base,arms,old,checkpoint=None):
    """Each pair uses the unchanged R3 evaluate, including training/evaluation row order."""
    metrics={}; predictions=[]; metadata={}
    for left,right in zip(ARMS[::2],ARMS[1::2]):
        cache=checkpoint/f'{left}_{right}.json' if checkpoint else None
        if cache and cache.exists():
            data=json.loads(cache.read_text()); m=data['metrics']; p=pd.DataFrame(data['predictions']); meta=data['metadata']
        else:
            pair_base=pd.concat([base[base.group!='R'],arms[right].assign(group='R')],ignore_index=True)
            m,p,meta=r3.evaluate(split,pair_base,arms[left],old)
            if cache: freeze(cache,dict(metrics=m,predictions=p.to_dict('records'),metadata=meta))
        for source,target in [('active',left),('random',right)]:
            metrics.update({target+k[len(source):]:v for k,v in m.items() if k.startswith(source+'.') and '.sampled.' not in k})
            metadata[target]=meta[source]
        predictions.append(p.assign(arm=p.arm.map({'active':left,'random':right})))
    pred=pd.concat(predictions,ignore_index=True)
    return reports(metrics,pred,arms),pred,metadata

def check_reused(metrics):
    reference=json.loads((R3/'first/surrogate_metrics.json').read_text())
    for arm,source in [('A','active'),('R','random')]:
        for key,value in reference.items():
            if key.startswith(source+'.m2.'):
                assert metrics[arm+key[len(source):]]==value, f'R3 bitwise regression: {key}'

def inputs():
    paths=[SOURCE,R3/'sweep_base.csv',R3/'sweep_active.csv',R3/'first/surrogate_metrics.json',
           ROOT/'data/dclink3/split.json',R3/'pool.json',OUT/'design.json',OUT/'sweep_random.csv',OUT/'sweep_mixed.csv',
           STAGE/'config_prerun.json',STAGE/'design_manifest.json',OUT/'runtime/replay_provenance.json',
           ROOT/'docs/prereg/M5_surrogate_round4_prereg.md']
    paths += [OUT/'mixed'/f'batch_{b}.json' for b in range(1,6)]
    paths += [ROOT/'scripts'/name for name in ('dclink_active4.py','dclink_surrogate4.py','dclink_active3.py','dclink_surrogate3.py','dclink_surrogate2.py','dclink_surrogate.py','dclink_sweep4.py','dclink_sweep3.py','dclink_sweep2.py','dclink_sweep.py')]
    paths += sorted((ROOT/'data/dclink_src/simsw/dclink_simsw').glob('*.py'))
    paths += [ROOT/'data/dclink_src/replay/run_replay.py']
    return paths

def run(split):
    fingerprint=dict(config=CONFIG,input_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs()})
    first=STAGE/'first'
    if first.exists():
        assert json.loads((first/'provenance.json').read_text())==fingerprint
        hashes=json.loads((first/'artifact_hashes.json').read_text())
        for name in NAMES:
            assert sha(first/name)==hashes[name]
            freeze_bytes(OUT/name,(first/name).read_bytes()); freeze_bytes(STAGE/name,(first/name).read_bytes())
        print('首次结果与 provenance 已核对；未重新拟合。'); return
    checkpoint=OUT/'evaluation_checkpoint'; freeze(checkpoint/'provenance.json',fingerprint)
    design=json.loads((OUT/'design.json').read_text()); batches=[json.loads((OUT/'mixed'/f'batch_{b}.json').read_text()) for b in range(1,6)]
    for batch in batches:
        assert batch['sha256']==digest({k:v for k,v in batch.items() if k!='sha256'})
        assert not batch['fingerprint']['smoke']
        freeze(STAGE/'mixed'/f"batch_{batch['fingerprint']['batch']}.json",batch)
    mixed=[p for batch in batches for p in batch['points']]
    assert len(mixed)==110 and len({p['pool_id'] for p in mixed})==110
    random=r3.load_new(OUT/'sweep_random.csv',design); m=r3.load_new(OUT/'sweep_mixed.csv',mixed)
    base=pd.read_csv(R3/'sweep_base.csv'); a=pd.read_csv(R3/'sweep_active.csv'); old=pd.read_csv(SOURCE)
    assert not old.ideal.any() and np.isfinite(old.y).all()
    arms=dict(A=a,R=base[base.group=='R'],M=m,**{arm:random[random.group==arm] for arm in RANDOM})
    assert all(len(frame)==110 for frame in arms.values())
    metrics,pred,metadata=evaluate(split,base,arms,old,checkpoint)
    check_reused(metrics)
    metadata.update(provenance=fingerprint,batches=batches,random_coverage_std_ddof=1,
                    hypotheses='H-A and H-M separately; no combined verdict; R report-only; A previously observed')
    artifacts={'surrogate_metrics.json':encoded(metrics),'surrogate_evidence_metrics.json':encoded(evidence_metrics(metrics)),
               'predictions.csv':pred.to_csv(index=False).encode(),'surrogate_metadata.json':encoded(metadata)}
    pending=STAGE/'first.pending'; pending.mkdir(exist_ok=True)
    for name,body in artifacts.items(): freeze_bytes(pending/name,body)
    freeze(pending/'provenance.json',fingerprint)
    freeze(pending/'artifact_hashes.json',{name:sha(pending/name) for name in NAMES})
    pending.rename(first)
    for name,body in artifacts.items(): freeze_bytes(OUT/name,body); freeze_bytes(STAGE/name,body)
    print(json.dumps(metrics,ensure_ascii=False))

def main():
    split=verify(); argparse.ArgumentParser(description=__doc__).parse_args()
    with (OUT/'.evaluation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); run(split)
if __name__=='__main__': main()
