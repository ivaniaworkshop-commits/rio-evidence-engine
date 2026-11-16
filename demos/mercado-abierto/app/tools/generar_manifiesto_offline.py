#!/usr/bin/env python3
"""Regenera el inventario público que instala el service worker de práctica."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'rio_pey_codi' / 'static' / 'unificada'
ASSETS = [p for area in ('caja', 'mercado') for p in (ROOT / area).rglob('*')
          if p.is_file() and p.suffix in ('.css', '.js')]
ASSETS += [ROOT / n for n in ('shell.css', 'shell.js', 'puente.js', 'unificada.css', 'offline.js', 'offline-sw.js')]
digests = {'/static/unificada/' + p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(ASSETS)}
canonical = json.dumps(digests, sort_keys=True, separators=(',', ':')).encode()
version = hashlib.sha256(canonical).hexdigest()[:20]
payload = {'cache': 'rio-unificada-' + version, 'assets': digests}
out = 'globalThis.RioOfflineManifest=Object.freeze(' + json.dumps(payload, separators=(',', ':')) + ');\n'
(ROOT / 'offline-manifiesto.js').write_text(out, encoding='utf-8')
print('Offline manifest:', payload['cache'], 'assets:', len(digests))
