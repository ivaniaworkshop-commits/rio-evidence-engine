import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile, threading
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_public_site import probe, valid_base

INDEX = b'<!doctype html><html lang="es"><body><a href="./app.html">Comenzar</a></body></html>'
APP = b'<!doctype html><html lang="es"><body>QR NO PAGABLE</body></html>'

class Handler(BaseHTTPRequestHandler):
    status = 200
    app_data = APP
    def do_GET(self):
        data = self.app_data if self.path.startswith('/app.html') else INDEX
        self.send_response(self.status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args): return

class CheckPublicSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
    def setUp(self):
        Handler.status = 200
        Handler.app_data = APP
        self.tmp = tempfile.TemporaryDirectory()
        Path(self.tmp.name, 'index.html').write_bytes(INDEX)
        Path(self.tmp.name, 'app.html').write_bytes(APP)
    def tearDown(self): self.tmp.cleanup()
    def test_public_access(self):
        o = probe(self.base, mode='access', allow_local=True, attempts=1)
        self.assertEqual(o['result'], 'PASS')
        self.assertEqual(len(o['pages']), 2)
        self.assertEqual(o['browser_UI'], 'NOT_OBSERVED')
    def test_public_exact(self):
        o = probe(self.base, self.tmp.name, mode='exact', allow_local=True, attempts=1)
        self.assertTrue(all(x['matches_source'] is True for x in o['pages']))
    def test_mismatched_bytes_rejected(self):
        Handler.app_data = APP + b'changed'
        with self.assertRaisesRegex(ValueError, 'PUBLIC_BYTES_DIFFER'):
            probe(self.base, self.tmp.name, mode='exact', allow_local=True, attempts=1)
    def test_unauthorized_status_rejected(self):
        Handler.status = 401
        with self.assertRaisesRegex(ValueError, 'PUBLIC_READBACK_FAILED'):
            probe(self.base, self.tmp.name, mode='exact', allow_local=True, attempts=1)
    def test_no_plain_http_in_production(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'): valid_base(self.base)
    def test_unapproved_public_domain(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'): valid_base('https://example.com')
    def test_url_userinfo_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'):
            valid_base('https://user:secret@rio-primer-cobro-frontdesk.vercel.app')
    def test_url_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'):
            valid_base('https://rio-primer-cobro-frontdesk.vercel.app/private')
    def test_other_vercel_project_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'):
            valid_base('https://unrelated-project.vercel.app')
    def test_known_candidate_hostname_allowed(self):
        self.assertEqual(
            valid_base('https://rio-primer-cobro-frontdesk-o6k25ltke-ivaniaworkshop-6855.vercel.app/'),
            'https://rio-primer-cobro-frontdesk-o6k25ltke-ivaniaworkshop-6855.vercel.app')
    def test_newline_in_url_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'):
            valid_base('https://rio-primer-cobro-frontdesk.vercel.app/\\nattack')
    def test_public_port_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BAD_BASE_URL'):
            valid_base('https://rio-primer-cobro-frontdesk.vercel.app:443/')

if __name__ == '__main__': unittest.main()
