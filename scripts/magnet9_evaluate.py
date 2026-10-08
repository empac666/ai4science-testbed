"""Stage 3, separate process: first real holdout reveal after all intervals sealed."""
from magnet9_common import *
from magnet9_design import load_design
from magnet9_stats import score,interval_score,analyze,summary
import argparse


def equal_width(y,mu,sigma,delta,q):
    a=interval_score(y,mu,sigma,q);b=interval_score(y,mu,sigma,q,delta)
    return dict(delta_c=b['c']-a['c'],delta_g=a['g']-b['g'],delta_W=a['W']-b['W'])


def run(smoke=False):
    root=STAGE/('smoke' if smoke else 'first');verify_seal(root,'ACQUIRED');verify_seal(root,'CALIBRATED')
    assert not (root/'EVALUATED').exists(),'First evaluation is immutable'
    df,split=load_design();cal=read_json(root/'calibration.json');assert cal['code_sha256']==code_hashes()
    arms={};diagnostics={};files=[]
    for arm in trajectories(smoke):
        log=root/'evaluation'/f'{arm}_labels.jsonl';reader=LabelReader(split,arm,'evaluate',log,df,smoke)
        arms[arm]={m:{} for m in ('B','E','D')};diagnostics[arm]={}
        q=cal['parameters'][arm]
        with np.load(root/'intervals'/f'{arm}.npz',allow_pickle=False) as p:
            for z in REGIONS:
                assert p[z+'_ids'].tolist()==split[z]
                y=reader.read(split[z])
                for m in ('B','E','D'):
                    arms[arm][m][z]=score(y,p[f'{z}_{m}_center'],p[f'{z}_{m}_lower'],p[f'{z}_{m}_upper'])
                if z in ('XF','XT'):
                    j='F' if z=='XF' else 'T'
                    diagnostics[arm][z]={anchor:equal_width(y,p[z+'_mu'],p[z+'_sigma'],q['delta'][j],q[anchor][j])
                                             for anchor in ('qE','qD')}
        result=dict(arm=arm,scores=arms[arm],equal_width=diagnostics[arm],parameters=q)
        path=root/'arms'/f'{arm}.json';freeze(path,encoded(result));files.extend([path,log])
        print(f'{now()} evaluated {arm}',flush=True)
    metrics=dict(prereg_sha=PREREG_SHA,H=H,smoke=smoke,arms=arms,diagnostics=diagnostics,
                 parameters=cal['parameters'],code_sha256=code_hashes(),calibration_seal=sha(root/'CALIBRATED.json'))
    if not smoke:
        metrics.update(analyze(arms,diagnostics))
        metrics['parameter_summaries']={s:{j:{name:summary([fn(cal['parameters'][f'{s}{k:02d}'],j) for k in range(1,31)])
            for name,fn in [('delta',lambda q,j:q['delta'][j]),('qD-qE',lambda q,j:q['qD'][j]-q['qE'][j])]} for j in ('F','T')} for s in ('U','S')}
        metrics['qD_qE_ratios']={a:{j:q['qD'][j]/q['qE'][j] if q['qE'][j]!=0 else None for j in ('F','T')} for a,q in cal['parameters'].items()}
    else:
        metrics.update(process_valid=False,status='synthetic smoke only; no formal inference; K=1 pair')
    freeze(root/'metrics.json',encoded(metrics));files.append(root/'metrics.json')
    seal(root,'EVALUATED',files,stage='evaluation',smoke=smoke)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');a=ap.parse_args();run(a.smoke)
