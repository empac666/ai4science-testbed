import importlib.util
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('magnet_igse',ROOT/'scripts/magnet_igse.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MagNetIGSETests(unittest.TestCase):
    def test_sinusoid_equals_steinmetz(self):
        # Periodic PWL integration converges to the analytic sinusoidal identity.
        n=16384;theta=2*np.pi*np.arange(n)/n
        for k,a,b in ((.03,1.3,2.5),(.002,1.8,2.7),(.01,2.2,2.1)):
            frequency=np.array([50000.,150000.]);amplitude=np.array([.05,.2])
            waves=amplitude[:,None]*np.sin(theta+.37)
            got=m.igse(waves,frequency,k,a,b)
            expected=k*frequency**a*amplitude**b
            self.assertTrue(np.all(np.abs(got/expected-1)<1e-3))

    def test_triangle_closed_form(self):
        n=4096;t=np.arange(n)/n;amplitude=.13;f=85000.;k=.02;a=1.7;b=2.6
        triangle=amplitude*(1-4*np.abs(t-.5))
        expected=m.ki_from_steinmetz(k,a,b)*(4*amplitude*f)**a*(2*amplitude)**(b-a)
        self.assertAlmostEqual(float(m.igse(triangle,f,k,a,b))/expected,1.,places=12)
        # DC shifts do not change delta B or slopes.
        self.assertAlmostEqual(float(m.igse(triangle+1.5,f,k,a,b))/expected,1.,places=12)

    def test_grouped_signed_and_absolute_statistics(self):
        frame=pd.DataFrame({'waveform':['sine']*4+['triangle'],
            'temperature_C':[25,25,50,50,25],'relative_error':[-.1,.1,-.2,.4,-.5]})
        got=m.grouped_stats(frame)
        self.assertEqual(got['sine.T25.n'],2)
        self.assertEqual(got['sine.T25.within_10'],1.)
        self.assertEqual(got['sine.all.n'],4)
        self.assertAlmostEqual(got['sine.all.abs_mean'],.2)
        self.assertAlmostEqual(got['sine.all.abs_median'],.15)
        self.assertAlmostEqual(got['sine.all.abs_p95'],.37)
        self.assertEqual(got['sine.all.signed_median'],0.)
        self.assertEqual(got['sine.all.within_20'],.75)
        self.assertEqual(got['triangle.T25.signed_median'],-.5)

    def test_fixed_waveform_rules(self):
        t=np.arange(1024)/1024
        sine=np.sin(2*np.pi*t+.8)
        triangle=1-4*np.abs(t-.5)
        trapezoid=np.clip(triangle*2,-1,1)
        labels,_,_=m.classify([sine,triangle,trapezoid])
        self.assertEqual(labels.tolist(),['sine','triangle','trapezoid'])

    def test_log_fit_recovers_known_parameters(self):
        f=np.array([5e4,8e4,1.1e5,1.4e5,1.8e5,2.2e5]);b=np.array([.05,.1,.03,.2,.12,.08])
        p=.003*f**1.6*b**2.5
        got=m.fit_parameters(f,b,p)
        for key,value in (('k',.003),('alpha',1.6),('beta',2.5)):
            self.assertAlmostEqual(got[key],value,places=10)
if __name__=='__main__':unittest.main()
