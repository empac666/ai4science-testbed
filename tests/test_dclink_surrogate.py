import importlib.util
import math
import hashlib
import json
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dclink_surrogate',ROOT/'scripts/dclink_surrogate.py')
dclink=importlib.util.module_from_spec(spec); spec.loader.exec_module(dclink)

def runtime_json_complete(relative, required):
    try:
        value=json.loads((ROOT/relative).read_text())
        if not isinstance(value,dict) or not all(key in value for key in required): return False
        if 'split_sha256' in required:
            return (all(isinstance(value[k],list) for k in dclink.GROUPS)
                    and all(isinstance(value[k],str) and len(value[k])==64 for k in ('split_sha256','design_sha256')))
        return all(isinstance(value[k],bool) if k.startswith('criterion.') else
                   isinstance(value[k],(int,float)) and not isinstance(value[k],bool) and math.isfinite(value[k])
                   for k in required)
    except (OSError,ValueError):
        return False

def runtime_design_complete():
    try:
        value=json.loads((ROOT/'data/dclink/design.json').read_text())
        return (isinstance(value,list) and len(value)>0
                and all(isinstance(r,dict) and all(k in r for k in ('case_id','load','dead_time_us','bw_iac_khz')) for r in value))
    except (OSError,ValueError):
        return False

RUNTIME_PARTITION_READY=(runtime_json_complete('data/dclink/split.json',dclink.GROUPS+['split_sha256','design_sha256'])
                         and runtime_design_complete())
RUNTIME_METRICS_READY=runtime_json_complete('data/dclink/surrogate_metrics.json',
    [f'{m}.{g}.{k}' for m in dclink.METHODS for g in dclink.SETS
     for k in ('n','mae','max_abs_error','bias','coverage','mean_width')]+
    ['criterion.gp_ood_coverage_in_85_95'])

class DCLinkSurrogateTests(unittest.TestCase):
    def test_committed_partition_manifest(self):
        manifest=json.loads((ROOT/'lab/cases/dclink/split_manifest.json').read_text())
        self.assertEqual(manifest['split_sha256'],'e4bac5895347942354a6dc7513c9989174888169c5c070ec9f3147900f5df4aa')
        self.assertEqual(manifest['design_sha256'],'fa900b0a2757c6e274438f978fd88b375008cab5c3e7d19fd61fa77908da46b5')
        self.assertEqual(manifest['seed'],20261003)
        self.assertEqual(manifest['counts'],dict(train=120,calib=40,test=40,ood_deadtime3=35,ood_lowload_lowbw=5))

    def test_synthetic_partition_and_hash(self):
        spec=importlib.util.spec_from_file_location('dclink_split',ROOT/'scripts/dclink_split.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        design=[dict(case_id=f'ind{i:02}',dead_time_us=1.,load=.5,bw_iac_khz=100.) for i in range(20)]
        design += [dict(case_id='dt',dead_time_us=3.,load=.2,bw_iac_khz=50.),
                   dict(case_id='corner',dead_time_us=1.,load=.35,bw_iac_khz=75.)]
        split,h=module.make_split(design)
        self.assertEqual(h,'071beb898e9897321404846e4c15f42c526d98a011579cb4cef41d0ee9a46e1c')
        self.assertEqual((split,h),module.make_split(list(reversed(design))))
        self.assertEqual(h,hashlib.sha256(json.dumps(split,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        groups=[set(split[k]) for k in dclink.GROUPS]
        for i,a in enumerate(groups):
            for b in groups[i+1:]: self.assertFalse(a&b)
        self.assertEqual(set.union(*groups),{r['case_id'] for r in design})
        self.assertEqual(split['ood_deadtime3'],['dt'])
        self.assertEqual(split['ood_lowload_lowbw'],['corner'])
        self.assertEqual([len(split[k]) for k in ('train','calib','test')],[12,4,4])

    def test_small_calibration_exact_rank(self):
        self.assertEqual(dclink.conformal_quantile(np.arange(1,10)),9)
        self.assertEqual(dclink.conformal_quantile(np.arange(1,41)),37)
        self.assertTrue(np.isinf(dclink.conformal_quantile([1,2,3])))
        self.assertEqual(dclink.conformal_quantile([4,1,3,2],.4),3)
        with self.assertRaises(ValueError): dclink.conformal_quantile([])

    def test_exchangeable_synthetic_coverage(self):
        rng=np.random.default_rng(831)
        # Independent Gaussian errors, repeated calibration samples, no fitted leakage.
        coverage=[]
        for _ in range(100):
            q=dclink.conformal_quantile(abs(rng.normal(size=199)))
            coverage.append(np.mean(abs(rng.normal(size=2000))<=q))
        self.assertAlmostEqual(float(np.mean(coverage)),.90,delta=.015)

    def test_interval_metric_definition(self):
        got=dclink.interval_metrics(np.array([0.,2.]),np.array([1.,1.]),np.array([0.,0.]),np.array([2.,2.]))
        self.assertEqual(got,dict(n=2,mae=1.,max_abs_error=1.,bias=0.,coverage=1.,mean_width=2.))

    @unittest.skipUnless(RUNTIME_PARTITION_READY, 'DC-link runtime split/design missing or incomplete')
    def test_rebuild_preserves_frozen_split_bytes(self):
        spec=importlib.util.spec_from_file_location('preserve',ROOT/'scripts/dclink_rebuild_preserving_split.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            isolated=Path(directory)
            (isolated/'data/dclink').mkdir(parents=True)
            (isolated/'lab/cases/dclink').mkdir(parents=True)
            for name in ('data/dclink/split.json','data/dclink/design.json','lab/cases/dclink/split_manifest.json'):
                (isolated/name).write_bytes((ROOT/name).read_bytes())
            path=isolated/'data/dclink/split.json'; expected=path.read_bytes()
            def simulated_cleanup(*args, **kwargs):
                path.unlink()
            with patch.object(module,'ROOT',isolated), patch.object(module.subprocess,'run',side_effect=simulated_cleanup) as command:
                module.main()
            self.assertEqual(path.read_bytes(),expected)
            self.assertEqual(command.call_args.args[0],['bash','scripts/dclink_rebuild.sh'])

    @unittest.skipUnless(RUNTIME_METRICS_READY, 'DC-link runtime metrics missing or incomplete')
    def test_metric_keys(self):
        path=ROOT/'data/dclink/surrogate_metrics.json'
        m=json.loads(path.read_text())
        for method in dclink.METHODS:
            for group in dclink.SETS:
                for k in ('n','mae','max_abs_error','bias','coverage','mean_width'):
                    self.assertIn(f'{method}.{group}.{k}',m)
        self.assertIsInstance(m['criterion.gp_ood_coverage_in_85_95'],bool)
        self.assertEqual(m['criterion.gp_ood_coverage_in_85_95'],.85<=m['gp_conformal.ood.coverage']<=.95)

if __name__=='__main__': unittest.main()
