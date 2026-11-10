"""Check manifest identity and path safety. Does not establish semantic truth."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


PATH_ROLES = {
    '.git': 'git_metadata',
    '.venv': 'runtime_environment',
    '__pycache__': 'bytecode_cache',
    'output': 'generated_output',
}


def reconcile_inventory(root, *, include_paths=False):
    """Walk every directory once and assign each entry to its local role."""
    roles = ('source', 'manifest_control', *PATH_ROLES.values())
    counts = {role: dict.fromkeys(('files', 'directories', 'symlinks', 'other'), 0) for role in roles}
    source_files = set()
    path_details = {} if include_paths else None
    pending = [(root, '', 'source')]

    while pending:
        directory, prefix, parent_role = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = prefix + entry.name
                role = PATH_ROLES.get(entry.name, parent_role)
                if entry.is_dir(follow_symlinks=False):
                    kind = 'directories'
                    pending.append((entry.path, relative + '/', role))
                elif entry.is_symlink():
                    kind = 'symlinks'
                elif entry.is_file(follow_symlinks=False):
                    kind = 'files'
                else:
                    kind = 'other'
                if role == 'source':
                    if entry.name == 'MANIFEST.json' and kind != 'directories':
                        role = 'manifest_control'
                    elif kind == 'files' or (kind == 'symlinks' and entry.is_file()):
                        source_files.add(relative)
                counts[role][kind] += 1
                if path_details is not None:
                    path_details[relative] = {'role': role, 'kind': kind}

    report = {
        'scope': 'OBSERVED_PATH_TYPES',
        'total_paths': sum(sum(kinds.values()) for kinds in counts.values()),
        'by_role': counts,
    }
    if path_details is not None:
        report['paths'] = dict(sorted(path_details.items()))
    return source_files, report


def resolve_source_path(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('invalid manifest path')
    relative_path = Path(relative)
    if relative_path.is_absolute() or '..' in relative_path.parts:
        raise ValueError('manifest path escapes root')
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('manifest path escapes root')
    return path


def verify(root, *, include_paths=False):
    root = Path(root).resolve()
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    paths = {}
    for entry in manifest['files']:
        relative = entry['path']
        path = resolve_source_path(root, relative)
        if relative in paths:
            raise ValueError('duplicate manifest path')
        paths[relative] = (path, entry)

    actual, report = reconcile_inventory(root, include_paths=include_paths)
    if actual != paths.keys():
        raise ValueError('manifest inventory differs from source files')
    for relative, (path, entry) in paths.items():
        data = path.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('manifest mismatch: ' + relative)
    return {
        'verified_files': len(paths),
        'scope': 'BYTE_IDENTITY_AND_INVENTORY_ONLY',
        'reconciliation': report,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths', action='store_true', help='include relative paths and their roles')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(Path(__file__).resolve().parents[1], include_paths=args.paths)))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        sys.exit(2)
