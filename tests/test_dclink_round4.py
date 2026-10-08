import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import dclink_active4 as active
import dclink_surrogate4 as model
import dclink_sweep4 as sweep
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel,RBF,WhiteKernel
from dclink_design3 import FEATURES,freeze,digest

def fixed(x,y):
    return GaussianProcessRegressor(kernel=ConstantKernel(1)*RBF(np.ones(4))+WhiteKernel(.01),
                                    alpha=1e-10,optimizer=None,normalize_y=True).fit(x,y)

class Round4(unittest.TestCase):
    def test_frozen_design(self):
        split=active.verify(); self.assertEqual(len(split['s0']),150)
        design=json.loads((active.OUT/'design.json').read_text())
        self.assertEqual(len(design),550)
        self.assertEqual(set(p['group'] for p in design),set(model.RANDOM))
        for p in design:
            self.assertEqual(p['case_id'],f"dclink4_{p['index']:03d}")
            self.assertEqual(p['nonideal_seed'],20280000+p['index'])

    def test_believer_direct_inverse_and_counts(self):
        rng=np.random.default_rng(42); x=rng.normal(size=(12,4)); z=rng.normal(size=(18,4)); cats=np.arange(18)%7*.5
        gp=fixed(x,2+5*rng.normal(size=12)); previous=[0.,0.,3.]
        indices,steps=active.mixed_believer(gp,z,cats,7,previous)
        condition=x.copy(); remaining=list(range(18)); counts={c:previous.count(c) for c in np.arange(0,3.5,.5)}
        for idx,step in zip(indices,steps):
            K=gp.kernel_(condition)+gp.alpha*np.eye(len(condition)); cross=gp.kernel_(condition,z[remaining])
            covariance=gp.kernel_(z[remaining])-cross.T@np.linalg.inv(K)@cross
            sigma=np.sqrt(np.maximum(np.diag(covariance),0))*gp._y_train_std
            scores=sigma/np.sqrt([1+counts[cats[i]] for i in remaining]); j=int(np.argmax(scores))
            self.assertEqual(idx,remaining[j]); self.assertEqual(step['a_c'],counts[cats[idx]])
            self.assertEqual(step['counts_before'],{str(c):n for c,n in counts.items()})
            np.testing.assert_allclose(step['sigma_quantiles'],np.quantile(sigma,active.LEVELS),atol=1e-8,rtol=0)
            np.testing.assert_allclose(step['score_quantiles'],np.quantile(scores,active.LEVELS),atol=1e-8,rtol=0)
            self.assertAlmostEqual(step['score'],scores[j],places=8)
            counts[cats[idx]]+=1; condition=np.vstack([condition,z[idx]]); remaining.pop(j)

    def test_tie_first_pool_and_in_batch_discount(self):
        gp=fixed(np.zeros((3,4)),np.arange(3.))
        z=np.ones((3,4)); indices,steps=active.mixed_believer(gp,z,[0.,0.,.5],2)
        self.assertEqual(indices,[0,2]); self.assertEqual(steps[1]['counts_before']['0.0'],1)

    def test_target_guard(self):
        split=dict(s0=['train'],calib=['cal'],test=['test'],ood_corner=['corner'],ood_dt3=['dt3'],random=['dclink3_200'],supplement_corner=[],supplement_dt3=[])
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.csv'; mixed=Path(tmp)/'mixed.csv'
            make=lambda cid,group,y:dict(case_id=cid,group=group,ideal=False,y=y,**dict(zip(FEATURES,[.5,1.,100.,2.])))
            pd.DataFrame([make('cal','E-in','MUST_NOT_PARSE'),make('train','E-in',1)]).to_csv(source,index=False)
            pd.DataFrame([make('dclink4_000','RS1','MUST_NOT_PARSE'),make('dclink4_550','M',2),make('dclink3_310','A','MUST_NOT_PARSE')]).to_csv(mixed,index=False)
            original=pd.read_csv
            def guarded(path,**kwargs):
                if 'y' in kwargs.get('usecols',[]):
                    self.assertIn(1,kwargs['skiprows'])
                    if path==mixed: self.assertIn(3,kwargs['skiprows'])
                return original(path,**kwargs)
            with patch.object(active,'SOURCE',source),patch.object(active.pd,'read_csv',side_effect=guarded):
                self.assertEqual(active.load_training(split,['dclink4_550'],mixed).y.tolist(),[1,2])
                for forbidden in ['cal','test','corner','dt3','dclink3_200','dclink3_310','dclink4_000','dclink4_549']:
                    with self.assertRaises(AssertionError): active.load_training(split,[forbidden],mixed)

    def fixture(self):
        metrics={f'{arm}.m2.{group}.{key}':value for arm in model.ARMS for group,n,c,w in [('test',60,48,2.),('ood_corner',40,32,6.),('ood_dt3',40,32,6.)] for key,value in [('n',n),('covered',c),('mean_width',w)]}
        metrics['A.m2.ood_corner.covered']=38; metrics['M.m2.ood_corner.covered']=36
        scores={arm:np.arange(1.,41.)*(1 if arm in ('A','M') else 2) for arm in model.ARMS}
        return metrics,scores

    def test_strict_score_p_and_coverage_boundaries(self):
        m,s=self.fixture(); d=model.decision(m,s,27,pvalue=.049999)
        self.assertTrue(d['criterion.H-A.pass']); self.assertTrue(d['criterion.H-M.pass'])
        self.assertFalse(model.decision(m,s,28)['criterion.M-0.pass'])
        self.assertFalse(model.decision(m,s,27,pvalue=.05)['criterion.A-3.pass'])
        s['RS1']=s['A'].copy(); d=model.decision(m,s,27)
        self.assertFalse(d['criterion.A-1.pass']); self.assertFalse(d['criterion.M-2.pass'])
        m,s=self.fixture(); m['M.m2.ood_corner.covered']=35
        self.assertFalse(model.decision(m,s,27)['criterion.M-2.pass'])
        for arm in model.RANDOM: m[f'{arm}.m2.ood_corner.covered']=34
        self.assertTrue(model.decision(m,s,27)['criterion.A-2.pass'])
        m['RS1.m2.ood_corner.covered']=35
        self.assertFalse(model.decision(m,s,27)['criterion.A-2.pass'])
        for arm in model.RANDOM: m[f'{arm}.m2.ood_corner.covered']=20
        m['RS1.m2.ood_corner.covered']=39
        self.assertFalse(model.decision(m,s,27)['criterion.A-2.pass'])

    def test_m1_all_boundaries(self):
        m,s=self.fixture(); self.assertTrue(model.decision(m,s,27)['criterion.M-1.pass'])
        for group,threshold in [('test',48),('ood_corner',32),('ood_dt3',32)]:
            changed=dict(m); changed[f'M.m2.{group}.covered']=threshold-1
            self.assertFalse(model.decision(changed,s,27)['criterion.M-1.pass'])
        for group in ['ood_corner','ood_dt3']:
            changed=dict(m); changed[f'M.m2.{group}.mean_width']=6.000001
            self.assertFalse(model.decision(changed,s,27)['criterion.M-1.pass'])
        self.assertEqual(model.paired(np.ones(40),np.ones(40))['pvalue'],1.)

    def test_interrupted_session_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); first=sweep.Session(out,2,'all',True)
            first.write('submitted',case_id='a',attempt=1,parameters_sha256='a')
            first.write('result',case_id='a',attempt=1,status='ok',result=dict(elapsed_s=2),parameters_sha256='a')
            first.write('heartbeat',wall_s=3.)
            first.write('submitted',case_id='b',attempt=1,parameters_sha256='b')
            with first.path.open('ab') as f: f.write(b'{"event":')
            second=sweep.Session(out,2,'all',True)
            second.write('end',wall_s=4.)
            summary=second.summary()
            self.assertEqual(summary['total_wall_s'],7.)
            self.assertEqual(summary['completed_n'],1)
            self.assertEqual(summary['interrupted_inflight_n'],1)
            self.assertEqual(summary['sessions'][0]['status'],'interrupted')
            third=sweep.Session(out,2,'all',True); self.assertEqual(third.summary()['interrupted_inflight_n'],1)

    def test_retry_resume_and_interruption_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); calls=[]; case=dict(case_id='test',load=.5)
            first=sweep.Session(out,1,'random',True)
            first.write('submitted',case_id='test',attempt=1,parameters_sha256=digest(case))
            second=sweep.Session(out,1,'random',True)
            def worker(p,out,smoke):
                calls.append(p.copy())
                return dict(status='failed',error='injected') if len(calls)==1 else dict(status='ok',result=dict(p,y=1,elapsed_s=.1))
            with patch.object(sweep,'ProcessPoolExecutor',ThreadPoolExecutor),patch.object(sweep,'worker',worker):
                self.assertEqual(sweep.batch([case],1,out,True,'sweep.csv',second),[])
                self.assertEqual(sweep.batch([case],1,out,True,'sweep.csv',second),[])
            history=sweep.journal_read(second.path); results=[r for r in history if r['event']=='result']
            self.assertEqual([r['attempt'] for r in results],[1,2]); self.assertEqual(calls,[case,case])
            self.assertEqual(second.end()['interrupted_inflight_n'],1)

    def test_failure_twice_no_replacement(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); session=sweep.Session(out,1,'all',True); case=dict(case_id='bad'); calls=[]
            def worker(p,*args): calls.append(p); return dict(status='failed',error='injected')
            with patch.object(sweep,'ProcessPoolExecutor',ThreadPoolExecutor),patch.object(sweep,'worker',worker):
                for _ in range(2): self.assertEqual(sweep.batch([case],1,out,True,'sweep.csv',session),['bad'])
            self.assertEqual(calls,[case,case]); self.assertEqual(session.end()['failed_case_ids'],['bad'])

    @unittest.skipUnless((ROOT/'data/dclink_src/simsw').exists(), 'External simulator constants not distributed')
    def test_batch_freeze_and_only_self_exclusion(self):
        split=active.verify(); pool=json.loads((active.R3/'pool.json').read_text())
        import dclink_active3 as active3
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with patch.object(active3,'gp_fit',side_effect=fixed):
                first=active.select_batch(1,split,pool,[],out,None,True)
            with patch.object(active,'fit_m2',side_effect=AssertionError('No refit on resume')):
                self.assertEqual(first,active.select_batch(1,split,pool,[],out,None,True))
            self.assertEqual([p['index'] for p in first['points']],[550,551])
            self.assertEqual(first['fingerprint']['candidates_sha256'],digest(pool[:200]))
            completed=pd.DataFrame(first['points']).assign(y=[.1,.2]); completed.to_csv(out/'sweep_mixed.csv',index=False)
            with patch.object(active3,'gp_fit',side_effect=fixed):
                second=active.select_batch(2,split,pool,[first],out,None,True)
            used={p['pool_id'] for p in first['points']}
            self.assertEqual(second['fingerprint']['candidates_sha256'],digest([p for p in pool[:200] if p['pool_id'] not in used]))
            self.assertEqual(second['fingerprint']['training_ids'][-2:],completed.case_id.tolist())
            self.assertEqual(sum(second['steps'][0]['counts_before'].values()),2)
            altered=dict(first); altered['kernel']='tampered'
            (out/'mixed/batch_1.json').write_text(json.dumps(altered))
            with self.assertRaises(AssertionError): active.select_batch(1,split,pool,[],out,None,True)

    def evidence_roundtrip(self,metrics):
        import subprocess
        import lab.repro.runner as runner
        from lab.evidence import check_case
        from dclink_case4 import build_report
        with tempfile.TemporaryDirectory(dir=active.OUT) as tmp:
            base=Path(tmp); supplied=base/'metrics.json'
            supplied.write_bytes(active.encoded(model.evidence_metrics(metrics)))
            with patch.object(runner,'ROOT',base):
                rec=runner.run('dclink4-synthetic',[sys.executable,'-c','print("synthetic only")'],inputs=[supplied],metrics_from=supplied)
                claims,report=build_report(metrics,rec['run_id'])
                (base/'claims.json').write_bytes(active.encoded(claims)); (base/'report.md').write_bytes(report)
                destination=runner.export_case(base/'case',[rec['run_id']],base/'claims.json',base/'report.md')
            result=check_case(destination)
            self.assertEqual(result['verdict'],'pass',result)
            result=subprocess.run([sys.executable,'-m','lab.evidence','check',str(destination)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless((ROOT/'data/dclink_src/simsw').exists(), 'External simulator constants not distributed')
    def test_synthetic_evaluation_end_to_end(self):
        import dclink_design3 as design3
        import dclink_active3 as active3
        from dclink_case4 import independent_check
        design,pool=design3.generate(); split=design3.make_split(design)
        base=pd.DataFrame(design); old=pd.read_csv(active.SOURCE,usecols=['case_id','group',*FEATURES])
        random=pd.DataFrame(json.loads((active.OUT/'design.json').read_text()))
        arms=dict(A=pd.DataFrame([design3.assign(dict(p,group='A'),310+i) for i,p in enumerate(pool[:110])]),
                  R=base[base.group=='R'].copy(),M=pd.DataFrame([active.assign(p,550+i) for i,p in enumerate(pool[110:220])]),
                  **{a:random[random.group==a].copy() for a in model.RANDOM})
        for frame in [base,old,*arms.values()]: frame['y']=frame.load+.1*frame.dead_time_us+.03*np.sin(frame.aperture_delay_us)
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint=Path(tmp)
            with patch.object(active3,'gp_fit',side_effect=fixed),patch.object(model.r3,'gp_fit',side_effect=fixed):
                metrics,pred,metadata=model.evaluate(split,base,arms,old,checkpoint)
            with patch.object(model.r3,'evaluate',side_effect=AssertionError('Must resume cached pairs')):
                again,pred2,_=model.evaluate(split,base,arms,old,checkpoint)
            self.assertEqual(metrics,again); pd.testing.assert_frame_equal(pred,pred2)
        self.assertEqual(len(pred),6240); self.assertEqual(set(metadata),set(model.ARMS))
        self.assertTrue(independent_check(metrics,pred)['verified'])
        self.evidence_roundtrip(metrics)
        for arm in model.ARMS:
            self.assertEqual(metrics[f'{arm}.m2.supplement_ood.n'],60)
            self.assertEqual(sum(metrics[f'{arm}.sampled.dead_time_{c:.1f}'] for c in np.arange(0,3.5,.5)),110)
        changed=dict(metrics); changed['criterion.A-1.pass']=not changed['criterion.A-1.pass']
        with self.assertRaises(AssertionError): independent_check(changed,pred)

if __name__=='__main__': unittest.main()
