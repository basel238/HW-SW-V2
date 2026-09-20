#!/usr/bin/env python3
"""Check vendored HardFloat bytes against the official-download manifest."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent / 'vendor' / 'HardFloat-1'
manifest = json.loads((root / 'PROVENANCE.json').read_text())
for name, expected in manifest['files'].items():
    actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f'FAIL: vendored source changed: {name}')
print(f"HardFloat provenance: PASS ({len(manifest['files'])} unchanged files)")
print('Official archive SHA-256:', manifest['archive_sha256'])
