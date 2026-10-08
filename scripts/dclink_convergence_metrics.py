#!/usr/bin/env python3
"""Parse host-produced convergence results without running simulations."""
import json
import pandas as pd
from dclink_surrogate import ROOT, write_json

def main():
    df=pd.read_csv(ROOT/'data/dclink/convergence.csv')
    df['point']=df.case_id.str.rsplit('_',n=1).str[0]
    if df.duplicated(['point','solver_dt_ns']).any():
        raise ValueError('Duplicate convergence point')
    paired=df.pivot(index='point',columns='solver_dt_ns',values='y')
    if set(paired.columns)!={25,50} or len(paired)!=5 or paired.isna().any().any():
        raise ValueError('Expected five complete 50/25 ns pairs')
    delta=(paired[50]-paired[25]).abs()
    metrics={'points':len(delta),'max_abs_delta_y':float(delta.max()),'mean_abs_delta_y':float(delta.mean())}
    for point in paired.index:
        metrics[point+'.y_50_ns']=float(paired.loc[point,50])
        metrics[point+'.y_25_ns']=float(paired.loc[point,25])
        metrics[point+'.abs_delta_y']=float(delta.loc[point])
    write_json(ROOT/'data/dclink/convergence_metrics.json',metrics)
    print(json.dumps(metrics))

if __name__=='__main__': main()
