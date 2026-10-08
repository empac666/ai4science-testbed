#!/usr/bin/env python3
"""Resumable HTTP-range extraction of N87; verify outer and inner ZIP CRCs."""
import argparse
import hashlib
import io
import json
import struct
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path
from datetime import datetime, timezone

URL = 'https://www.princeton.edu/~minjie/magnet/pre-training.zip'
ROOT = Path(__file__).resolve().parents[1]
CHUNK = 8 * 1024 * 1024

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def crc(path):
    value = 0
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): value = zlib.crc32(b, value)
    return value & 0xffffffff

class Remote(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD', headers={'User-Agent':'curl/8.0'}), timeout=90) as r:
            self.size = int(r.headers['Content-Length'])
            self.etag, self.modified = r.headers.get('ETag'), r.headers.get('Last-Modified')
        if not self.etag: raise RuntimeError('ETag required for safe resume')
    def seekable(self): return True
    def readable(self): return True
    def seek(self, n, whence=0):
        self.pos = n if whence == 0 else self.pos+n if whence == 1 else self.size+n
        return self.pos
    def tell(self): return self.pos
    def read(self, n=-1):
        n = self.size-self.pos if n < 0 else min(n, self.size-self.pos)
        if n <= 0: return b''
        start, end = self.pos, self.pos+n-1
        for attempt in range(5):
            try:
                req = urllib.request.Request(self.url+f'?magnet_range={start}-{end}',
                      headers={'Range': f'bytes={start}-{end}', 'If-Range': self.etag, 'User-Agent': 'curl/8.0'})
                with urllib.request.urlopen(req, timeout=180) as r:
                    if r.status != 206 or r.headers.get('Content-Range') != f'bytes {start}-{end}/{self.size}':
                        raise RuntimeError('Server did not honor exact range')
                    if r.headers.get('ETag') != self.etag: raise RuntimeError('Remote ETag changed')
                    b = r.read(n+1)
                if len(b) != n: raise RuntimeError('Incomplete range')
                self.pos += n
                return b
            except (OSError, RuntimeError):
                if attempt == 4: raise
                time.sleep(2**attempt)

def validate(path, info):
    if not path.is_file() or path.stat().st_size != info.file_size or crc(path) != info.CRC: return False
    with zipfile.ZipFile(path) as inner:
        bad = inner.testzip()
        if bad: raise RuntimeError('Inner ZIP CRC failed: '+bad)
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT/'data/magnet')
    args = ap.parse_args(); out = args.out; out.mkdir(parents=True, exist_ok=True)
    remote = Remote(URL)
    with zipfile.ZipFile(remote) as archive:
        infos = archive.infolist()
    entries = []
    for info in infos:
        if info.filename != 'pre-training/N87.zip': continue
        folder = out/'N87'; folder.mkdir(exist_ok=True)
        path = folder/'N87.zip'
        if not validate(path, info):
            # Store compressed outer member bytes. Deflate cannot resume from an
            # arbitrary uncompressed offset; the interrupted old ZIP is untrusted.
            part, state = folder/'N87.deflate.part', folder/'resume.json'
            identity = dict(url=URL, etag=remote.etag, member=info.filename,
                            compressed_size=info.compress_size, crc32=f'{info.CRC:08x}')
            if not state.exists() or json.loads(state.read_text()) != identity:
                part.unlink(missing_ok=True)
                state.write_text(json.dumps(identity, indent=2)+'\n')
            remote.seek(info.header_offset)
            header = remote.read(30)
            fields = struct.unpack('<4s5H3I2H', header)
            if fields[0] != b'PK\x03\x04': raise RuntimeError('Bad local header')
            start = info.header_offset+30+fields[-2]+fields[-1]
            done = part.stat().st_size if part.exists() else 0
            if done > info.compress_size: raise RuntimeError('Partial download oversized')
            with part.open('ab') as f:
                while done < info.compress_size:
                    remote.seek(start+done)
                    b = remote.read(min(CHUNK, info.compress_size-done))
                    f.write(b); f.flush(); done += len(b)
                    print(f'N87 compressed bytes {done}/{info.compress_size}', flush=True)
            temp = folder/'N87.zip.tmp'
            decoder = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
            if info.compress_type not in (zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED): raise RuntimeError('Unsupported compression')
            with part.open('rb') as src, temp.open('wb') as dst:
                for b in iter(lambda: src.read(1024*1024), b''):
                    dst.write(decoder.decompress(b) if decoder else b)
                if decoder:
                    dst.write(decoder.flush())
                    if not decoder.eof: raise RuntimeError('Truncated deflate stream')
            try:
                if not validate(temp, info): raise RuntimeError('Outer member length/CRC failed')
            except (RuntimeError, zipfile.BadZipFile):
                # A complete but corrupt partial would otherwise fail every rerun.
                part.unlink(missing_ok=True);temp.unlink(missing_ok=True)
                raise
            temp.replace(path)
            part.unlink(); state.unlink()
        else: print('Existing N87 ZIP: size, outer CRC and all inner CRCs verified', flush=True)
        entries.append(dict(path=str(path.relative_to(out)), url=URL, member=info.filename,
                      size_bytes=path.stat().st_size, sha256=sha(path), zip_crc32=f'{info.CRC:08x}',
                      compressed_size_bytes=info.compress_size, inner_crc_verified=True,
                      etag=remote.etag, last_modified=remote.modified))
    if not entries: raise RuntimeError('No N87 member')
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = dict(material='N87', verified_at=timestamp,
        archive=dict(url=URL, size_bytes=remote.size, etag=remote.etag,
                     last_modified=remote.modified, sha256=None,
                     note='Only member ranges fetched; whole archive SHA256 unavailable'),
        files=entries, archive_members=[dict(name=i.filename,size_bytes=i.file_size) for i in infos])
    previous = out/'MANIFEST.json'
    old = json.loads(previous.read_text()) if previous.exists() else {}
    manifest['retrieved_at'] = old.get('retrieved_at', timestamp) if old.get('files') == entries else timestamp
    previous.write_text(json.dumps(manifest, indent=2)+'\n')
    (out/'fetch_metrics.json').write_text(json.dumps({'fetch':{'verified':1,'bytes':entries[0]['size_bytes'],
        'outer_crc_verified':1,'inner_crc_verified':1}},indent=2)+'\n')
    print('N87 SHA256', entries[0]['sha256'], flush=True)
if __name__ == '__main__': main()
