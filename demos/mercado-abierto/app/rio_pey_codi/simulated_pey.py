"""In-memory provider pages for LOCAL DEMO only; this module has no network client."""
from threading import Lock
from urllib.parse import parse_qsl, urlsplit

from .pey_transaction_review import MAX_RESPONSE, PageRequest, PageResponse, QR_ID


class SimulatedPeyPages:
    """Scenario installation is an in-process test hook, not an HTTP operation."""

    def __init__(self):
        self._pages = {}
        self._lock = Lock()

    def install(self, qr_id, pages):
        if (not isinstance(qr_id, str) or not QR_ID.fullmatch(qr_id)
                or type(pages) is not dict or not 1 <= len(pages) <= 10 or None not in pages):
            raise ValueError('Invalid simulation scenario')
        for token, response in pages.items():
            if (token is not None and (not isinstance(token, str) or not token or len(token) > 2048)):
                raise ValueError('Invalid simulation scenario')
            if (type(response) is not PageResponse or type(response.status) is not int
                    or type(response.body) is not bytes or len(response.body) > MAX_RESPONSE + 1):
                raise ValueError('Invalid simulation scenario')
        with self._lock:
            self._pages[qr_id] = dict(pages)

    def __call__(self, request):
        if type(request) is not PageRequest or request.method != 'GET':
            return PageResponse(400, b'{}')
        try:
            parts = urlsplit(request.path_and_query)
            prefix = '/transaction/codi/qr/'
            if parts.scheme or parts.netloc or parts.fragment or not parts.path.startswith(prefix):
                raise ValueError('Invalid path')
            qr_id = parts.path[len(prefix):]
            if not QR_ID.fullmatch(qr_id):
                raise ValueError('Invalid QR')
            query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
            if len(query) > 1 or (query and query[0][0] != 'nextToken'):
                raise ValueError('Invalid query')
            token = query[0][1] if query else None
        except (TypeError, ValueError):
            return PageResponse(400, b'{}')
        with self._lock:
            pages = self._pages.get(qr_id)
            if pages is None and token is None:
                return PageResponse(200, b'{"items":[],"nextToken":null}')
            if pages is None:
                return PageResponse(400, b'{}')
            return pages.get(token, PageResponse(400, b'{}'))
