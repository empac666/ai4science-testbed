import sys
import json
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import dclink_sweep2 as sweep
import dclink_split2 as split
import dclink_surrogate2 as model

class Round2Tests(unittest.TestCase):
    def test_design_ranges(self):
        pts=sweep.design()
        self.assertEqual(len(pts),210)
        self.assertEqual(pts,sweep.design())
        for group,count in [('E-in',150),('E-dt3',30),('E-corner',30)]:
            rows=[p for p in pts if p['group']==group]; self.assertEqual(len(rows),count)
            for p in rows:
                self.assertTrue(.3<=p['load']<= (.35 if group=='E-corner' else 1))
                self.assertTrue(50<=p['bw_iac_khz']<= (75 if group=='E-corner' else 400))
                self.assertTrue(0<=p['aperture_delay_us']<=30)
                self.assertIn(p['dead_time_us'],[3] if group=='E-dt3' else [0,.5,1,1.5,2,2.5])
                if group=='E-in': self.assertFalse(p['load']<=.35 and p['bw_iac_khz']<=75)
                self.assertEqual(p['nonideal_seed'],20261004+p['index']); self.assertEqual(p['seed'],20261002)
        path=ROOT/'data/dclink2/design.json'
        if path.exists(): self.assertEqual(pts,json.loads(path.read_text()))

    def test_no_leakage_and_hash(self):
        required=['data/dclink/design.json','data/dclink2/design.json','data/dclink2/split.json','lab/cases/dclink2/split_manifest.json']
        if not all((ROOT/p).exists() for p in required): self.skipTest('Frozen designs not available')
        s=split.verify(); groups=[set(s[g]) for g in split.GROUPS]
        for i,a in enumerate(groups):
            for b in groups[i+1:]: self.assertFalse(a&b)
        self.assertEqual([len(s[g]) for g in split.GROUPS],[200,75,75,30,30,40])
        self.assertEqual(set.union(*groups[1:5]),{p['case_id'] for p in sweep.design()})
        # Arbitrary target columns cannot affect design-only assignment.
        old=json.loads((ROOT/required[0]).read_text()); new=sweep.design()
        for p in old+new: p['y']=999
        self.assertEqual(split.make_split(new,old),{k:v for k,v in s.items() if not k.endswith('sha256')})

    def test_normalized_heteroscedastic_coverage(self):
        rng=np.random.default_rng(9831); cover=[]
        for _ in range(150):
            sigma=np.exp(rng.uniform(-2,2,75)); y=sigma*rng.normal(size=75)
            q=model.normalized_quantile(y,np.zeros(75),sigma)
            self.assertAlmostEqual(q,sorted(abs(y)/sigma)[68])
            ts=np.exp(rng.uniform(-2,2,2000)); ty=ts*rng.normal(size=2000)
            cover.append(np.mean(abs(ty)<=q*ts))
        self.assertAlmostEqual(np.mean(cover),.90,delta=.02)

    def test_criteria_counts_and_width(self):
        m={f'm2.{g}.{k}':v for g,n,c,w in [('test',75,62,2),('ood_dt3',30,24,6),('ood_corner',30,24,6)]
           for k,v in [('n',n),('covered',c),('mean_width',w)]}
        self.assertTrue(model.criteria(m)['criterion.overall'])
        m['m2.ood_corner.mean_width']=6.001
        self.assertFalse(model.criteria(m)['criterion.overall'])
        m['m2.ood_corner.mean_width']=6; m['m2.test.covered']=61
        self.assertFalse(model.criteria(m)['criterion.overall'])
if __name__=='__main__': unittest.main()
