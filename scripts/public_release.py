"""Verify the sanitized release; historical commits are seed records, not local objects."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_file(relative):
    manifest = json.loads((ROOT / 'release_manifest.json').read_text())
    expected = manifest['files'][relative]
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError('Published file changed: ' + relative)


def main():
    manifest = json.loads((ROOT / 'release_manifest.json').read_text())
    for relative in manifest['files']:
        verify_file(relative)
    print(f"Verified {len(manifest['files'])} published files")


if __name__ == '__main__':
    main()
