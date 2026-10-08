#!/usr/bin/env python3
"""Temperature-specific sinusoidal Steinmetz fits and a fixed-rule iGSE baseline.
SI units: Hz, T, W/m^3. Samples are one uniform period, endpoint excluded.
Waveforms are processed in bounded chunks; no raw measurements enter git.
"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import beta as beta_function

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261003
CHUNK = 1024
WAVES = ('sine','triangle','trapezoid')

def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def ki_from_steinmetz(k, alpha, beta):
    if k <= 0 or alpha <= 0: raise ValueError('k and alpha must be positive')
    integral = 2*beta_function(.5,(alpha+1)/2)  # integral_0^{2pi} |cos theta|^alpha
    return k/((2*np.pi)**(alpha-1)*integral*2**(beta-alpha))

def igse(b, frequency, k, alpha, beta):
    """Exact integral on the periodic piecewise-linear interpolant of uniform B."""
    b=np.asarray(b,dtype=float)
    delta=np.ptp(b,axis=-1)
    slopes=np.abs(np.roll(b,-1,axis=-1)-b)*b.shape[-1]*np.asarray(frequency)[...,None]
    return ki_from_steinmetz(k,alpha,beta)*np.mean(slopes**alpha,axis=-1)*delta**(beta-alpha)

def classify(b):
    """Sine: fundamental residual <=5%; else plateau >=5% -> trapezoid.
    Plateau = |periodic difference| < 10% of the 90th percentile slope.
    Remaining nonsines are triangles; rules do not depend on measured loss.
    """
    b=np.atleast_2d(np.asarray(b,dtype=float))
    centered=b-b.mean(axis=1,keepdims=True)
    theta=2*np.pi*np.arange(b.shape[1])/b.shape[1]
    model=(2/b.shape[1])*((centered@np.cos(theta))[:,None]*np.cos(theta)+
                               (centered@np.sin(theta))[:,None]*np.sin(theta))
    residual=np.sqrt(np.mean((centered-model)**2,axis=1)/np.mean(centered**2,axis=1))
    slope=np.abs(np.roll(b,-1,axis=1)-b)
    plateau=np.mean(slope < .1*np.quantile(slope,.9,axis=1)[:,None],axis=1)
    labels=np.where(residual<=.05,'sine',np.where(plateau>=.05,'trapezoid','triangle'))
    return labels,residual,plateau

def error_stats(error):
    error=np.asarray(error,dtype=float)
    if not len(error) or not np.all(np.isfinite(error)): raise ValueError('Empty or nonfinite errors')
    absolute=np.abs(error)
    return dict(n=int(len(error)),abs_mean=float(absolute.mean()),abs_median=float(np.median(absolute)),
                abs_p95=float(np.quantile(absolute,.95)),within_10=float(np.mean(absolute<=.1)),
                within_20=float(np.mean(absolute<=.2)),signed_median=float(np.median(error)))

def grouped_stats(frame):
    result={}
    for wave,g in frame.groupby('waveform',sort=True):
        for key,value in error_stats(g.relative_error).items(): result[f'{wave}.all.{key}']=value
        for temp,tg in g.groupby('temperature_C',sort=True):
            for key,value in error_stats(tg.relative_error).items(): result[f'{wave}.T{temp:g}.{key}']=value
    return result

def fit_parameters(frequency, amplitude, loss):
    x=np.column_stack((np.ones(len(loss)),np.log(frequency),np.log(amplitude)))
    coeff,_,rank,_=np.linalg.lstsq(x,np.log(loss),rcond=None)
    if rank != 3: raise ValueError('Rank-deficient Steinmetz fit')
    k,alpha,beta=float(np.exp(coeff[0])),float(coeff[1]),float(coeff[2])
    ki_from_steinmetz(k,alpha,beta)
    return dict(k=k,alpha=alpha,beta=beta,n=int(len(loss)),log_rmse=float(np.sqrt(np.mean((x@coeff-np.log(loss))**2))))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',type=Path,default=ROOT/'data/magnet'); args=ap.parse_args()
    out=args.data; staging=ROOT/'lab/cases/magnet'; staging.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((out/'MANIFEST.json').read_text())
    entry=manifest['files'][0]; path=out/entry['path']
    if path.stat().st_size!=entry['size_bytes']: raise ValueError('N87 ZIP size mismatch; rerun fetch')
    h=hashlib.sha256()
    with path.open('rb') as src:
        for block in iter(lambda:src.read(1024*1024),b''): h.update(block)
    if h.hexdigest()!=entry['sha256']: raise ValueError('N87 SHA256 mismatch; rerun fetch')
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        expected={'B_waveform[T].csv','H_waveform[Am-1].csv','Frequency[Hz].csv','Temperature[C].csv','Volumetric_losses[Wm-3].csv'}
        if set(names)!=expected: raise ValueError('ZIP schema changed: inspect for provided waveform labels first')
        def scalar(name):
            with archive.open(name) as src: return pd.read_csv(src,header=None).to_numpy(dtype=float).ravel()
        f=scalar('Frequency[Hz].csv'); temp=scalar('Temperature[C].csv'); loss=scalar('Volumetric_losses[Wm-3].csv')
        n=len(f)
        if len(temp)!=n or len(loss)!=n or np.any(f<=0) or np.any(loss<=0): raise ValueError('Invalid scalar data')
        frame=pd.DataFrame(dict(sample_id=np.arange(n),frequency_Hz=f,temperature_C=temp,measured_W_m3=loss))
        all_labels=[]; all_res=[]; all_plateau=[]; amplitudes=[]; offset=0
        cache=out/'N87/B.npy'; mapped=None
        with archive.open('B_waveform[T].csv') as src:
            for chunk in pd.read_csv(src,header=None,chunksize=CHUNK):
                b=chunk.to_numpy(dtype=float)
                if not np.all(np.isfinite(b)): raise ValueError('Nonfinite B waveform')
                if mapped is None:
                    points=b.shape[1]; mapped=np.lib.format.open_memmap(cache,mode='w+',dtype='float64',shape=(n,points))
                if offset+len(b)>n: raise ValueError('Too many B rows')
                mapped[offset:offset+len(b)]=b
                labels,res,plateau=classify(b)
                all_labels.extend(labels);all_res.extend(res);all_plateau.extend(plateau);amplitudes.extend(np.ptp(b,axis=1)/2)
                offset+=len(b)
        if offset!=n: raise ValueError('B/scalar row count mismatch')
        mapped.flush()
        h_rows=0;h_widths=set()
        with archive.open('H_waveform[Am-1].csv') as src:
            for line in src:
                h_rows+=1;h_widths.add(line.count(b',')+1)
        if h_rows!=n or h_widths!={points}: raise ValueError('H/B shape mismatch')
    frame['waveform']=all_labels;frame['sine_residual']=all_res;frame['plateau_fraction']=all_plateau;frame['amplitude_T']=amplitudes
    if np.any(frame.amplitude_T<=0): raise ValueError('Nonpositive amplitude')
    train=np.zeros(n,dtype=bool);params={};rng=np.random.default_rng(SEED)
    sine_ids=np.flatnonzero(frame.waveform.to_numpy()=='sine')
    selected=rng.permutation(sine_ids)[:len(sine_ids)//2]
    train[selected]=True
    for temperature in sorted(np.unique(temp)):
        selected=np.flatnonzero((temp==temperature)&train)
        if len(selected)<3: raise ValueError('Insufficient sinusoids for temperature '+str(temperature))
        params[f'{temperature:g}']=fit_parameters(f[selected],frame.amplitude_T.to_numpy()[selected],loss[selected])
    prediction=np.empty(n)
    for start in range(0,n,CHUNK):
        stop=min(start+CHUNK,n); b=np.asarray(mapped[start:stop])
        for temperature in np.unique(temp[start:stop]):
            mask=temp[start:stop]==temperature; p=params[f'{temperature:g}']
            prediction[start:stop][mask]=igse(b[mask],f[start:stop][mask],p['k'],p['alpha'],p['beta'])
    frame['split']=np.where(train,'train','eval');frame['predicted_W_m3']=prediction
    frame['relative_error']=(prediction-loss)/loss
    evaluation=frame[~train]
    metrics=grouped_stats(evaluation)
    metrics.update({'data.n':n,'data.points':points,'split.train_n':int(train.sum()),'split.eval_n':int((~train).sum()),'split.seed':SEED})
    for wave in WAVES: metrics[f'data.{wave}.n']=int((frame.waveform==wave).sum())
    for temperature,p in params.items():
        for key,value in p.items(): metrics[f'fit.T{temperature}.{key}']=value
    write_json(out/'igse_metrics.json',metrics)
    nested={}
    for key,value in metrics.items():
        current=nested;parts=key.split('.')
        for part in parts[:-1]: current=current.setdefault(part,{})
        current[parts[-1]]=value
    write_json(out/'igse_evidence_metrics.json',nested)
    frame.to_csv(out/'igse_predictions.csv',index=False,float_format='%.12g')
    summary=dict(n=n,points=points,h_rows=h_rows,h_points=points,temperatures_C=sorted(np.unique(temp).tolist()),
        ranges={key:[float(frame[key].min()),float(frame[key].max())] for key in ('frequency_Hz','temperature_C','amplitude_T','measured_W_m3')},
        waveform_counts=frame.waveform.value_counts().to_dict(),members=names,parameters=params,seed=SEED,
        train_ids_sha256=hashlib.sha256(np.flatnonzero(train).astype('<i8').tobytes()).hexdigest(),
        data_sha256=entry['sha256'],classification='fixed B-only rule; no original labels',
        units=dict(frequency='Hz',amplitude='T = peak-to-peak / 2',loss='W/m^3'),
        derivative='periodic forward differences, endpoint excluded; exact PWL integral; no smoothing')
    write_json(out/'igse_metadata.json',summary)
    # Fixed random visual audit, plus closest samples to both decision boundaries.
    audit=[]
    for wave in WAVES:
        ids=np.flatnonzero(frame.waveform.to_numpy()==wave)
        chosen=np.random.default_rng(SEED+1).choice(ids,size=min(12,len(ids)),replace=False)
        for i in chosen: audit.append(int(i))
    boundary=np.argsort(np.abs(frame.sine_residual.to_numpy()-.05))[:6].tolist()
    nonsine=np.flatnonzero(frame.waveform.to_numpy()!='sine')
    boundary+=nonsine[np.argsort(np.abs(frame.plateau_fraction.to_numpy()[nonsine]-.05))[:6]].tolist()
    frame.iloc[audit+boundary][['sample_id','waveform','sine_residual','plateau_fraction']].to_csv(out/'classification_audit.csv',index=False)
    np.savez(out/'classification_audit.npz',ids=audit+boundary,b=np.asarray(mapped[audit+boundary]),labels=frame.waveform.to_numpy(dtype='U16')[audit+boundary])
    for name in ('igse_metrics.json','igse_metadata.json','MANIFEST.json','classification_audit.csv'):
        shutil.copy2(out/name,staging/name)
    pred=out/'igse_predictions.csv'
    if pred.stat().st_size<=5_000_000: shutil.copy2(pred,staging/pred.name)
    else:
        (staging/pred.name).unlink(missing_ok=True)
        write_json(staging/'predictions_summary.json',dict(size_bytes=pred.stat().st_size,
            sha256=hashlib.sha256(pred.read_bytes()).hexdigest(),rows=n,note='CSV exceeds 5 MB; raw predictions remain in data/magnet'))
    print(json.dumps({'n':n,'points':points,'train_n':int(train.sum()),'eval_n':len(evaluation),'waveform_counts':summary['waveform_counts'],'parameters':params},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
