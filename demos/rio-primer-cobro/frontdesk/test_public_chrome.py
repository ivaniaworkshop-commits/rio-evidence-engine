#!/usr/bin/env python3
"""R018: observe public app rendering in a fresh, unauthenticated Chromium profile."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from check_public_site import DEFAULT_URL, valid_base

def check(base_url=DEFAULT_URL, allow_local=False):
    base = valid_base(base_url, allow_local=allow_local)
    browser = next((p for candidate in
        (os.environ.get('CHROME_BIN'), 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser')
        if candidate and (p := shutil.which(candidate))), None)
    if not browser:
        raise RuntimeError('HEADLESS_BROWSER_NOT_AVAILABLE')
    data = []
    with tempfile.TemporaryDirectory(prefix='rio-r018-browser-') as profile:
        for path, required in (
            ('/', ('RÍO Primer Cobro', './app.html', 'github.com/ivaniaworkshop-commits/rio-evidence-engine')),
            ('/app.html', ('RÍO', 'add', 'start-sale')),
        ):
            url = base + path
            result = subprocess.run([
                browser, '--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
                '--disable-gpu', '--no-first-run', '--disable-background-networking',
                '--window-size=390,844', '--virtual-time-budget=3000',
                f'--user-data-dir={profile}', '--dump-dom', url,
            ], capture_output=True, text=True, timeout=65)
            dom = result.stdout
            failures = [token for token in required if token not in dom]
            if result.returncode != 0 or failures or '<html' not in dom.lower():
                raise RuntimeError(f'BROWSER_RENDER_FAILED path={path} returncode={result.returncode} missing={failures}')
            data.append({'path': path, 'rendered': True, 'dom_chars': len(dom),
                         'required_elements_present': len(required)})
    return {
        'schema': 'RIO_PUBLIC_CHROMIUM_R018_V1', 'result': 'PASS',
        'scope': 'HEADLESS_DESKTOP_CHROME_FRESH_PROFILE_EXTERNAL_WEBSITE',
        'cookies_from_user_session': 'NONE', 'authentication_headers': 'NOT_SENT',
        'click_flow': 'NOT_TESTED', 'android_physical': 'NOT_OBSERVED',
        'payment_backend': 'NONE', 'pages': data,
    }

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--base-url', default=DEFAULT_URL)
    p.add_argument('--allow-local', action='store_true')
    p.add_argument('--output', default=None)
    args = p.parse_args()
    try:
        report = check(args.base_url, allow_local=args.allow_local)
        s = json.dumps(report, ensure_ascii=False, indent=2)
        print(s)
        if args.output:
            Path(args.output).write_text(s + '\n', encoding='utf-8')
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
        print(json.dumps({'result': 'FAIL', 'error': str(e)}), file=sys.stderr)
        sys.exit(2)
