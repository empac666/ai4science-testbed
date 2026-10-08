"""Stage 2: per-trajectory CAL reads only after the complete acquisition seal."""
from magnet9_common import *
from magnet9_design import load_design
from magnet9_audit import predictions,validate_acquisition_code
from magnet9_stats import q90
import argparse


def parameters(q,method,z):
    if method=='B' or z=='G9': return q['q0'],0.
    js=('F','T') if z=='XFT' else (('F',) if z=='XF' else ('T',))
    return max(q['q'+method][j] for j in js),sum(q['delta'][j] for j in js) if method=='D' else 0.


def run(smoke=False):
    root=STAGE/('smoke' if smoke else 'first');verify_seal(root,'ACQUIRED')
    df,split=load_design();calibration={};files=[]
    for arm in trajectories(smoke):
        source=root/'trajectories'/arm;verify_seal(source,'EVALUATED')
        validate_acquisition_code(read_json(source/'result.json')['code_sha256'])
        log=root/'calibration'/f'{arm}_labels.jsonl'
        reader=LabelReader(split,arm,'calibrate',log,df,smoke)
        y=reader.read(split['CAL9']);series=pd.Series(y,index=split['CAL9'])
        pred=predictions(source);p=pred[pred.region=='CAL9']
        q0=q90(np.abs(y-p.mu.to_numpy())/p.sigma.to_numpy())
        result=read_json(source/'result.json');q=dict(q0=q0,qE={},qD={},delta={})
        for j in ('F','T'):
            p=predictions(source,f'shadow_{j}_predictions.csv');p=p[p.region=='CAL_edge']
            assert p.sample_id.tolist()==result['shadows'][j]['cal_edge_ids']
            dj=result['shadows'][j]['delta'];qy=series.loc[p.sample_id].to_numpy()
            q['delta'][j]=dj
            q['qE'][j]=max(q0,q90(np.abs(qy-p.mu.to_numpy())/p.sigma.to_numpy()))
            q['qD'][j]=max(q0,q90(np.abs(qy-p.mu.to_numpy()-dj)/p.sigma.to_numpy()))
        calibration[arm]=q
        # Seal actual interval endpoints, centers and both diagnostic anchors before evaluation.
        arrays={}
        for z in REGIONS:
            p=pred[pred.region==z];mu=p.mu.to_numpy();sd=p.sigma.to_numpy()
            arrays[z+'_ids']=p.sample_id.to_numpy();arrays[z+'_mu']=mu;arrays[z+'_sigma']=sd
            for m in ('B','E','D'):
                scale,shift=parameters(q,m,z);center=mu+shift
                arrays[f'{z}_{m}_center']=center
                arrays[f'{z}_{m}_lower']=center-scale*sd
                arrays[f'{z}_{m}_upper']=center+scale*sd
        import io
        stream=io.BytesIO();np.savez(stream,**arrays)
        path=root/'intervals'/f'{arm}.npz';freeze(path,stream.getvalue());files.extend([path,log])
        print(f'{now()} calibration {arm} sealed',flush=True)
    freeze(root/'calibration.json',encoded(dict(parameters=calibration,code_sha256=code_hashes(),
        acquisition_seal=sha(root/'ACQUIRED.json'),smoke=smoke)))
    files.append(root/'calibration.json');seal(root,'CALIBRATED',files,stage='calibration')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');a=ap.parse_args();run(a.smoke)
