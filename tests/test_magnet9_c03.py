"""C03 preregistered synthetic acceptance tests; never read real labels."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import itertools
import unittest
from fractions import Fraction
from unittest.mock import patch
import tempfile
import numpy as np
import pandas as pd
from magnet9_stats import *
from magnet9_common import LabelReader,read_targets,seed_audit
from magnet9_model import linear_columns,fit,delta,shadow_subsets
from magnet9_evaluate import equal_width
from magnet9_calibrate import parameters
from magnet9_independent_recompute import exact_count,independent_gate
from magnet9_sweep import paused_state
from magnet9_audit import validate_replay_points


def exhaustive(d):
    f=[Fraction.from_float(float(x)) for x in d]
    eps=Fraction.from_float(1e-12)
    den=max([x.denominator for x in f]+[eps.denominator])
    a=[int(x*den) for x in f];threshold=sum(a)-len(a)*int(eps*den)
    return sum(sum(s*x for s,x in zip(signs,a))>=threshold for signs in itertools.product((-1,1),repeat=len(a)))


def row(coverage=91,n=100,w=1.,gcoverage=91):
    return {z:dict(n=n,coverage=gcoverage if z=='G9' else coverage,w=w) for z in ('G9','XF','XT')}


class ExactTests(unittest.TestCase):
    def test_all_small_k_exhaustive(self):
        for k in range(1,17):
            d=np.array([((i*7)%11-5)*.125 for i in range(k)])
            self.assertEqual(signflip(d,formal=False)['numerator'],exhaustive(d),k)
            self.assertEqual(exact_count(d),exhaustive(d),k)

    def test_degeneracy(self):
        self.assertEqual(signflip(np.zeros(30))['numerator'],2**30)
        self.assertEqual(signflip(np.ones(30))['numerator'],1)
        self.assertEqual(signflip(-np.ones(30))['numerator'],2**30)
        d=[1.,1.,-1.,0.,0.,0.]
        self.assertEqual(signflip(d,False)['numerator'],8*signflip(d[:3],False)['numerator'])
        for d in ([1.,1.,-1.,-1.],[1e200,-1e200,1e-200,0.],[-1e-200,1e-200,0.],[-3,2,2,-1]):
            self.assertEqual(signflip(d,False)['numerator'],exhaustive(d))

    def test_epsilon_boundary(self):
        edge=1e-12/2
        for d,want in [(np.nextafter(edge,0),2),(edge,2),(np.nextafter(edge,np.inf),1)]:
            self.assertEqual(signflip([d],False)['numerator'],want)
            self.assertEqual(exact_count([d]),want)
        for d in ([1e20,-1e20,1e-12],[1e20,1e-12,-1e20]):
            self.assertEqual(signflip(d,False)['numerator'],exhaustive(d))

    def test_rejections(self):
        for d in ([],[[1,2]],[np.nan],[np.inf],[-np.inf],np.ones(31)):
            with self.assertRaises(AssertionError):signflip(d,False)
        for k in (1,14,15,16,29):
            with self.assertRaises(AssertionError):signflip(np.ones(k))

    def test_sequences(self):
        p=dict(H1=.025,H2=.001,H3=0,H4=.001)
        self.assertEqual(fixed_sequence(p),dict(H1='not_rejected',H3='not_tested',H2='rejected',H4='rejected'))
        p=dict(H1=.001,H2=.025,H3=.001,H4=0)
        self.assertEqual(fixed_sequence(p),dict(H1='rejected',H3='rejected',H2='not_rejected',H4='not_tested'))
        p=dict(H1=.001,H2=.001,H3=.03,H4=.03)
        self.assertEqual(fixed_sequence(p)['H3'],'not_rejected')
        self.assertTrue(all(x=='not_tested' for x in fixed_sequence(p,False).values()))


class RulesTests(unittest.TestCase):
    def test_replay_keeps_exact_selections(self):
        a=dict(sample_id=1,sigma=.02,score=.02,a_c=0,cell='')
        b=dict(a,sigma=.02+3e-15,score=.02+3e-15)
        self.assertGreater(validate_replay_points([a],[b]),0)
        with self.assertRaises(AssertionError):validate_replay_points([a],[dict(a,sample_id=2)])
        with self.assertRaises(AssertionError):validate_replay_points([a],[dict(a,sigma=.021)])

    def test_integer_ceilings_quantile(self):
        self.assertEqual([ceil_div(4*n,5) for n in (5361,8345)],[4289,6676])
        self.assertEqual([ceil_div(9*n,10) for n in (5361,8345)],[4825,7511])
        self.assertEqual([ceil_div(9*30*n,10) for n in (5361,8345)],[144747,225315])
        self.assertEqual(q90(np.arange(9)),8.)
        self.assertEqual(q90(np.arange(19)),17.)
        for a in ([],np.arange(8),[1]*9+[np.inf],[-1]*9):
            with self.assertRaises(AssertionError):q90(a)

    def test_floor_width_and_dual(self):
        rows=[row() for _ in range(30)];base=[row() for _ in range(30)]
        g=gates(rows,base,'XF');self.assertTrue(g['A']);self.assertTrue(g['WIDTH'])
        rows[-1]=row(79)
        g=gates(rows,base,'XF');self.assertFalse(g['FLOOR80']);self.assertFalse(g['A'])
        self.assertTrue(g['HONEST90']);self.assertTrue(g['MEAN90'])
        rows=[row() for _ in range(30)];rows[-1]=row(w=2.01)
        g=gates(rows,base,'XF');self.assertFalse(g['WIDTH']);self.assertEqual(g['width_pair_veto_k'],[30])
        for key,value in independent_gate(rows,base,'XF').items():self.assertEqual(g[key],value)
        zero=[row(w=0.) for _ in range(30)]
        self.assertTrue(gates(zero,zero,'XF')['WIDTH']);self.assertFalse(gates(base,zero,'XF')['WIDTH'])
        gate=gates(base,base,'XF');status=fixed_sequence(dict(H1=1,H2=1,H3=0,H4=0))
        c=conclusion(gate,gate,status,'XF',[.01]*30,[.01]*30)
        self.assertTrue(c['dual_A']);self.assertFalse(c['all_shortfalls_zero'])
        self.assertNotIn('无额外相对欠覆盖',c['text'])
        c=conclusion(gate,gate,status,'XF',[0.]*30,[0.]*30)
        self.assertIn('无额外相对欠覆盖',c['text'])
        self.assertEqual(c['Winkler_status'],'not_tested')

    def test_zero_variance_and_sensitivity(self):
        r=variance_policy([.9]*30,[.8]*30,[0]*30,[.1]*30)
        self.assertIsNone(r['ratio']);self.assertIsNone(r['support'])
        # Use exactly representable constants to enforce mathematical zero variance.
        r=variance_policy([1.]*30,[.5]*30,[0.]*30,[.4]*30)
        self.assertIsNone(r['ratio']);self.assertIsNone(r['support'])
        r=winkler_sensitivity([0.,1.,2.],[1.,1.,1.])
        self.assertIsNone(r['pair_ratios'][0]);self.assertEqual(len(r['leave_one_pair_out']['values']),3)
        np.testing.assert_allclose(r['leave_one_pair_out']['values'],[.65,.1,-.45],rtol=0,atol=2e-16)
        self.assertIsNone(winkler_sensitivity([0.,0.],[1.,2.])['ratio_of_means'])

    def test_center_sign_and_anchors(self):
        self.assertEqual(delta(np.array([2.,4.]),np.array([1.,1.]),[1,2],[1,2],[],[]),2.)
        self.assertEqual(delta(np.array([-2.,-4.]),np.array([1.,1.]),[1,2],[1,2],[],[]),-4.)
        for anchor in (.1,.5):
            r=equal_width(np.ones(20),np.zeros(20),np.ones(20),1.,anchor)
            self.assertEqual(r['delta_c'],1.);self.assertEqual(r['delta_g'],.9);self.assertGreater(r['delta_W'],0)
        q=dict(q0=1.,qE=dict(F=2.,T=3.),qD=dict(F=4.,T=5.),delta=dict(F=.2,T=-.1))
        self.assertEqual(parameters(q,'D','XF'),(4.,.2));self.assertEqual(parameters(q,'D','XFT'),(5.,.1))
        self.assertEqual(parameters(q,'D','G9'),(1.,0.))

    def test_shadow_features(self):
        self.assertNotIn('T_C^2',linear_columns([25,50],True))
        self.assertIn('T_C^2',linear_columns([25,50,70],True))
        self.assertIn('T_C^2',linear_columns([25,50],False))

    def test_permissions_before_parser(self):
        split=dict(pool=[1,2,3],S=[1,2,3],S0={'U01':[1]},CAL9=[4],G9=[5],XF=[6],XT=[7],XFT=[8])
        with tempfile.TemporaryDirectory() as tmp:
            a=LabelReader(split,'U01','acquire',Path(tmp)/'log')
            with patch('magnet9_common.read_targets',return_value=np.array([1.])) as parser:
                for ids in ([2],[4],[6]):
                    with self.assertRaises(AssertionError):a.read(ids)
                parser.assert_not_called();a.authorize([2]);a.read([2]);parser.assert_called_once()
            c=LabelReader(split,'U01','calibrate',Path(tmp)/'cal')
            with patch('magnet9_common.read_targets') as parser:
                for i in (1,5,6,7,8):
                    with self.assertRaises(AssertionError):c.read([i])
                parser.assert_not_called()
        with self.assertRaises(AssertionError):fit(pd.DataFrame(),[1,2],np.array([1.,2.]),True,allowed=[1])
        for cal,hold in (([1],[]),([],[1])):
            with self.assertRaises(AssertionError):delta([1.],[0.],[1],[1],cal,hold)
        with patch('magnet9_common.pd.read_csv') as parser:
            with self.assertRaises(AssertionError):read_targets([9],[1],[9])
            parser.assert_not_called()

    def test_hysteresis_and_seed_disjointness(self):
        self.assertFalse(paused_state(False,3.8*2**30));self.assertTrue(paused_state(True,4.3*2**30))
        self.assertTrue(paused_state(False,3.79*2**30));self.assertFalse(paused_state(True,4.31*2**30))
        self.assertEqual(seed_audit()['intersection'],[])


if __name__=='__main__':unittest.main()
