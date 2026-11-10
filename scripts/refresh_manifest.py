"""Explicit build helper; run only after authorized changes and validation."""
import hashlib
import json
from pathlib import Path

if __package__:
    from .verify_manifest import reconcile_inventory, resolve_source_path
else:
    from verify_manifest import reconcile_inventory, resolve_source_path


ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    source_files, report = reconcile_inventory(ROOT)
    files = []
    for relative in sorted(source_files, key=Path):
        data = resolve_source_path(ROOT, relative).read_bytes()
        files.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

    manifest = {'scope': 'SOURCE_BYTES_NOT_TRUTH_OR_AUTHENTICITY', 'files': files}
    path = ROOT / 'MANIFEST.json'
    temp = ROOT / 'MANIFEST.tmp'
    temp.write_text(json.dumps(manifest, indent=2) + '\n')
    temp.replace(path)
    print(json.dumps({
        'files': len(files),
        'guard': 'BUILD_ONLY_NOT_AN_AUTOMATIC_REPAIR_OF_UNTRUSTED_SOURCE',
        'reconciliation': report,
    }))
