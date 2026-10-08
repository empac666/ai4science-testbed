"""Exercise interrupted compressed-byte resume without network or real data."""
import contextlib
import importlib.util
import io
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('magnet_fetch',ROOT/'scripts/magnet_fetch.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MagnetFetchTests(unittest.TestCase):
    def fixture(self):
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('fixture.csv','one,two\n'*80)
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('pre-training/N87.zip',inner.getvalue())
        with zipfile.ZipFile(io.BytesIO(outer.getvalue())) as z: info=z.infolist()[0]
        fields=struct.unpack('<4s5H3I2H',outer.getvalue()[:30])
        start=30+fields[-2]+fields[-1]
        return inner.getvalue(),outer.getvalue(),info,start

    def test_interrupted_member_resumes_and_existing_zip_is_checked(self):
        inner,outer,info,start=self.fixture()
        class FakeRemote(io.BytesIO):
            fail=True
            reads=[]
            def __init__(self,url):
                super().__init__(outer);self.size=len(outer);self.etag='"fixture"';self.modified='fixture-date'
            def read(self,n=-1):
                offset=self.tell();self.reads.append((offset,n))
                if self.fail and n==16 and offset==start+16: raise RuntimeError('Simulated interruption')
                return super().read(n)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            with patch.object(m,'Remote',FakeRemote),patch.object(m,'CHUNK',16),patch('sys.argv',['magnet_fetch','--out',folder]),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'Simulated interruption'):m.main()
                part=out/'N87/N87.deflate.part'
                self.assertEqual(part.read_bytes(),outer[start:start+16])
                FakeRemote.fail=False;FakeRemote.reads=[]
                m.main()
                self.assertEqual((out/'N87/N87.zip').read_bytes(),inner)
                self.assertFalse(part.exists())
                self.assertNotIn((start,16),FakeRemote.reads)
                manifest=json.loads((out/'MANIFEST.json').read_text())
                self.assertEqual(manifest['files'][0]['sha256'],m.sha(out/'N87/N87.zip'))
                self.assertTrue(manifest['files'][0]['inner_crc_verified'])
                FakeRemote.reads=[];m.main()
                self.assertFalse(any(n==16 for _,n in FakeRemote.reads))
                # A full-size corrupt ZIP is rejected, then fetched afresh.
                damaged=bytearray(inner);damaged[40]^=1
                (out/'N87/N87.zip').write_bytes(damaged)
                FakeRemote.reads=[];m.main()
                self.assertEqual((out/'N87/N87.zip').read_bytes(),inner)
                self.assertIn((start,16),FakeRemote.reads)
if __name__=='__main__':unittest.main()
