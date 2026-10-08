"""Stage 1: local acquisition, seven main fits and two core-only shadow fits."""
from magnet9_common import *
from magnet9_design import load_design,describe
from magnet9_model import fit,save_model,predict,shadow_subsets,delta
from collections import Counter
import argparse
import time


def sampling(df,ids):
    rows=df.loc[ids]
    return dict(n=len(ids),**{key:dict(Counter(map(lambda v:str(int(v)),rows[key]))) for key in ('fset','T_C','v_bin')})


def extrema(df,ids):
    return {key:dict(min=float(df.loc[ids,key].min()),max=float(df.loc[ids,key].max()))
            for key in ('frequency_Hz','fset','T_C','amplitude_T','v')}


def frame_prediction(module,model,df,split,names):
    tables=[]
    for name,ids in names:
        mu,sigma=predict(module,model,df,ids)
        tables.append(pd.DataFrame(dict(region=name,sample_id=ids,mu=mu,sigma=sigma)))
    return pd.concat(tables,ignore_index=True)


def run(arm,smoke=False):
    assert arm in trajectories(smoke)
    df,split=load_design();root=STAGE/('smoke' if smoke else 'first')
    folder=root/'trajectories'/arm;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'EVALUATED').exists():
        verify_seal(folder,'EVALUATED');return
    started=time.monotonic();log=folder/'labels.jsonl'
    reader=LabelReader(split,arm,'acquire',log,df,smoke)
    manifest=dict(arm=arm,smoke=smoke,prereg_sha=PREREG_SHA,H=H,gp_seed=GP_SEED,
        family_seed=seed(0,0),s0_seed=seed(1,int(arm[1:])),split_sha256=digest(split),
        config_sha256=sha(STAGE/'config_prerun.json'),code_sha256=code_hashes(),versions=versions())
    freeze(folder/'manifest.json',encoded(manifest))
    selected=[];s0=split['S0'][arm];checkpoints=[];files=[folder/'manifest.json']
    for b in range(7):
        ids=s0+selected
        y=reader.read(ids)
        module,model,meta=fit(df,ids,y)
        save_model(folder/f'model_{b}.npz',model);files.append(folder/f'model_{b}.npz')
        freeze(folder/f'model_{b}.json',encoded(meta));files.append(folder/f'model_{b}.json')
        checkpoints.append(dict(b=b,n=len(ids),metadata=meta,extrema=extrema(df,ids)))
        print(f'{now()} {arm} main b={b} n={len(ids)} sealed',flush=True)
        if b==6: break
        candidates=sorted(set(split['pool'])-set(ids))
        z=model[0].transform(df.loc[candidates,module.FEATURES].to_numpy())
        _,points=module.believer(model,z,20,candidates)
        chosen=[p['sample_id'] for p in points]
        record=dict(arm=arm,b=b+1,training_ids=ids,candidate_sha256=digest(candidates),points=points,
                    model_sha256=sha(folder/f'model_{b}.npz'))
        freeze(folder/f'batch_{b+1}.json',encoded(record));files.append(folder/f'batch_{b+1}.json')
        # This durable record must precede the reader's authorization/reveal.
        reader.authorize(chosen);selected.extend(chosen)
    pred=frame_prediction(module,model,df,split,[(z,split[z]) for z in ('CAL9',)+REGIONS])
    freeze(folder/'predictions.csv',pred.to_csv(index=False,float_format='%.17g').encode());files.append(folder/'predictions.csv')
    shadows={};holdouts=set().union(*(set(split[z]) for z in REGIONS))
    for j in ('F','T'):
        core,edge=shadow_subsets(df,ids,split,j)
        cy=reader.read(core)
        sm,model_j,meta=fit(df,core,cy,shadow=True,allowed=core)
        save_model(folder/f'shadow_{j}.npz',model_j);files.append(folder/f'shadow_{j}.npz')
        freeze(folder/f'shadow_{j}.json',encoded(meta));files.append(folder/f'shadow_{j}.json')
        mu,_=predict(sm,model_j,df,edge)
        dj=delta(reader.read(edge),mu,edge,edge,split['CAL9'],holdouts)
        caledge=[i for i in split['CAL9'] if i in set(split['pseudo'][j]['edge'])]
        p=frame_prediction(sm,model_j,df,split,[('CAL_edge',caledge),('training_edge',edge)])
        freeze(folder/f'shadow_{j}_predictions.csv',p.to_csv(index=False,float_format='%.17g').encode())
        files.append(folder/f'shadow_{j}_predictions.csv')
        shadows[j]=dict(delta=dj,core=describe(df,core),edge=describe(df,edge),cal_edge=describe(df,caledge),
                        core_ids=core,edge_ids=edge,cal_edge_ids=caledge,metadata=meta)
    result=dict(**manifest,training_ids=ids,selected_ids=selected,checkpoints=checkpoints,shadows=shadows,
        sampling_counts=dict(S0=sampling(df,s0),additions=sampling(df,selected)),
        pool_extrema=extrema(df,split['pool']),training_extrema=extrema(df,ids))
    freeze(folder/'result.json',encoded(result));files.extend([folder/'result.json',log])
    seal(folder,'EVALUATED',files,stage='acquisition',arm=arm,synthetic=smoke)
    print(f'{now()} {arm} ACQUIRED seconds={time.monotonic()-started:.2f}',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--arm',required=True);ap.add_argument('--smoke',action='store_true')
    a=ap.parse_args();run(a.arm,a.smoke)
