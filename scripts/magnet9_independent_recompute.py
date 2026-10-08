"""Independent post-seal recomputation: no imports from R9 stats/evaluate/calibrate."""
from magnet9_common import *
from magnet9_design import load_design
from fractions import Fraction
from bisect import bisect_right
import argparse


def exact_count(values):
    """Independent subset-sum oracle: flipped subset sum <= K*epsilon/2."""
    fractions=[Fraction.from_float(float(x)) for x in values]
    tol=Fraction.from_float(1e-12)*len(values)/2
    scale=max([x.denominator for x in fractions]+[tol.denominator])
    vals=[int(x*scale) for x in fractions];limit=int(tol*scale)
    def sums(v):
        a=[0]
        for x in v: a += [s+x for s in a]
        return a
    mid=len(vals)//2;a=sums(vals[:mid]);b=sorted(sums(vals[mid:]))
    return sum(bisect_right(b,limit-x) for x in a)


def independent_metrics(y,center,lo,hi):
    n=len(y);count=int(np.count_nonzero((y>=lo)&(y<=hi)));err=center-y
    return dict(n=n,coverage=count,c=count/n,g=max(0.,.90-count/n),w=float((hi-lo).mean()),
        W=float((hi-lo+20*np.maximum(lo-y,0)+20*np.maximum(y-hi,0)).mean()),
        MAE=float(np.abs(err).mean()),bias=float(err.mean()),median_relative_error=float(np.median(np.abs(np.power(10.,err)-1))))


