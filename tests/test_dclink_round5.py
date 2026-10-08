import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import dclink_active5 as active
import dclink_surrogate5 as model
import dclink_sweep5 as sweep
import dclink_active3 as active3
import dclink_active4 as active4
from dclink_case5 import independent_check,verify_sampling,build_report
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel,RBF,WhiteKernel

def fixed(x,y):
    return GaussianProcessRegressor(kernel=ConstantKernel(1)*RBF(np.ones(4))+WhiteKernel(.01),
                                    alpha=1e-10,optimizer=None,normalize_y=True).fit(x,y)

class Round5(unittest.TestCase):
    def test_freeze(self):
        split=active.verify(); self.assertEqual(len(split['s0']),150)
        self.assertEqual(active.sha(active.STAGE/'config_prerun.json'),active.CONFIG_SHA)
        self.assertEqual(active.sha(active.OUT/'design.json'),active.DESIGN_SHA)
        self.assertEqual(active.CONFIG['model'],active.MODEL_CONFIG)

    def test_index_seed_all_2120(self):
        design=json.loads((active.OUT/'design.json').read_text())
        adaptive=[active.assign({},a,j) for a in active.ADAPTIVE for j in range(110)]
        points=design+adaptive
        self.assertEqual(sorted(p['index'] for p in points),list(range(2120)))
        for p in points:
            self.assertEqual(p['case_id'],f"dclink5_{p['index']:04d}")
            self.assertEqual(p['nonideal_seed'],20290000+p['index'])
            self.assertEqual(p['seed'],p['nonideal_seed']); self.assertFalse(p['ideal'])
        for arm in ['A0','M7','R1','A_1']:
            with self.assertRaises(AssertionError): active.arm_start(arm)

    def test_target_guard_cross_arm_and_unparsed_y(self):
        split=dict(s0=['train'],calib=['cal'],test=['test'],ood_corner=['corner'],ood_dt3=['dt3'],random=['dclink3_200'])
        make=lambda cid,group,y:dict(case_id=cid,group=group,ideal=False,y=y,**dict(zip(active.FEATURES,[.5,1.,100.,2.])))
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'old.csv'; path=Path(tmp)/'adaptive.csv'
            pd.DataFrame([make('cal','E-in','MUST_NOT_READ'),make('train','E-in',1)]).to_csv(source,index=False)
            forbidden=['dclink5_0000','dclink5_0060','dclink5_0100','dclink5_0140','dclink5_0910','dclink5_1020','dclink3_310','dclink4_550','dclink4_000']
            pd.DataFrame([make(cid,'other','MUST_NOT_READ') for cid in forbidden]+[make('dclink5_0800','A1',2)]).to_csv(path,index=False)
            original=pd.read_csv
            def guarded(p,**kwargs):
                if 'y' in kwargs.get('usecols',[]):
                    expected=list(range(1,len(forbidden)+1)) if p==path else [1]
                    self.assertEqual(kwargs['skiprows'],expected)
                else: self.assertEqual(kwargs['usecols'],['case_id','group','ideal'])
                return original(p,**kwargs)
            with patch.object(active,'SOURCE',source),patch.object(active.pd,'read_csv',side_effect=guarded):
                self.assertEqual(active.load_training(split,'A1',['dclink5_0800'],path).y.tolist(),[1,2])
                for cid in forbidden+['cal','test','corner','dt3']:
                    with self.assertRaises(AssertionError): active.load_training(split,'A1',[cid],path)
                with self.assertRaises(AssertionError): active.load_training(split,'M1',['dclink5_0800'],path)

    def test_believer_reuse_identity_and_results(self):
        self.assertIs(active.fit_m2,active3.fit_m2); self.assertIs(active.believer,active3.believer)
        self.assertIs(active.posterior_std,active3.posterior_std); self.assertIs(active.mixed_believer,active4.mixed_believer)
        rng=np.random.default_rng(5); gp=fixed(rng.normal(size=(12,4)),rng.normal(size=12)); z=rng.normal(size=(20,4))
        self.assertEqual(active.believer(gp,z,4),active3.believer(gp,z,4))
        self.assertEqual(active.mixed_believer(gp,z,np.arange(20)%7*.5,4,[3.,3.]),
                         active4.mixed_believer(gp,z,np.arange(20)%7*.5,4,[3.,3.]))

    @unittest.skipUnless((ROOT/'data/dclink_src/simsw').exists(), 'External simulator constants not distributed')
    def test_frozen_batch_self_only_and_incomplete_guard(self):
        split=active.verify(); pool=json.loads((active.R3/'pool.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with patch.object(active3,'gp_fit',side_effect=fixed):
                first=active.select_batch('A1',1,split,pool,[],out,None,True)
                other=active.select_batch('A2',1,split,pool,[],out,None,True)
                mixed=active.select_batch('M1',1,split,pool,[],out,None,True)
            self.assertEqual([p['pool_id'] for p in first['points']],[p['pool_id'] for p in other['points']])
            for rec in [first,other,mixed]: self.assertEqual(rec['fingerprint']['candidates_sha256'],active.digest(pool[:200]))
            with patch.object(active,'fit_m2',side_effect=AssertionError('Frozen batch refit')):
                self.assertEqual(first,active.select_batch('A1',1,split,pool,[],out,None,True))
            pd.DataFrame(first['points'][:1]).assign(y=.1).to_csv(out/'sweep_adaptive.csv',index=False)
            with self.assertRaises(AssertionError): active.select_batch('A1',2,split,pool,[first],out,None,True)
            pd.DataFrame(first['points']+other['points']+mixed['points']).assign(y=.1).to_csv(out/'sweep_adaptive.csv',index=False)
            with patch.object(active3,'gp_fit',side_effect=fixed): second=active.select_batch('A1',2,split,pool,[first],out,None,True)
            self.assertEqual(second['fingerprint']['training_ids'][-2:],[p['case_id'] for p in first['points']])
            used={p['pool_id'] for p in first['points']}
            self.assertEqual(second['fingerprint']['candidates_sha256'],active.digest([p for p in pool[:200] if p['pool_id'] not in used]))
            path=out/'adaptive/A1/batch_1.json'; changed=dict(first,kernel='bad'); path.write_text(json.dumps(changed))
            with self.assertRaises(AssertionError): active.select_batch('A1',1,split,pool,[],out,None,True)

    def test_permutation(self):
        self.assertEqual(model.sign_flip([1]*6),1/64)
        self.assertEqual(model.sign_flip([1]*5+[-.1]),2/64)
        self.assertEqual(model.sign_flip([0]*6),1.)
        self.assertEqual(model.sign_flip([1,1,0,0,0,0]),16/64)
        self.assertEqual(model.sign_flip([1,-1,0,0,0,0]),48/64)
        self.assertEqual(model.sign_flip([.1,.2,.3,.4,.5,.6]),1/64)
        with self.assertRaises(AssertionError): model.sign_flip([1]*5)
        with self.assertRaises(AssertionError): model.sign_flip([1]*5+[np.nan])

    def test_fixed_sequence(self):
        self.assertEqual(model.fixed_sequence([1/64]*4),['rejected']*4)
        for i in range(4):
            p=[1/64]*4; p[i]=.05
            self.assertEqual(model.fixed_sequence(p),['rejected']*i+['not_rejected']+['not_tested']*(3-i))
        self.assertEqual(model.fixed_sequence([1,0,0,0]),['not_rejected']+['not_tested']*3)

    def fixture(self):
        return {f'{a}.m2.{g}.{key}':v for a in model.ARMS for g,n,c,w in [('T5',60,48,2.),('C5',40,32,6.),('D5',40,32,6.)]
                for key,v in [('n',n),('covered',c),('mean_width',w),('mean_winkler',2. if a[0]=='R' else 1.)]}

    def test_coverage_width_and_cv_boundary(self):
        m=self.fixture(); self.assertTrue(model.decision(m)['CV-A.pass'])
        for g,thr in [('T5',48),('C5',32),('D5',32)]:
            changed=dict(m); changed[f'A1.m2.{g}.covered']=thr-1
            d=model.decision(changed); self.assertEqual(d['CV-A.count'],5); self.assertTrue(d['CV-A.pass'])
            changed[f'A2.m2.{g}.covered']=thr-1
            self.assertFalse(model.decision(changed)['CV-A.pass'])
        for g in ['C5','D5']:
            changed=dict(m); changed[f'M1.m2.{g}.mean_width']=6.00000001
            self.assertFalse(model.criteria(changed,'M1')['M1.criterion.overall'])
        changed=dict(m); changed['A1.m2.T5.n']=59
        with self.assertRaises(AssertionError): model.criteria(changed,'A1')

    def test_claim_gates(self):
        m=self.fixture(); d=model.decision(m)
        self.assertTrue(d['claim_A']); self.assertTrue(d['claim_M']); self.assertTrue(d['claim_M_noninf']); self.assertFalse(d['claim_M_dt3'])
        for k in range(1,7): m[f'A{k}.m2.C5.mean_winkler']=3.
        d=model.decision(m); self.assertEqual(d['H2.status'],'not_tested'); self.assertFalse(d['claim_M'])

    def test_interrupted_timing(self):
        self.assertIs(sweep.Session,__import__('dclink_sweep4').Session)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); a=sweep.Session(out,2,'all',True)
            a.write('submitted',case_id='a',attempt=1,parameters_sha256='a')
            a.write('result',case_id='a',attempt=1,status='ok',result=dict(elapsed_s=2),parameters_sha256='a')
            a.write('heartbeat',wall_s=3.); a.write('submitted',case_id='b',attempt=1,parameters_sha256='b')
            with a.path.open('ab') as f: f.write(b'{"partial":')
            b=sweep.Session(out,2,'all',True); b.write('end',wall_s=4.)
            result=b.summary(); self.assertEqual(result['total_wall_s'],7.)
            self.assertEqual(result['interrupted_inflight_n'],1); self.assertEqual(result['completed_n'],1)
            c=sweep.Session(out,2,'all',True); self.assertEqual(c.summary()['interrupted_inflight_n'],1)

    def test_retry_resume_unchanged_parameters(self):
        import dclink_sweep4 as r4
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); session=sweep.Session(out,2,'all',True); calls=[]; case=dict(case_id='test',load=.5)
            def worker(p,*args):
                calls.append(p.copy())
                return dict(status='failed',error='injected') if len(calls)==1 else dict(status='ok',result=dict(p,y=1.,elapsed_s=.1))
            with patch.object(r4,'ProcessPoolExecutor',ThreadPoolExecutor),patch.object(r4,'worker',worker):
                self.assertEqual(sweep.batch([case],2,out,True,'sweep.csv',session),[])
                self.assertEqual(sweep.batch([case],2,out,True,'sweep.csv',session),[])
                self.assertEqual(calls,[case,case])
                with self.assertRaises(AssertionError): sweep.batch([dict(case,load=.6)],2,out,True,'sweep.csv',session)
            session.end()

    def test_sync_all_arms_before_simulation(self):
        from types import SimpleNamespace
        split=active.verify(); order=[]
        def select(arm,b,split,pool,previous,out,stage,smoke):
            order.append(('select',b,arm)); return dict(points=[dict(case_id=f'{arm}-{b}-{j}') for j in range(22)])
        def batch(points,jobs,out,smoke,name,session):
            order.append(('simulate',name,len(points))); return []
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            # Exercise full schedule without requiring a READY marker or any simulation.
            marker={'sha256':{'lab/cases/dclink5/config_prerun.json':active.CONFIG_SHA,'lab/cases/dclink5/design.json':active.DESIGN_SHA}}
            (out/'READY_TO_RUN').write_text(json.dumps(marker)); (out/'design.json').write_bytes((active.OUT/'design.json').read_bytes())
            with patch.object(sweep,'OUT',out),patch.object(sweep,'STAGE',out/'stage'),patch.object(sweep,'memory_gate'),patch.object(sweep,'prepare_replay'),patch.object(sweep,'select_batch',side_effect=select),patch.object(sweep,'batch',side_effect=batch):
                (out/'stage').mkdir(); sweep.execute(SimpleNamespace(smoke=False,jobs=2,phase='all'),out,split)
        self.assertEqual(order[0],('simulate','sweep_base.csv',800))
        for b in range(1,6):
            block=order[1+(b-1)*13:1+b*13]
            self.assertEqual(block[:12],[('select',b,arm) for arm in active.ADAPTIVE])
            self.assertEqual(block[-1],('simulate','sweep_adaptive.csv',264*b))

    def test_adaptive_requires_completed_base(self):
        from dclink_sweep3 import append
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); points=[dict(case_id='base1'),dict(case_id='base2')]
            with self.assertRaises(AssertionError): sweep.require_base_complete(out,points)
            for p in points:
                append(out/'progress.jsonl',dict(event='result',case_id=p['case_id'],status='ok',parameters_sha256=active.digest(p)))
            sweep.require_base_complete(out,points)
            with self.assertRaises(AssertionError): sweep.require_base_complete(out,[dict(points[0],load=.5),points[1]])

    def test_terminal_failure_stops_next_batch(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with patch.object(sweep,'memory_gate'),patch.object(sweep,'prepare_replay'),patch.object(sweep,'batch',return_value=['failed']),patch.object(sweep,'select_batch') as select:
                with self.assertRaises(RuntimeError): sweep.execute(SimpleNamespace(smoke=True,jobs=2,phase='all'),out,active.verify())
                select.assert_not_called()

    def synthetic(self):
        split=active.verify(); pool=json.loads((active.R3/'pool.json').read_text())
        base=pd.DataFrame(json.loads((active.OUT/'design.json').read_text()))
        old_base=pd.read_csv(active.R3/'sweep_base.csv',usecols=['case_id','group',*active.FEATURES])
        old=pd.read_csv(active.SOURCE,usecols=['case_id','group',*active.FEATURES])
        arms={a:(base[base.group==a].copy() if a[0]=='R' else pd.DataFrame([active.assign(p,a,j) for j,p in enumerate(pool[:110])])) for a in model.ARMS}
        for frame in [base,old_base,old,*arms.values()]: frame['y']=frame.load+.1*frame.dead_time_us+.03*np.sin(frame.aperture_delay_us)
        return split,base,arms,old_base,old

    @unittest.skipUnless((ROOT/'data/dclink_src/simsw').exists(), 'External simulator constants not distributed')
    def test_synthetic_18_arms_end_to_end(self):
        args=self.synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint=Path(tmp)
            with patch.object(active3,'gp_fit',side_effect=fixed),patch.object(model,'gp_fit',side_effect=fixed):
                m,p,meta=model.evaluate(*args,checkpoint)
            with patch.object(model,'evaluate_arm',side_effect=AssertionError('Must resume')):
                m2,p2,_=model.evaluate(*args,checkpoint)
            self.assertEqual(m,m2); pd.testing.assert_frame_equal(p,p2)
            # Checkpoint fingerprints reject target changes.
            args[1].loc[0,'y']+=1
            with self.assertRaises(AssertionError): model.evaluate(*args,checkpoint)
        self.assertEqual(len(p),18*3*400); self.assertEqual(set(meta),set(model.ARMS))
        self.assertTrue(independent_check(m,p)['verified']); verify_sampling(m,args[2])
        for key in ['claim_A','H1.rejected','CV-A.pass','A1.criterion.C1.pass']:
            changed=dict(m); changed[key]=not changed[key]
            with self.assertRaises(AssertionError): independent_check(changed,p)
        changed=dict(m); changed['H1.pvalue']=.123
        with self.assertRaises(AssertionError): independent_check(changed,p)
        self.evidence_roundtrip(m)
        self.first_seal_roundtrip(m,p,meta)
        from dclink_figures5 import plot
        with tempfile.TemporaryDirectory() as tmp:
            plot(m,Path(tmp)); self.assertEqual(len(list(Path(tmp).glob('r5_*.png'))),3)

    def first_seal_roundtrip(self,m,p,meta):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out'; stage=Path(tmp)/'stage'; out.mkdir(); stage.mkdir()
            source=out/'input.json'; source.write_text('{}')
            with patch.object(model,'OUT',out),patch.object(model,'STAGE',stage),patch.object(model,'ROOT',Path(tmp)),patch.object(model,'inputs',return_value=[source]),patch.object(model,'regression_check',return_value=dict(verified=True)),patch.object(model,'load_inputs',return_value=(None,None)),patch.object(model,'evaluate',return_value=(m,p,dict(meta))) as evaluate:
                model.run({}); model.run({}); self.assertEqual(evaluate.call_count,1)
                self.assertTrue((stage/'first').is_dir()); self.assertFalse((stage/'first.pending').exists())
                source.write_text('{"changed":true}')
                with self.assertRaises(AssertionError): model.run({})
                source.write_text('{}')
                (stage/'first/predictions.csv').write_text('tampered')
                with self.assertRaises(AssertionError): model.run({})

    def evidence_roundtrip(self,m):
        import subprocess
        import lab.repro.runner as runner
        from lab.evidence import check_case
        with tempfile.TemporaryDirectory(dir=ROOT/'data/dclink5_smoke') as tmp:
            base=Path(tmp); supplied=base/'metrics.json'
            supplied.write_bytes(active.encoded(model.evidence_metrics(model.numeric_metrics(m))))
            with patch.object(runner,'ROOT',base):
                rec=runner.run('dclink5-synthetic',[sys.executable,'-c','print("synthetic only")'],inputs=[supplied],metrics_from=supplied)
                claims,report=build_report(m,rec['run_id'])
                (base/'claims.json').write_bytes(active.encoded(claims)); (base/'report.md').write_bytes(report)
                dest=runner.export_case(base/'case',[rec['run_id']],base/'claims.json',base/'report.md')
            self.assertEqual(check_case(dest)['verdict'],'pass')
            result=subprocess.run([sys.executable,'-m','lab.evidence','check',str(dest)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__': unittest.main()
