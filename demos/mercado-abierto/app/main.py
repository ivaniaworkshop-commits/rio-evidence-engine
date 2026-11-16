"""Vercel ASGI entrypoint. Incomplete hosted configuration fails closed."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rio_pey_codi.platform import create_platform


def _hosted():
    return os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') in ('preview', 'production')


def _unavailable():
    fallback = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @fallback.api_route('/', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    @fallback.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    def unavailable(request: Request):
        return JSONResponse({'status':'UNAVAILABLE', 'live_payments_enabled':False,
                             'bank_payment_confirmed':False}, status_code=503,
                            headers={'Cache-Control':'no-store', 'Retry-After':'300'})
    return fallback


def build_application():
    if not _hosted():
        return create_platform()
    try:
        return create_platform()
    except Exception:
        # Provider/DB configuration errors may contain secrets: never log or
        # return their text. A failed setup must not open any application route.
        return _unavailable()


app = build_application()
