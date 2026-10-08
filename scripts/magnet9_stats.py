"""Pure R9 statistics: binary-rational exact sign flip and frozen gate mapping."""
from bisect import bisect_left
import math
import numpy as np

EPS = 1e-12


def ceil_div(a,b):
    assert isinstance(a,int) and a >= 0 and isinstance(b,int) and b > 0
    return (a+b-1)//b


def q90(scores):
    a = np.asarray(scores,dtype=float)
    assert a.ndim == 1 and len(a)>0 and np.isfinite(a).all() and (a>=0).all()
    rank = ceil_div(9*(len(a)+1),10)
    assert rank <= len(a), 'Q90 rank exceeds finite calibration size'
    return float(np.partition(a,rank-1)[rank-1])


def integer_problem(d):
    d = np.asarray(d,dtype=np.float64)
    assert d.ndim == 1 and 0 < len(d) <= 30 and np.isfinite(d).all()
    ratios = [float(x).as_integer_ratio() for x in d]+[EPS.as_integer_ratio()]
    denominator = max(q for _,q in ratios)
    a = [p*(denominator//q) for p,q in ratios]
    return a[:-1],sum(a[:-1])-len(d)*a[-1],denominator


def signed_sums(a):
    sums = [0]
    for x in a:
        sums = [s-x for s in sums]+[s+x for s in sums]
    return sums


def signflip(d, formal=True):
    a,threshold,denominator = integer_problem(d)
    if formal:
        assert len(a)==30, 'Formal analysis requires K=30'
    mid=len(a)//2
    left,right = signed_sums(a[:mid]),sorted(signed_sums(a[mid:]))
    numerator=sum(len(right)-bisect_left(right,threshold-x) for x in left)
    return dict(numerator=numerator,denominator=2**len(a),p=numerator/2**len(a),
                K=len(a),epsilon=EPS,integer_scale_denominator=denominator,
                integer_threshold=threshold,arithmetic='exact binary64 rational MITM')


def fixed_sequence(p, valid=True):
    result={}
    for chain in (('H1','H3'),('H2','H4')):
        active=valid
        for h in chain:
            assert math.isfinite(p[h]) and 0<=p[h]<=1
            status=('rejected' if p[h]<.025 else 'not_rejected') if active else 'not_tested'
            result[h]=status
            active=active and status=='rejected'
    return result


def score(y, center, lower, upper):
    y,center,lower,upper=map(lambda x:np.asarray(x,dtype=float),(y,center,lower,upper))
    assert y.ndim==1 and len(y)>0 and y.shape==center.shape==lower.shape==upper.shape
    assert all(np.isfinite(x).all() for x in (y,center,lower,upper)) and (upper>=lower).all()
    n=len(y); count=int(((lower<=y)&(y<=upper)).sum()); c=count/n
    return dict(n=n,coverage=count,c=c,g=max(0.,.9-c),w=float(np.mean(upper-lower)),
                W=float(np.mean(upper-lower+20*np.maximum(lower-y,0)+20*np.maximum(y-upper,0))),
                MAE=float(np.mean(np.abs(center-y))),bias=float(np.mean(center-y)),
                median_relative_error=float(np.median(np.abs(10.**(center-y)-1))))


def interval_score(y,mu,sigma,q,delta=0.):
    center=np.asarray(mu)+delta
    return score(y,center,center-q*np.asarray(sigma),center+q*np.asarray(sigma))


def summary(a):
    a=np.asarray(a,dtype=float)
    assert a.ndim==1 and len(a)>0 and np.isfinite(a).all()
    q=np.quantile(a,[.25,.75])
    return dict(values=a.tolist(),mean=float(a.mean()),median=float(np.median(a)),
                min=float(a.min()),max=float(a.max()),q25=float(q[0]),q75=float(q[1]),IQR=float(q[1]-q[0]),
                positive=int((a>0).sum()),zero=int((a==0).sum()),negative=int((a<0).sum()))


def gates(rows,base,region):
    K=len(rows); assert K==len(base)>0
    n=rows[0][region]['n']; ng=rows[0]['G9']['n']
    c1=[r['G9']['coverage']>=ceil_div(4*ng,5) for r in rows]
    c80=[r[region]['coverage']>=ceil_div(4*n,5) for r in rows]
    c90=[r[region]['coverage']>=ceil_div(9*n,10) for r in rows]
    v80=[a and b and r[region]['w']<=3*r['G9']['w'] for a,b,r in zip(c1,c80,rows)]
    floor=[a and b for a,b in zip(c1,c80)]
    widths=np.array([r[region]['w'] for r in rows]); bw=np.array([r[region]['w'] for r in base])
    width_pairs=(widths<=2*bw).tolist()
    mean_cap=bool(widths.mean()<=1.5*bw.mean())
    total=sum(r[region]['coverage'] for r in rows)
    flags=dict(V80=sum(v80)>=26,HONEST90=sum(c90)>=26,
               MEAN90=total>=ceil_div(9*K*n,10),FLOOR80=all(floor))
    flags['A']=all(flags.values()); flags['WIDTH']=all(width_pairs) and mean_cap
    flags['J']=flags['A'] and flags['WIDTH']
    return dict(**flags,validity_pass_counts=dict(C1=sum(c1),V80=sum(v80),HONEST90=sum(c90),FLOOR80=sum(floor),
                 WIDTH_pairs=sum(width_pairs)),per_arm=dict(C1=c1,V80=v80,HONEST90=c90,FLOOR80=floor,WIDTH=width_pairs),
                 width_mean_pass=mean_cap,width_pair_veto_k=[k+1 for k,p in enumerate(width_pairs) if not p],
                 coverage_total=total,mean90_required=ceil_div(9*K*n,10),
                 width_ratio_of_means=float(widths.mean()/bw.mean()) if bw.mean()>0 else None,
                 width_ratios=[float(w/b) if b>0 else None for w,b in zip(widths,bw)])


def conclusion(gate,base_gate,status,region,gb,gd,valid=True):
    h1,h2=('H1','H3') if region=='XF' else ('H2','H4')
    a,w,j=gate['A'],gate['WIDTH'],gate['J']
    if not valid: text='不完整或无效，不作确认性结论'
    elif not a: text='未达到完整经验覆盖标准'
    elif not w: text='达到覆盖标准，但区间宽度代价超限'
    elif status[h1]!='rejected': text='达到经验门槛，但未确认相对新基线的欠覆盖改进'
    elif status[h2]!='rejected': text='覆盖欠缺改进且达到门槛，10%综合代价非劣未确认'
    else: text='本固定面板上完整D策略的区域成功（条件性推断）'
    dual=valid and a and base_gate['A'] and status[h1]!='rejected'
    if dual:
        text='基线与候选方法均达到预注册经验覆盖标准，相对欠覆盖改进未确认。'+('达到覆盖标准，但区间宽度代价超限。' if not w else '')
    allzero=all(x==0 for x in gb+gd)
    if dual and allzero: text+='本评估面板无额外相对欠覆盖需要缩减。'
    return dict(region=region,A=a,WIDTH=w,J=j,coverage_status=status[h1],Winkler_status=status[h2],
                SUCCESS=bool(valid and j and status[h1]==status[h2]=='rejected'),text=text,
                failed_coverage_components=[k for k in ('V80','HONEST90','MEAN90','FLOOR80') if not gate[k]],
                dual_A=dual,all_shortfalls_zero=allzero,
                baseline_nonzero_g=sum(x!=0 for x in gb),candidate_nonzero_g=sum(x!=0 for x in gd),
                baseline_mean_g=float(np.mean(gb)),candidate_mean_g=float(np.mean(gd)),
                shortfall_differences=summary(np.array(gb)-np.array(gd)),
                inference_limit='固定N87面板与单一族划分；符号对称/对称位置平移假设未经保证；经验门控无总体90%覆盖保证；不作中心单独归因')


def variance_policy(u,s,gu,gs):
    u,s=np.asarray(u),np.asarray(s)
    vu=0. if np.all(u==u[0]) else float(np.var(u,ddof=1))
    vs=0. if np.all(s==s[0]) else float(np.var(s,ddof=1))
    dg=np.asarray(gu)-np.asarray(gs)
    return dict(v_U=vu,v_S=vs,ratio=vs/vu if vu>0 else None,reduction=1-vs/vu if vu>0 else None,
                Delta_g=summary(dg),support=bool(vs<=.5*vu and dg.mean()>=0) if vu>0 else None,
                status='evaluable' if vu>0 else 'not_evaluable',U=summary(u),S=summary(s))


def winkler_sensitivity(b,d):
    b,d=np.asarray(b),np.asarray(d); a=1.10*b-d
    leave=[float(np.delete(a,k).mean()) for k in range(len(a))]
    return dict(pair_ratios=[float(y/x) if x!=0 else None for x,y in zip(b,d)],
                ratio_of_means=float(d.mean()/b.mean()) if b.mean()!=0 else None,
                leave_one_pair_out=summary(leave),nonpositive_count=sum(x<=0 for x in leave))


def analyze(arms,diagnostics,valid=True):
    rows=lambda s,m:[arms[f'{s}{k:02d}'][m] for k in range(1,31)]
    out=dict(process_valid=valid,gates={},summaries={},hypotheses={},conclusions={},
             ablation={},equal_width={},S0={},variance_decomposition={},winkler_sensitivity={})
    for s in ('U','S'):
        out['gates'][s]={};out['summaries'][s]={};out['ablation'][s]={};out['equal_width'][s]={}
        for m in ('B','E','D'):
            out['gates'][s][m]={z:gates(rows(s,m),rows(s,'B'),z) for z in ('XF','XT')}
            out['summaries'][s][m]={z:{metric:summary([r[z][metric] for r in rows(s,m)])
                for metric in ('coverage','c','g','w','W','MAE','bias','median_relative_error')} for z in ('G9','XF','XT','XFT')}
        for z in ('XF','XT'):
            er,dr=rows(s,'E'),rows(s,'D')
            contrasts={name:summary([sign*(d[z][key]-e[z][key]) for d,e in zip(dr,er)])
                for name,key,sign in [('c_D-c_E','c',1),('g_E-g_D','g',-1),('W_E-W_D','W',-1),
                                     ('w_D-w_E','w',1),('MAE_E-MAE_D','MAE',-1),('bias_D-bias_E','bias',1)]}
            out['ablation'][s][z]=contrasts
            out['equal_width'][s][z]={anchor:{metric:summary([diagnostics[f'{s}{k:02d}'][z][anchor][metric]
                for k in range(1,31)]) for metric in ('delta_c','delta_g','delta_W')} for anchor in ('qE','qD')}
    for h,z,kind in [('H1','XF','g'),('H2','XT','g'),('H3','XF','W'),('H4','XT','W')]:
        b=np.array([r[z][kind] for r in rows('U','B')]);d=np.array([r[z][kind] for r in rows('U','D')])
        diff=(1.10*b-d) if kind=='W' else b-d
        out['hypotheses'][h]=dict(**signflip(diff),differences=summary(diff),region=z)
    status=fixed_sequence({h:v['p'] for h,v in out['hypotheses'].items()},valid)
    for h in status: out['hypotheses'][h]['status']=status[h]
    for z in ('XF','XT'):
        gb=[r[z]['g'] for r in rows('U','B')];gd=[r[z]['g'] for r in rows('U','D')]
        out['conclusions'][z]=conclusion(out['gates']['U']['D'][z],out['gates']['U']['B'][z],status,z,gb,gd,valid)
        out['S0'][z]=variance_policy([r[z]['c'] for r in rows('U','D')],[r[z]['c'] for r in rows('S','D')],
                                     gd,[r[z]['g'] for r in rows('S','D')])
        mat=np.array([[arms[f'U{k:02d}'][m][z]['c'] for m in ('B','E','D')] for k in range(1,31)])
        grand=mat.mean();rm=mat.mean(axis=1,keepdims=True);cm=mat.mean(axis=0,keepdims=True)
        total=float(np.sum((mat-grand)**2))
        ss=dict(group=float(3*np.sum((rm-grand)**2)),method=float(30*np.sum((cm-grand)**2)),
                interaction=float(np.sum((mat-rm-cm+grand)**2)))
        out['variance_decomposition'][z]=dict(total=total,SS=ss,fractions={k:v/total if total>0 else None for k,v in ss.items()},
            group_majority=bool(total>0 and ss['group']/total>=.5))
        out['winkler_sensitivity'][z]=winkler_sensitivity([r[z]['W'] for r in rows('U','B')],[r[z]['W'] for r in rows('U','D')])
    out['both_success']=all(v['SUCCESS'] for v in out['conclusions'].values())
    out['S0_both_support']=all(v['support'] is True for v in out['S0'].values())
    return out
