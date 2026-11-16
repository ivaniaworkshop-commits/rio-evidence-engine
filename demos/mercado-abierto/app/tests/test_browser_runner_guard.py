"""The browser integration test must never write to an unrelated local service."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT.parent / 'iniciar_unificada.py'
RUNNER = ROOT / 'tests' / 'browser_integracion.cjs'


def test_temporary_server_exposes_only_valid_test_marker():
    marker = '0123456789abcdef' * 2
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(LAUNCHER), '--port', str(port), '--test-marker', marker],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/__rio_test_{marker}', timeout=1) as response:
                    assert json.load(response) == {'marker': marker}
                break
            except (OSError, urllib.error.URLError):
                if process.poll() is not None:
                    pytest.fail('El servidor temporal terminó antes de responder')
                time.sleep(0.1)
        else:
            pytest.fail('El servidor temporal no respondió')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/public-status') as response:
            status = json.load(response)
        assert status['mode'] == 'DEMO'
        assert status['live_payments_enabled'] is False
    finally:
        process.terminate()
        process.wait(timeout=10)
    invalid = subprocess.run(
        [sys.executable, str(LAUNCHER), '--test-marker', 'invalido'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
    )
    assert invalid.returncode == 2


def test_browser_runner_does_not_write_to_an_occupied_port(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js no disponible')
    requests = []

    class OtherService(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(('GET', self.path))
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            requests.append(('POST', self.path))
            self.send_response(500)
            self.end_headers()

        def log_message(self, *_):
            pass

    server = HTTPServer(('127.0.0.1', 0), OtherService)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fake_playwright = tmp_path / 'playwright'
        fake_playwright.mkdir()
        (fake_playwright / 'index.js').write_text(
            'module.exports={chromium:{launch:()=>{throw Error("unexpected browser")}}};',
            encoding='utf-8',
        )
        env = dict(os.environ, NODE_PATH=str(tmp_path), RIO_DEMO_PYTHON=sys.executable,
                   RIO_DEMO_PORT=str(server.server_port))
        result = subprocess.run([node, str(RUNNER)], env=env, text=True,
                                capture_output=True, timeout=20)
        assert result.returncode != 0
        assert 'servidor de prueba' in result.stderr or 'puerto' in result.stderr
        assert all(method == 'GET' and path.startswith('/__rio_test_')
                   for method, path in requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
