"""No-label audit, replaying every sealed believer batch before CAL opens."""
from magnet9_common import *
from magnet9_design import load_design
from magnet9_model import replay,shadow_subsets,verify_prediction_state
from magnet9_arm import sampling,extrema
import argparse


def predictions(folder,name='predictions.csv'):
    return pd.read_csv(folder/name,float_precision='round_trip')


def validate_acquisition_code(recorded):
    current=code_hashes()
    if recorded!=current:
        repair=read_json(STAGE/'implementation_repair.json')
        assert recorded==repair['acquisition_code_sha256']
        assert current==repair['repaired_code_sha256']


def validate_replay_points(rebuilt,sealed):
    """Selections are exact; exp(log(kernel)) round-trip need not preserve score bits."""
    assert len(rebuilt)==len(sealed)
    maximum=0.
    for x,y in zip(rebuilt,sealed):
        assert set(x)==set(y)
        assert all(x[k]==y[k] for k in x if k not in ('sigma','score'))
        for key in ('sigma','score'):
            np.testing.assert_allclose(x[key],y[key],rtol=1e-12,atol=1e-12)
            maximum=max(maximum,abs(x[key]-y[key]))
    return maximum


def audit(smoke=False):
    root=STAGE/('smoke' if smoke else 'first');df,split=load_design()
    results={};hashes={};replayed=0;score_roundtrip_drift={}
    for arm in trajectories(smoke):
        folder=root/'trajectories'/arm;verify_seal(folder,'EVALUATED')
        hashes[arm]=sha(folder/'EVALUATED.json');r=read_json(folder/'result.json')
        validate_acquisition_code(r['code_sha256'])
        assert r['versions']==versions()
        assert r['split_sha256']==digest(split) and r['config_sha256']==sha(STAGE/'config_prerun.json')
        assert r['H']==H and r['gp_seed']==GP_SEED and r['s0_seed']==seed(1,int(arm[1:]))
        assert r['prereg_sha']==PREREG_SHA and r['smoke']==smoke
        ids=list(split['S0'][arm]);authorized=set(ids)
        for b in range(7):
            assert len(ids)==len(set(ids))==100+20*b and set(ids)<=set(split['pool'])
            meta=read_json(folder/f'model_{b}.json')
            assert meta['ids']==ids and meta['columns']==['1','log10_f','log10_Bpk','T_C','T_C^2','shape']
            with np.load(folder/f'model_{b}.npz',allow_pickle=False) as state:
                assert all(np.isfinite(state[k]).all() for k in state.files)
                assert state['X_train'].shape==(len(ids),6) and state['L'].shape==(len(ids),len(ids))
                if b==6: continue
                batch=read_json(folder/f'batch_{b+1}.json')
                candidates=sorted(set(split['pool'])-set(ids))
                assert batch['training_ids']==ids and batch['candidate_sha256']==digest(candidates)
                assert batch['model_sha256']==sha(folder/f'model_{b}.npz')
                points=replay(df,candidates,state)
                drift=validate_replay_points(points,batch['points'])
                if drift:score_roundtrip_drift[f'{arm}/{b+1}']=drift
                chosen=[p['sample_id'] for p in points]
                assert len(chosen)==len(set(chosen))==20 and not set(chosen)&set(ids)
                ids+=chosen;replayed+=1
        assert ids==r['training_ids'] and ids[100:]==r['selected_ids']
        assert r['sampling_counts']==dict(S0=sampling(df,ids[:100]),additions=sampling(df,ids[100:]))
        assert r['training_extrema']==extrema(df,ids) and r['pool_extrema']==extrema(df,split['pool'])
        p=predictions(folder)
        assert set(p.region)==set(('CAL9',)+REGIONS)
        for z in ('CAL9',)+REGIONS: assert p.loc[p.region==z,'sample_id'].tolist()==split[z]
        assert np.isfinite(p[['mu','sigma']]).all().all() and (p.sigma>0).all()
        verify_prediction_state(df,folder,'model_6','predictions.csv')
        for j in ('F','T'):
            core,edge=shadow_subsets(df,ids,split,j);sh=r['shadows'][j]
            assert sh['core_ids']==core and sh['edge_ids']==edge
            assert sh['metadata']['ids']==core
            assert ('T_C^2' in sh['metadata']['columns'])==(j=='F')
            with np.load(folder/f'shadow_{j}.npz',allow_pickle=False) as state:
                assert state['X_train'].shape==(len(core),6) and all(np.isfinite(state[k]).all() for k in state.files)
            sp=predictions(folder,f'shadow_{j}_predictions.csv')
            assert sp.loc[sp.region=='training_edge','sample_id'].tolist()==edge
            assert sp.loc[sp.region=='CAL_edge','sample_id'].tolist()==sh['cal_edge_ids']
            assert set(sh['cal_edge_ids'])==set(split['CAL9'])&set(split['pseudo'][j]['edge'])
            verify_prediction_state(df,folder,f'shadow_{j}',f'shadow_{j}_predictions.csv',True)
        # Reconstruct authorization chronologically. Repeated reads on infrastructure resume are allowed.
        for line in (folder/'labels.jsonl').read_text().splitlines():
            event=json.loads(line.split(' ',1)[1]);assert event['arm']==arm and event['phase']=='acquire'
            assert event['synthetic']==smoke if event['event']=='read' else True
            if event['event']=='authorize':
                assert set(event['ids'])<=set(ids) and set(event['ids'])<=set(split['pool'])
                authorized.update(event['ids'])
            else: assert set(event['ids'])<=authorized and set(event['ids'])<=set(split['pool'])
        results[arm]=r
        print(f'{now()} audit {arm} replayed=6',flush=True)
    record=dict(trajectories=len(results),interval_arms=3*len(results),replayed_batches=replayed,
        source_checks=verify_sources(),seed_audit=seed_audit(),trajectory_seals=hashes,
        code_sha256=code_hashes(),process_acquisition_valid=True,smoke=smoke,
        acquisition_code_sha256=next(iter(results.values()))['code_sha256'],
        score_roundtrip_max_abs_drift=score_roundtrip_drift,
        implementation_repair_sha256=sha(STAGE/'implementation_repair.json') if (STAGE/'implementation_repair.json').exists() else None)
    freeze(root/'acquisition_audit.json',encoded(record))
    seal(root,'ACQUIRED',[root/'acquisition_audit.json']+[root/'trajectories'/a/'EVALUATED.json' for a in results],stage='acquisition')
    return record


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');a=ap.parse_args();audit(a.smoke)
