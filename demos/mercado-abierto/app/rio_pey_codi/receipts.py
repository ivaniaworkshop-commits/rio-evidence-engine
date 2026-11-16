"""Receipts attest authenticated pey readback, never independent bank settlement."""
import base64
import hashlib
import hmac
import json
import html
import re
import smtplib
import time
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
import ssl

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .merchant_pey_checkout import qr_png
from .merchant_pey_vault import master_key
from .activity import Activity
from .models import Intent, Merchant, User, PaymentReceipt, ReceiptDelivery

TITLE = 'Pago confirmado por pey'
DISCLAIMER = 'Confirmación del proveedor pey; liquidación bancaria no verificada independientemente. No es un comprobante fiscal.'


def eligible(intent):
    return bool(intent and intent.status == 'PROVIDER_REPORTED' and intent.pey_credential_ref
                and intent.transaction_id and intent.provider_payment_source
                and intent.provider_payment_sha256 and intent.provider_payment_observed_at)


def reserve_receipt(db, intent, enabled, payer_email):
    db.add(PaymentReceipt(intent_id=intent.id, public_id=uuid.uuid4().hex,
        payer_email=payer_email if enabled else None, enabled=enabled, created_at=int(time.time())))


class Receipts:
    def __init__(self, factory, mailer, public_url):
        self.Session, self.mailer = factory, mailer
        self.public_url = public_url.rstrip('/')

    @staticmethod
    def token(receipt):
        digest = hmac.new(master_key(), ('rio.receipt.v1:' + receipt.public_id).encode(), hashlib.sha256).digest()
        return receipt.public_id + '.' + base64.urlsafe_b64encode(digest).decode().rstrip('=')

    def link(self, receipt):
        return self.public_url + '/comprobante/' + self.token(receipt)

    def lookup(self, token):
        if not re.fullmatch(r'[0-9a-f]{32}\.[A-Za-z0-9_-]{43}', token):
            raise HTTPException(404, 'Comprobante no encontrado')
        with self.Session() as db:
            receipt = db.scalar(select(PaymentReceipt).where(PaymentReceipt.public_id == token.split('.')[0]))
            if not receipt or not hmac.compare_digest(self.token(receipt), token):
                raise HTTPException(404, 'Comprobante no encontrado')
            intent = db.get(Intent, receipt.intent_id)
            if receipt.issued_at is None or not eligible(intent):
                raise HTTPException(404, 'Pago no confirmado')
            merchant = db.get(Merchant, intent.merchant_id)
            return receipt, intent, merchant.name

    def issue(self, intent_id):
        """Idempotently record both recipients after provider evidence is committed."""
        with self.Session.begin() as db:
            intent = db.get(Intent, intent_id)
            receipt = db.get(PaymentReceipt, intent_id)
            if not receipt or not eligible(intent):
                return
            if receipt.issued_at is None:
                receipt.issued_at = int(time.time())
            if not receipt.enabled:
                return
            merchant = db.get(Merchant, intent.merchant_id)
            owner = db.get(User, merchant.owner_id)
            recipients = [('payer', receipt.payer_email, 'PENDING')]
            # An invited, unverified mailbox is not an authenticated destination.
            if owner:
                recipients.append(('receiver', owner.email, 'PENDING' if owner.verified_at is not None else 'UNVERIFIED'))
            insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
            for role, email, initial_state in recipients:
                if email:
                    db.execute(insert(ReceiptDelivery).values(receipt_id=intent_id,
                        recipient_role=role, recipient_email=email, state=initial_state).on_conflict_do_nothing())
                    if initial_state == 'PENDING':
                        db.execute(update(ReceiptDelivery).where(ReceiptDelivery.receipt_id == intent_id,
                            ReceiptDelivery.recipient_role == role, ReceiptDelivery.state == 'UNVERIFIED',
                            ReceiptDelivery.recipient_email == email).values(state='PENDING'))
        self.deliver(intent_id)

    def deliver(self, intent_id):
        # Claim before SMTP. Never blindly retry a timeout: the server may have accepted it.
        for role in ('payer', 'receiver'):
            with self.Session.begin() as db:
                claimed = db.execute(update(ReceiptDelivery).where(
                    ReceiptDelivery.receipt_id == intent_id, ReceiptDelivery.recipient_role == role,
                    ReceiptDelivery.state == 'PENDING').values(state='SENDING')).rowcount
                if not claimed:
                    continue
                row = db.get(ReceiptDelivery, (intent_id, role))
                receipt = db.get(PaymentReceipt, intent_id)
                intent = db.get(Intent, intent_id)
                merchant = db.get(Merchant, intent.merchant_id)
                if not eligible(intent):
                    row.state = 'CANCELLED'
                    continue
                email, name = row.recipient_email, merchant.name
            state = 'SENT'
            try:
                self.send(email, receipt, intent, name, role)
            except Exception:
                state = 'UNCERTAIN'
            with self.Session.begin() as db:
                row = db.get(ReceiptDelivery, (intent_id, role))
                row.state = state
                row.sent_at = int(time.time()) if state == 'SENT' else None
            Activity(self.Session).record('RECEIPT_ACCEPTED' if state=='SENT' else 'RECEIPT_UNCERTAIN',email=email,reference=intent_id)

    def amount_detail(self, intent):
        from .pey_operations_models import PeyOperation
        with self.Session() as db:
            operation = db.scalar(select(PeyOperation).where(PeyOperation.intent_id == intent.id))
        if not operation or operation.state != 'PAID':
            return ''
        items = json.loads(operation.result_json).get('transactions', [])
        if not items:
            return ''
        totals = {key: sum(x[key] for x in items) for key in ('amount_minor','base_minor','tip_minor','fee_minor')}
        if totals['base_minor'] != intent.amount_minor:
            return ''
        money = lambda n: f'{n//100}.{n%100:02d}'
        return 'Base: MXN '+money(totals['base_minor'])+' · Propina: MXN '+money(totals['tip_minor'])+' · Comisión al pagador: MXN '+money(totals['fee_minor'])+' · Total pagado: MXN '+money(totals['amount_minor'])

    def send(self, email, receipt, intent, name, role):
        link = self.link(receipt)
        amount = f'{intent.amount_minor // 100}.{intent.amount_minor % 100:02d}'
        text = f'{TITLE}\nComercio: {name}\nFolio: {intent.order_id}\nImporte: MXN {amount}\n\nVerifica el comprobante: {link}\n\n{DISCLAIMER}'
        detail = self.amount_detail(intent)
        if detail:
            text += '\n\n' + detail
        png = qr_png(link)
        cfg = self.mailer.cfg
        if cfg.mode == 'memory':
            self.mailer.outbox.append({'kind':'payment_receipt','email':email,'link':link,
                'role':role,'body':text,'qr_png':png})
            return
        if cfg.mode != 'smtp':
            raise smtplib.SMTPException('Correo no disponible')
        msg = EmailMessage()
        msg['Subject'] = TITLE + ' · Mercado Abierto'
        msg['From'], msg['To'] = cfg.sender, email
        msg['Message-ID'] = f'<receipt-{receipt.public_id}-{role}@rio.local>'
        msg.set_content(text)
        esc = html.escape
        msg.add_alternative(f'<h1>{TITLE}</h1><p>{esc(name)} · MXN {amount}</p><p>Folio: {esc(intent.order_id)}</p>'
            f'<p>{esc(detail)}</p><p><a href="{esc(link, quote=True)}">Verificar comprobante</a></p>'
            f'<img src="cid:receipt-qr" alt="QR para verificar el comprobante" width="250">'
            f'<p>{DISCLAIMER}</p>', subtype='html')
        msg.get_payload()[1].add_related(png,maintype='image',subtype='png',cid='<receipt-qr>',filename='comprobante-qr.png')
        ctx = ssl.create_default_context()
        transport = smtplib.SMTP_SSL if cfg.port == 465 else smtplib.SMTP
        kwargs = {'timeout':10}
        if cfg.port == 465:
            kwargs['context'] = ctx
        with transport(cfg.host, cfg.port, **kwargs) as smtp:
            if cfg.port != 465:
                smtp.ehlo(); smtp.starttls(context=ctx); smtp.ehlo()
            if cfg.username:
                smtp.login(cfg.username, cfg.password)
            refused=smtp.send_message(msg)
            if refused:raise smtplib.SMTPRecipientsRefused(refused)

    def register(self, app, accounts):
        @app.get('/comprobante/{token}', response_class=HTMLResponse)
        def public_receipt(token: str):
            receipt, intent, name = self.lookup(token)
            esc = html.escape
            amount = f'{intent.amount_minor // 100}.{intent.amount_minor % 100:02d}'
            date = datetime.fromtimestamp(intent.provider_payment_observed_at, timezone.utc).isoformat()
            return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + \
                '<meta name="robots" content="noindex,nofollow"><title>Comprobante Mercado Abierto</title><link rel="stylesheet" href="/static/style.css">' + \
                '<link rel="stylesheet" href="/static/workspace.css"></head><body class="auth-page"><main class="auth-shell"><article class="panel auth-panel">' + \
                f'<p class="eyebrow">COMPROBANTE VERIFICADO · Mercado Abierto</p><h1>{TITLE}</h1><p>{esc(name)}</p>' + \
                f'<p>Importe: MXN {amount}</p><p>{esc(self.amount_detail(intent))}</p><p>Folio: {esc(intent.order_id)}</p><p>Fecha de verificación (UTC): {date}</p>' + \
                f'<div class="qr"><img src="/comprobante/{token}/qr.png" alt="QR de verificación" width="250"></div><p>{DISCLAIMER}</p></article></main></body></html>'

        @app.get('/comprobante/{token}/qr.png')
        def public_qr(token: str):
            receipt, _, _ = self.lookup(token)
            return Response(qr_png(self.link(receipt)), media_type='image/png')

        @app.get('/v1/checkout/qr/{intent_id}/receipt')
        def receipt_status(intent_id: str, request: Request):
            principal = accounts.session(request)
            with self.Session() as db:
                intent = db.get(Intent, intent_id)
                if intent is None:
                    raise HTTPException(404, 'Solicitud no encontrada')
                accounts.assert_member(principal['id'], intent.merchant_id)
                receipt = db.get(PaymentReceipt, intent_id)
                if not receipt:
                    return {'enabled':False, 'issued':False}
                issued = receipt.issued_at is not None and eligible(intent)
                deliveries = db.scalars(select(ReceiptDelivery).where(ReceiptDelivery.receipt_id == intent_id)).all()
                return {'enabled':receipt.enabled, 'issued':issued, 'link':self.link(receipt) if issued else None,
                        'deliveries':{row.recipient_role:row.state for row in deliveries}}
