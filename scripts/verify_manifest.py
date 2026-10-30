"""Check manifest identity and path safety. Does not establish semantic truth."""
import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'MANIFEST.json').read_text())
    paths = set()
    for entry in manifest['files']:
        relative = entry['path']
        if not isinstance(relative, str) or not relative or '\\' in relative:
            raise ValueError('invalid manifest path')
        path = (root/relative).resolve()
        if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.is_relative_to(root):
            raise ValueError('manifest path escapes root')
        if relative in paths:
            raise ValueError('duplicate manifest path')
        paths.add(relative)
        data = path.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('manifest mismatch: '+relative)
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
              and not any(part in {'.git','__pycache__','.venv','output'} for part in p.relative_to(root).parts)
              and p.name != 'MANIFEST.json'}
    if actual != paths:
        raise ValueError('manifest inventory differs from source files')
    return {'verified_files': len(paths), 'scope': 'BYTE_IDENTITY_AND_INVENTORY_ONLY'}


if __name__ == '__main__':
    import sys
    try:
        print(json.dumps(verify(Path(__file__).resolve().parents[1])))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        sys.exit(2)
