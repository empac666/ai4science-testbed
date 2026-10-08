import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import dclink_design3 as design
import dclink_active3 as active
import dclink_surrogate3 as model
import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel,RBF,WhiteKernel

class Round3Tests(unittest.TestCase):
    def test_design_sequence_ranges_seeds(self):
        from scipy.stats import qmc
        d,p=design.generate(); self.assertEqual((d,p),design.generate())
        self.assertEqual(len(d),310); self.assertEqual(len(p),5000)
        rng=np.random.default_rng(20261010)
        for group,n,expected in [('E-in',600,120),('E-corner',40,40),('E-dt3',40,40),('R',110,110),('P',5000,5000)]:
            u=qmc.LatinHypercube(d=4,seed=rng).random(n)
            rows=p if group=='P' else [r for r in d if r['group']==group]
            self.assertEqual(len(rows),expected)
            raw=[]
            for x in u:
                load=.3+(.05 if group=='E-corner' else .7)*x[0]
                bw=50*(1.5 if group=='E-corner' else 8)**x[2]
                if group=='E-in' and load<=.35 and bw<=75: continue
                raw.append((load,bw,x))
            for row,(load,bw,x) in zip(rows,raw):
                self.assertEqual(row['load'],load); self.assertEqual(row['bw_iac_khz'],bw)
                self.assertEqual(row['aperture_delay_us'],30*x[3])
                self.assertEqual(row['dead_time_us'],3. if group=='E-dt3' else .5*int((7 if group in ('R','P') else 6)*x[1]))
                self.assertFalse(row['ideal']); self.assertEqual(row['solver_dt_ns'],50)
        for i,row in enumerate(d):
            self.assertEqual(row['index'],i); self.assertEqual(row['case_id'],f'dclink3_{i:03d}')
            self.assertEqual(row['nonideal_seed'],20270000+i)
        self.assertEqual([r['pool_id'] for r in p],[f'pool_{i:04d}' for i in range(5000)])

    def test_frozen_split_sources(self):
        if not design.SOURCE.exists() or not (design.OUT/'split.json').exists(): self.skipTest('Round3 data absent')
        s=design.verify(); old=pd.read_csv(design.SOURCE,usecols=['case_id','group'])
        self.assertEqual(s['s0'],old.loc[old.group=='E-in','case_id'].tolist())
        for g,key in [('E-corner','supplement_corner'),('E-dt3','supplement_dt3')]:
            self.assertEqual(s[key],old.loc[old.group==g,'case_id'].tolist())
        sets=[set(v) for v in s.values() if isinstance(v,list)]
        for i,a in enumerate(sets):
            for b in sets[i+1:]: self.assertFalse(a&b)
        ids=[f'dclink3_{i:03d}' for i in np.random.default_rng(20261011).permutation(120)]
        self.assertEqual(s['calib'],ids[:60]); self.assertEqual(s['test'],ids[60:])
        self.assertEqual([len(s[k]) for k in ('s0','calib','test','ood_corner','ood_dt3','random','supplement_corner','supplement_dt3')],[150,60,60,40,40,110,30,30])

    def test_believer_direct_matrix(self):
        rng=np.random.default_rng(910); x=rng.normal(size=(12,4)); z=rng.normal(size=(17,4)); y=3+7*rng.normal(size=12)
        gp=GaussianProcessRegressor(kernel=ConstantKernel(1.7)*RBF([.8,1.2,.9,1.4])+WhiteKernel(.08),
                                    alpha=1e-10,optimizer=None,normalize_y=True).fit(x,y)
        selected,stats,sigmas=active.believer(gp,z,5); condition=x.copy(); remaining=list(range(len(z)))
        for step in range(5):
            K=gp.kernel_(condition)+np.eye(len(condition))*gp.alpha
            cross=gp.kernel_(condition,z[remaining])
            cov=gp.kernel_(z[remaining])-cross.T@np.linalg.solve(K,cross)
            std=np.sqrt(np.diag(cov))*gp._y_train_std
            np.testing.assert_allclose(active.posterior_std(gp.kernel_,condition,np.linalg.cholesky(K),z[remaining],gp._y_train_std),std,atol=1e-8,rtol=0)
            np.testing.assert_allclose(stats[step],np.quantile(std,[0,.25,.5,.75,.9,1]),atol=1e-8,rtol=0)
            j=int(np.argmax(std)); self.assertEqual(selected[step],remaining[j]); self.assertAlmostEqual(sigmas[step],std[j],places=8)
            condition=np.vstack([condition,z[remaining.pop(j)]])
        np.testing.assert_allclose(gp.predict(z,return_std=True)[1],active.posterior_std(gp.kernel_,x,gp.L_,z,gp._y_train_std),atol=1e-8,rtol=0)

    def test_target_access_guard(self):
        s=dict(s0=['train'],calib=['holdout'],test=[],ood_corner=[],ood_dt3=[],random=[],supplement_corner=[],supplement_dt3=[])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.csv'
            pd.DataFrame([dict(case_id='holdout',group='E-in',ideal=False,y='MUST_NOT_PARSE',**{k:1 for k in design.FEATURES}),
                          dict(case_id='train',group='E-in',ideal=False,y=1,**{k:1 for k in design.FEATURES})]).to_csv(path,index=False)
            original=pd.read_csv
            def guarded(path,**kwargs):
                if 'y' in kwargs.get('usecols',[]): self.assertIn(1,kwargs['skiprows'])
                else: self.assertNotIn('y',kwargs['usecols'])
                return original(path,**kwargs)
            with patch.object(active,'SOURCE',path),patch.object(active.pd,'read_csv',side_effect=guarded):
                self.assertEqual(active.load_training(s,[]).y.tolist(),[1.])
            with self.assertRaises(AssertionError): active.load_training(s,['holdout'])

    def test_winkler_wilcoxon_and_criteria(self):
        np.testing.assert_array_equal(model.winkler(np.array([-1,1,4]),np.zeros(3),np.ones(3)*2),[22,2,42])
        a=np.arange(1.,41.); r=2*a
        self.assertLess(model.paired(a,r)['pvalue'],.05); self.assertGreater(model.paired(r,a)['pvalue'],.95)
        self.assertEqual(model.paired(a,a)['pvalue'],1)
        self.assertEqual(model.conformal_quantile(np.arange(60)),54)
        m={f'active.m2.{g}.{k}':v for g,n,c,w in [('test',60,48,2),('ood_corner',40,32,6),('ood_dt3',40,32,6)] for k,v in [('n',n),('covered',c),('mean_width',w)]}
        self.assertTrue(model.criteria(m,'active')['active.criterion.overall'])
        m['active.m2.ood_corner.mean_width']=6.0001
        self.assertFalse(model.criteria(m,'active')['active.criterion.overall'])

    def test_freeze_and_truncated_journal(self):
        from dclink_sweep3 import journal_read,append
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'f.json'; design.freeze(p,{'a':1}); design.freeze(p,{'a':1})
            with self.assertRaises(ValueError): design.freeze(p,{'a':2})
            journal=Path(tmp)/'progress.jsonl'; append(journal,{'case_id':'x'})
            with journal.open('ab') as f: f.write(b'{"partial":')
            self.assertEqual(journal_read(journal),[{'case_id':'x'}]); self.assertTrue(journal.read_bytes().endswith(b'\n'))

    def test_retry_resume(self):
        import dclink_sweep3 as sweep
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); calls=[]; case=dict(case_id='test',load=.5)
            def run(p,out,smoke):
                calls.append(p.copy())
                return dict(status='failed',error='test failure') if len(calls)==1 else dict(status='ok',result=dict(p,y=1))
            with patch.object(sweep,'ProcessPoolExecutor',ThreadPoolExecutor),patch.object(sweep,'worker',run):
                self.assertEqual(sweep.batch([case],1,out,True,'sweep.csv'),[])
                before=(out/'progress.jsonl').read_bytes()
                self.assertEqual(sweep.batch([case],1,out,True,'sweep.csv'),[])
                self.assertEqual((out/'progress.jsonl').read_bytes(),before)
                self.assertEqual(calls,[case,case])

    def test_synthetic_evaluation_pipeline(self):
        if not design.SOURCE.exists() or not (ROOT/'data/dclink_src/simsw').exists(): self.skipTest('Source inputs absent')
        d,p=design.generate(); split=design.make_split(d)
        old=pd.read_csv(design.SOURCE,usecols=['case_id','group',*design.FEATURES])
        a=pd.DataFrame([design.assign(dict(point,group='A',batch=1),310+i) for i,point in enumerate(p[:110])])
        base=pd.DataFrame(d)
        for frame in (old,a,base):
            frame['y']=frame.load+frame.dead_time_us*.1+np.sin(frame.aperture_delay_us)*.03
        def fixed(z,y):
            return GaussianProcessRegressor(kernel=ConstantKernel(1)*RBF(np.ones(4))+WhiteKernel(.01),
                                            alpha=1e-10,optimizer=None,normalize_y=True).fit(z,y)
        with patch.object(active,'gp_fit',side_effect=fixed),patch.object(model,'gp_fit',side_effect=fixed):
            metrics,pred,metadata=model.evaluate(split,base,a,old)
        self.assertEqual(len(pred),1560)
        self.assertEqual(metrics['active.m2.supplement_ood.n'],60)
        for (arm,method,group),r in pred.groupby(['arm','method','split']):
            key=f'{arm}.{method}.{group}'
            if group=='calib':
                self.assertAlmostEqual(np.sort(abs(r.y-r.prediction)/r.sigma)[54],metrics[key+'.q'])
            else:
                self.assertEqual(int(((r.y>=r.lower)&(r.y<=r.upper)).sum()),metrics[key+'.covered'])
        self.assertEqual(metrics['criterion.overall'],metrics['active.criterion.overall'] and metrics['comparison.P.pass'])

    def test_joint_simulation(self):
        from scipy.stats import betabinom
        m=model.joint_simulation()
        self.assertEqual(m['joint_simulation.n'],100000)
        for g,n,limit in [('test',60,48),('ood_corner',40,32),('ood_dt3',40,32)]:
            self.assertAlmostEqual(m[f'joint_simulation.{g}.failed']/100000,betabinom.cdf(limit-1,n,55,6),delta=.004)
        self.assertLessEqual(m['joint_simulation.coverage_failed'],sum(m[f'joint_simulation.{g}.failed'] for g in ('test','ood_corner','ood_dt3')))

if __name__=='__main__': unittest.main()
