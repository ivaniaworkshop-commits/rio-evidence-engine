"""Local transport checks; no requests to pey and no payment credentials."""
import io
from unittest.mock import patch

import pytest

from rio_pey_codi.pey import LivePeyGateway, ProviderError


def test_chunked_response_keeps_exact_body_and_size_limit():
    from rio_pey_codi.pey import _read_provider_body
    assert _read_provider_body(io.BytesIO(b'{"items":[]}'), 12, float('inf')) == b'{"items":[]}'
    with pytest.raises(ProviderError, match='size limit'):
        _read_provider_body(io.BytesIO(b'12345'), 4, float('inf'))


def test_body_stops_when_the_shared_deadline_expires():
    from rio_pey_codi.pey import _read_provider_body
    class SlowBody(io.BytesIO):
        def read1(self, size):
            return super().read(1)

    response = SlowBody(b'{"items":[]}')
    with patch('rio_pey_codi.pey.time.monotonic', side_effect=[0.0, 0.2, 0.2, 0.4]):
        with pytest.raises(ProviderError, match='deadline exceeded'):
            _read_provider_body(response, 256, 0.25)
    assert response.tell() == 2


def test_get_rejects_a_drip_fed_http_body_without_retry():
    # An in-process HTTP server reproduces urllib.read(N)'s inactivity behavior.
    import http.server
    import threading
    import time
    import urllib.request

    class SlowBody(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            body = b'{"items":[]}'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            for byte in body:
                try:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(0.04)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), SlowBody)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def local_open(_request, timeout):
        return urllib.request.urlopen('http://127.0.0.1:' + str(server.server_port), timeout=timeout)

    try:
        with patch('rio_pey_codi.pey._open_provider', side_effect=local_open) as transport:
            with pytest.raises(ProviderError, match='deadline exceeded'):
                LivePeyGateway(api_key='synthetic-unused', bank_account_id='')._get('/fixture', timeout=0.12)
            assert transport.call_count == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
