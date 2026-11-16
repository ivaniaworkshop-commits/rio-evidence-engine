"""RÍO Hackatón R010 — historical gateway session adapter.

Never reads R003 cookies, never exchanges login credentials, never maps
merchant/owner identity to R003 SUPERADMIN. R008 commerce is DEMO/localStorage.
"""
from __future__ import annotations
from pathlib import Path
from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

_HACKATON = Path(__file__).resolve().parent / 'static' / 'unificada' / 'hackaton'


def register_hackaton_routes(app, accounts):
    """Register only audited compatibility endpoints on existing FastAPI app.

    accounts is the *same* AccountService bound to /v1/auth; it is not an
    independent login provider, and does not accept credentials from the R003
    namespace. All auth decisions are made by AccountService.session.
    """

    @app.get('/mercado-abierto', include_in_schema=False)
    @app.get('/hackaton', include_in_schema=False)
    async def hackaton_page(request: Request):
        await run_in_threadpool(accounts.session, request)
        return FileResponse(_HACKATON / 'production.html', media_type='text/html',
                            headers={'Cache-Control':'no-store'})

    @app.get('/api/auth/me', include_in_schema=False)
    async def hackaton_identity(request: Request):
        principal = await run_in_threadpool(accounts.session, request)
        csrf = await run_in_threadpool(accounts.session_csrf, request)
        # Never grant R003 admin permissions from an unrelated email or role.
        return {'user': {
                    'id': principal['id'], 'email': principal['email'],
                    'can_access_market': accounts.can_invite(principal),
                    'display_name': principal['email'], 'role': 'GATEWAY_ACCOUNT',
                    'active': True},
                'csrf_token': csrf,
                'permissions': ['account.manage'],
                'auth_source': 'RIO_GATEWAY_RIO_SID',
                'commercial_state': 'DATABASE_SHARED_CDMX',
                'payments': 'PEY_AND_DECLARED_CASH'}

    @app.post('/api/auth/logout', include_in_schema=False)
    async def hackaton_logout(request: Request, response: Response):
        # The historical service verifies both live session and CSRF.
        return await run_in_threadpool(accounts.logout, request, response)

    @app.api_route('/api/admin/{resource:path}',
                   methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'],
                   include_in_schema=False)
    async def hackaton_admin_boundary(resource: str, request: Request):
        await run_in_threadpool(accounts.session, request)
        raise HTTPException(status_code=403,
            detail='R003 administrative privileges are not mapped to gateway accounts')
