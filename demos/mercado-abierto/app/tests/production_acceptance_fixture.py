"""Loopback-only acceptance fixture for production marketplace, cash and receipts.

Uses real AccountService/SQLite/API handlers and an in-memory verification outbox.
The receipt seed is synthetic test evidence, never a real provider/bank payment.
This launcher and its random-key endpoints are not deployment source files.
"""
import argparse
import base64
import os
from pathlib import Path
import time
import uuid

from fastapi import Header, HTTPException, Request
import uvicorn


def make_app(database: Path, key: str, port: int):
    if len(key) < 32:
        raise ValueError('A random acceptance-fixture key is required')
    # Register separate normalized tables before auto_create, even while the
    # production root wiring is being integrated in another work stream.
    from rio_pey_codi import production_market_models, cash_ledger_models  # noqa: F401
    from rio_pey_codi.platform import Settings, create_platform
    from rio_pey_codi.models import Intent, MerchantPeyCredential, PaymentReceipt

    class NoNetworkProvider:
        calls = 0

        def create_qr(self, **_kwargs):
            self.calls += 1
            raise AssertionError('Acceptance test cannot create payment requests')

    provider = NoNetworkProvider()
    app = create_platform(Settings(
        env='local', mode='DEMO', live_enabled=False, auto_create=True,
        database_url='sqlite+pysqlite:///' + str(database), email_mode='memory',
        public_url=f'http://127.0.0.1:{port}', origin=f'http://127.0.0.1:{port}',
    ), provider=provider)
    paths = {getattr(route, 'path', '') for route in app.routes}
    if '/v1/market/bootstrap' not in paths:
        from rio_pey_codi.production_market import register_production_market_routes
        register_production_market_routes(app, app.state.accounts)
    if '/v1/merchants/{merchant_id}/cash-sales' not in paths:
        from rio_pey_codi.cash_ledger import register_cash_ledger_routes
        register_cash_ledger_routes(app, app.state.accounts)
    if '/v1/receipts/verify' not in paths:
        from rio_pey_codi.receipt_verification import register_receipt_verification
        register_receipt_verification(app, app.state.accounts, app.state.receipts)

    def boundary(value):
        if value != key:
            raise HTTPException(403, 'Synthetic fixture boundary')

    @app.get('/__production_test/metrics', include_in_schema=False)
    def metrics(x_production_fixture_key: str = Header(default='')):
        boundary(x_production_fixture_key)
        return {'provider_calls': provider.calls,
                'mail_kinds': [message['kind'] for message in app.state.mailer.outbox]}

    @app.get('/__production_test/verification-token', include_in_schema=False)
    def verification_token(email: str, x_production_fixture_key: str = Header(default='')):
        boundary(x_production_fixture_key)
        for message in reversed(app.state.mailer.outbox):
            if message['kind'] == 'verify' and message['email'] == email:
                return {'token': message['token']}
        raise HTTPException(404, 'No synthetic verification message')

    @app.post('/__production_test/receipt/{merchant_id}', include_in_schema=False)
    def seed_receipt(merchant_id: str, request: Request,
                     x_production_fixture_key: str = Header(default='')):
        boundary(x_production_fixture_key)
        principal = app.state.accounts.session(request, csrf=True)
        app.state.accounts.assert_member(principal['id'], merchant_id, {'owner'})
        stamp = int(time.time())
        ref, ident = uuid.uuid4().hex, uuid.uuid4().hex
        with app.state.accounts.Session.begin() as db:
            db.add(MerchantPeyCredential(ref=ref, merchant_id=merchant_id,
                api_key=b'isolated-acceptance-synthetic', webhook_secret=b'isolated-acceptance-synthetic',
                checked_at=stamp))
            db.flush()
            db.add(Intent(id=ident, merchant_id=merchant_id, order_id='acceptance-' + ident,
                amount_minor=1250, concept='Comprobante sintético de aceptación',
                numref=ident[:20], expiration_s=600, status='PROVIDER_REPORTED', created_at=stamp,
                provider_qr_id='acceptance-qr-' + ident, transaction_id='acceptance-tx-' + ident,
                pey_credential_ref=ref, provider_payment_source='PROVIDER_LOOKUP',
                provider_payment_observed_at=stamp, provider_payment_sha256='a' * 64))
            db.flush()
            receipt = PaymentReceipt(intent_id=ident, public_id=uuid.uuid4().hex,
                enabled=False, created_at=stamp, issued_at=stamp)
            db.add(receipt)
            db.flush()
            link = app.state.receipts.link(receipt)
        return {'link': link, 'amount_minor': 1250, 'synthetic': True}

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port < 65536:
        parser.error('Use a nonprivileged loopback TCP port')
    os.environ['RPG_MERCHANT_VAULT_KEY'] = base64.urlsafe_b64encode(b't' * 32).decode()
    app = make_app(args.db.resolve(), os.environ.get('PRODUCTION_ACCEPTANCE_KEY', ''), args.port)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning', access_log=False)