def independent_gate(rows,base,z):
    n=rows[0][z]['n'];ng=rows[0]['G9']['n'];K=len(rows)
    cc=[r['G9']['coverage']>=(4*ng+4)//5 for r in rows]
    f=[a and r[z]['coverage']>=(4*n+4)//5 for a,r in zip(cc,rows)]
    v=[a and r[z]['w']<=3*r['G9']['w'] for a,r in zip(f,rows)]
    h=[r[z]['coverage']>=(9*n+9)//10 for r in rows]
    w=[r[z]['w']<=2*b[z]['w'] for r,b in zip(rows,base)]
    wm=bool(np.mean([r[z]['w'] for r in rows])<=1.5*np.mean([r[z]['w'] for r in base]))
    total=sum(r[z]['coverage'] for r in rows)
    flags=dict(V80=sum(v)>=26,HONEST90=sum(h)>=26,MEAN90=total>=(9*K*n+9)//10,FLOOR80=all(f))
    flags.update(A=all(flags.values()),WIDTH=all(w) and wm)
    flags['J']=flags['A'] and flags['WIDTH']
    return dict(**flags,validity_pass_counts=dict(C1=sum(cc),V80=sum(v),HONEST90=sum(h),FLOOR80=sum(f),WIDTH_pairs=sum(w)),
        per_arm=dict(C1=cc,V80=v,HONEST90=h,FLOOR80=f,WIDTH=w),width_mean_pass=wm,
        width_pair_veto_k=[i+1 for i,x in enumerate(w) if not x],coverage_total=total,mean90_required=(9*K*n+9)//10)


def run(smoke=False):
    root=STAGE/('smoke' if smoke else 'first')
    for name in ('ACQUIRED','CALIBRATED','EVALUATED'):verify_seal(root,name)
    df,split=load_design();m=read_json(root/'metrics.json');cal=read_json(root/'calibration.json')['parameters']
    rebuilt={};diag={};checks=0
    for arm in trajectories(smoke):
        folder=root/'trajectories'/arm;verify_seal(folder,'EVALUATED')
        reader=LabelReader(split,arm,'evaluate',root/'recompute'/f'{arm}_labels.jsonl',df,smoke)
        rebuilt[arm]={method:{} for method in ('B','E','D')};diag[arm]={}
        q=cal[arm]
        # Independently reopen only this trajectory's authorized train and CAL labels.
        r=read_json(folder/'result.json')
        train_reader=LabelReader(split,arm,'acquire',root/'recompute'/f'{arm}_train_labels.jsonl',df,smoke)
        train_reader.authorize(r['selected_ids'])
        cal_reader=LabelReader(split,arm,'calibrate',root/'recompute'/f'{arm}_cal_labels.jsonl',df,smoke)
        cy=cal_reader.read(split['CAL9']);cy=pd.Series(cy,index=split['CAL9'])
        pp=pd.read_csv(folder/'predictions.csv',float_precision='round_trip');pp=pp[pp.region=='CAL9']
        def order_stat(a):
            rank=(9*(len(a)+1)+9)//10
            assert rank<=len(a) and np.isfinite(a).all()
            return float(sorted(a)[rank-1])
        q0=order_stat(np.abs(cy.loc[pp.sample_id].to_numpy()-pp.mu.to_numpy())/pp.sigma.to_numpy())
        assert q0==q['q0']
        for j in ('F','T'):
            pp=pd.read_csv(folder/f'shadow_{j}_predictions.csv',float_precision='round_trip')
            edge=pp[pp.region=='training_edge'];yy=train_reader.read(edge.sample_id.tolist())
            dj=float(np.median(yy-edge.mu.to_numpy()))
            assert dj==q['delta'][j]==r['shadows'][j]['delta']
            edge=pp[pp.region=='CAL_edge'];yy=cy.loc[edge.sample_id].to_numpy()
            assert max(q0,order_stat(np.abs(yy-edge.mu.to_numpy())/edge.sigma.to_numpy()))==q['qE'][j]
            assert max(q0,order_stat(np.abs(yy-edge.mu.to_numpy()-dj)/edge.sigma.to_numpy()))==q['qD'][j]
        with np.load(root/'intervals'/f'{arm}.npz',allow_pickle=False) as p:
            for z in REGIONS:
                y=reader.read(split[z]);mu=p[z+'_mu'];sd=p[z+'_sigma']
                for method in ('B','E','D'):
                    jj=('F','T') if z=='XFT' else (('F',) if z=='XF' else ('T',))
                    scale=q['q0'] if method=='B' or z=='G9' else max(q['q'+method][j] for j in jj)
                    shift=sum(q['delta'][j] for j in jj) if method=='D' and z!='G9' else 0.
                    center=mu+shift;lo=center-scale*sd;hi=center+scale*sd
                    for suffix,values in [('center',center),('lower',lo),('upper',hi)]:
                        np.testing.assert_array_equal(values,p[f'{z}_{method}_{suffix}'])
                    rebuilt[arm][method][z]=independent_metrics(y,center,lo,hi);checks+=1
                if z in ('XF','XT'):
                    j='F' if z=='XF' else 'T';diag[arm][z]={}
                    for anchor in ('qE','qD'):
                        width=q[anchor][j]*sd;center=mu+q['delta'][j]
                        a=independent_metrics(y,mu,mu-width,mu+width)
                        b=independent_metrics(y,center,center-width,center+width)
                        diag[arm][z][anchor]=dict(delta_c=b['c']-a['c'],delta_g=a['g']-b['g'],delta_W=a['W']-b['W'])
        assert rebuilt[arm]==m['arms'][arm] and diag[arm]==m['diagnostics'][arm]
        print(f'{now()} independent metrics {arm} passed',flush=True)
    record=dict(smoke=smoke,per_region_metrics_checked=checks,all_per_arm_metrics_equal=True,all_diagnostics_equal=True,
        p_numerators={},gate_checks=0,conclusions_equal=True,process_valid=not smoke,
        evaluation_seal=sha(root/'EVALUATED.json'),code_sha256=code_hashes())
    if not smoke:
        differences={}
        for h,z,key in [('H1','XF','g'),('H2','XT','g'),('H3','XF','W'),('H4','XT','W')]:
            a=[(1.10 if key=='W' else 1.)*rebuilt[f'U{k:02d}']['B'][z][key]-rebuilt[f'U{k:02d}']['D'][z][key] for k in range(1,31)]
            assert a==m['hypotheses'][h]['differences']['values']
            numerator=exact_count(a);assert numerator==m['hypotheses'][h]['numerator']
            assert m['hypotheses'][h]['denominator']==2**30
            record['p_numerators'][h]=numerator;differences[h]=a
        statuses={}
        for first,second in [('H1','H3'),('H2','H4')]:
            statuses[first]='rejected' if record['p_numerators'][first]/2**30<.025 else 'not_rejected'
            statuses[second]=('rejected' if record['p_numerators'][second]/2**30<.025 else 'not_rejected') if statuses[first]=='rejected' else 'not_tested'
        assert statuses=={h:v['status'] for h,v in m['hypotheses'].items()}
        gg={}
        for s in ('U','S'):
            gg[s]={}
            for method in ('B','E','D'):
                gg[s][method]={}
                for z in ('XF','XT'):
                    r=[rebuilt[f'{s}{k:02d}'][method] for k in range(1,31)]
                    b=[rebuilt[f'{s}{k:02d}']['B'] for k in range(1,31)]
                    g=independent_gate(r,b,z);gg[s][method][z]=g
                    for key,value in g.items():assert value==m['gates'][s][method][z][key],(s,method,z,key)
                    record['gate_checks']+=1
        for z,h1,h2 in [('XF','H1','H3'),('XT','H2','H4')]:
            g=gg['U']['D'][z];c=m['conclusions'][z]
            assert all(c[key]==g[key] for key in ('A','WIDTH','J'))
            assert c['coverage_status']==statuses[h1] and c['Winkler_status']==statuses[h2]
            success=g['J'] and statuses[h1]==statuses[h2]=='rejected'
            assert c['SUCCESS']==success
            if not g['A']:text='未达到完整经验覆盖标准'
            elif not g['WIDTH']:text='达到覆盖标准，但区间宽度代价超限'
            elif statuses[h1]!='rejected':text='达到经验门槛，但未确认相对新基线的欠覆盖改进'
            elif statuses[h2]!='rejected':text='覆盖欠缺改进且达到门槛，10%综合代价非劣未确认'
            else:text='本固定面板上完整D策略的区域成功（条件性推断）'
            dual=g['A'] and gg['U']['B'][z]['A'] and statuses[h1]!='rejected'
            if dual:
                text='基线与候选方法均达到预注册经验覆盖标准，相对欠覆盖改进未确认。'+('达到覆盖标准，但区间宽度代价超限。' if not g['WIDTH'] else '')
                if all(rebuilt[f'U{k:02d}'][method][z]['g']==0 for k in range(1,31) for method in ('B','D')):
                    text+='本评估面板无额外相对欠覆盖需要缩减。'
            assert c['text']==text and c['dual_A']==dual
        assert m['both_success']==all(c['SUCCESS'] for c in m['conclusions'].values())
        assert len(rebuilt)==60 and checks==720 and m['process_valid']
    freeze(root/'independent_recompute.json',encoded(record))
    files=[root/'independent_recompute.json']+sorted((root/'recompute').glob('*.jsonl'))
    seal(root,'RECOMPUTED',files,stage='independent_recompute')
    print('Independent integer numerators, metrics, gates and conclusions verified.',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');a=ap.parse_args();run(a.smoke)
