"""Isolated adapter to the hash-locked numerical model; no legacy evaluation calls."""
from magnet9_common import *
from magnet9_design import subsets,describe
import copy
import importlib.util
import io
from types import SimpleNamespace


def linear_columns(temperatures,shadow=False):
    columns=['1','log10_f','log10_Bpk','T_C','T_C^2','shape']
    if shadow and len(set(temperatures))<3: columns.remove('T_C^2')
    return columns


def adapter(temperatures,shadow=False):
    spec=importlib.util.spec_from_file_location('_r9_isolated_model',ROOT/'scripts/magnet6_model.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.CONFIG=copy.deepcopy(module.CONFIG)
    module.CONFIG['model']['gp_random_state']=GP_SEED
    module.CONFIG['features']['linear_mean_features']=linear_columns(temperatures,shadow)
    # Neither legacy label readers nor statistical helpers are exposed by this adapter.
    return SimpleNamespace(FEATURES=module.FEATURES,fit=module.fit_m2,predict=module.predict,
                           believer=module.believer,make_kernel=module.make_kernel,linear=module.linear,
                           columns=module.CONFIG['features']['linear_mean_features'])


def fit(df,ids,y,shadow=False,allowed=None):
    assert len(ids)==len(y) and len(ids)==len(set(ids))
    if allowed is not None: assert set(ids)<=set(allowed), 'Shadow edge labels forbidden in fit/scaler'
    train=df.loc[ids].copy();train['y']=y
    module=adapter(train.T_C,shadow)
    model=module.fit(train)
    matrix=module.linear(train)
    condition=float(np.linalg.cond(matrix))
    metadata=dict(ids=ids,columns=module.columns,rank=int(np.linalg.matrix_rank(matrix)),
        condition_number=condition if np.isfinite(condition) else None,condition_infinite=not np.isfinite(condition),
        temperatures=sorted(map(int,train.T_C.unique())),gp_seed=GP_SEED)
    return module,model,metadata


def save_model(path,model):
    scaler,coef,gp=model;stream=io.BytesIO()
    np.savez(stream,scaler_mean=scaler.mean_,scaler_scale=scaler.scale_,coef=coef,
        kernel_theta=gp.kernel_.theta,X_train=gp.X_train_,L=gp.L_,alpha=gp.alpha_,
        y_mean=gp._y_train_mean,y_std=gp._y_train_std)
    freeze(path,stream.getvalue())


def predict(module,model,df,ids):
    parts=[module.predict(model,df.loc[ids[i:i+1024]]) for i in range(0,len(ids),1024)]
    mu=np.concatenate([x[0] for x in parts]);sigma=np.concatenate([x[1] for x in parts])
    assert np.isfinite(mu).all() and np.isfinite(sigma).all() and (sigma>0).all()
    return mu,sigma


def shadow_subsets(df,train,split,j):
    assert set(train)<=set(split['pool']) and set(train)<=set(split['S'])
    core,edge=subsets(df,train,j)
    assert len(core)>=30 and df.loc[core,'fset'].nunique()>=2 and len(edge)>=10
    assert sorted(map(int,df.loc[core,'T_C'].unique()))==([25,50,70] if j=='F' else [25,50])
    return core,edge


def delta(y,mu,ids,edge,cal,holdouts):
    assert set(ids)<=set(edge) and not set(ids)&(set(cal)|set(holdouts))
    y,mu=np.asarray(y),np.asarray(mu)
    assert y.shape==mu.shape==(len(ids),) and np.isfinite(y-mu).all()
    return float(np.median(y-mu))


def replay(df,candidates,state,count=20):
    module=adapter([25,50,70])
    x=df.loc[candidates,module.FEATURES].to_numpy()
    z=(x-state['scaler_mean'])/state['scaler_scale']
    gp=SimpleNamespace(X_train_=state['X_train'],L_=state['L'],
        kernel_=module.make_kernel().clone_with_theta(state['kernel_theta']),
        _y_train_std=state['y_std'],alpha=1e-10)
    return module.believer(gp,z,count,candidates)[1]


def verify_prediction_state(df,folder,model_name,prediction_name,shadow=False):
    """Rebuild predictive moments from saved linear/scaler/GP state without labels."""
    from scipy.linalg import solve_triangular
    meta=read_json(folder/f'{model_name}.json')
    module=adapter(meta['temperatures'],shadow)
    p=pd.read_csv(folder/prediction_name,float_precision='round_trip')
    with np.load(folder/f'{model_name}.npz',allow_pickle=False) as state:
        x=df.loc[meta['ids'],module.FEATURES].to_numpy()
        np.testing.assert_array_equal((x-state['scaler_mean'])/state['scaler_scale'],state['X_train'])
        matrix=module.linear(df.loc[meta['ids']])
        assert meta['rank']==int(np.linalg.matrix_rank(matrix))
        cond=float(np.linalg.cond(matrix))
        assert meta['condition_number']==(cond if np.isfinite(cond) else None)
        kernel=module.make_kernel().clone_with_theta(state['kernel_theta'])
        for start in range(0,len(p),1024):
            batch=p.iloc[start:start+1024];rows=df.loc[batch.sample_id]
            z=(rows[module.FEATURES].to_numpy()-state['scaler_mean'])/state['scaler_scale']
            cross=kernel(z,state['X_train'])
            mu=module.linear(rows)@state['coef']+(cross@state['alpha'])*state['y_std']+state['y_mean']
            v=solve_triangular(state['L'],cross.T,lower=True,check_finite=False)
            var=kernel.diag(z)-np.einsum('ij,ji->i',v.T,v)
            sd=np.maximum(np.sqrt(np.maximum(var,0)*state['y_std']**2),2.220446049250313e-16)
            np.testing.assert_allclose(mu,batch.mu,rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(sd,batch.sigma,rtol=1e-12,atol=1e-12)
