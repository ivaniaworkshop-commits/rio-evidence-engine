"""Authenticated, read-only Spanish assistant for live account and order status.

The assistant answers from a fresh database snapshot on each request. It has no
write tools and never treats a pey event as independent bank settlement.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from starlette.concurrency import run_in_threadpool

from .models import (Intent, Merchant, Membership, MerchantPeySecret,
                     PaymentReceipt, ProviderAccountObservation, User)
from .production_market_models import MarketFreight, MarketOrder, MarketProfile, MarketQuote


ORDER_LABELS = {
    'REQUESTED': 'solicitado', 'ACCEPTED': 'aceptado', 'PREPARED': 'preparado',
    'SHIPPED': 'enviado', 'RECEIVED': 'recibido', 'REJECTED': 'rechazado',
    'CANCELLED': 'cancelado',
}
QUOTE_LABELS = {
    'REQUESTED': 'solicitada', 'QUOTED': 'cotizada', 'ACCEPTED': 'aceptada',
    'REJECTED': 'rechazada', 'CANCELLED': 'cancelada',
}
FREIGHT_LABELS = {'PROPOSED': 'propuesto', 'ACCEPTED': 'aceptado', 'DELIVERED': 'entrega declarada'}


def iso_time(value):
    if not value:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=500)


class StatusChatbot:
    def __init__(self, accounts, market):
        self.accounts = accounts
        self.market = market
        self.Session = accounts.Session

    def snapshot(self, principal, requested_order_id=None):
        try:
            with self.Session() as db:
                user = db.get(User, principal['id'])
                if user is None:
                    raise HTTPException(401, 'Inicia sesión para consultar tu estado')
                owned = db.execute(select(Merchant, Membership.role).join(
                    Membership, Membership.merchant_id == Merchant.id
                ).where(Membership.user_id == principal['id']).order_by(Merchant.name)).all()
                merchant_ids = [merchant.id for merchant, _role in owned]
                profiles = {row.merchant_id: row for row in db.scalars(
                    select(MarketProfile).where(MarketProfile.merchant_id.in_(merchant_ids))
                )} if merchant_ids else {}
                secrets = {row.merchant_id: row for row in db.scalars(
                    select(MerchantPeySecret).where(MerchantPeySecret.merchant_id.in_(merchant_ids))
                )} if merchant_ids else {}
                latest_observations = {}
                if merchant_ids:
                    observations = list(db.scalars(select(ProviderAccountObservation).where(
                        ProviderAccountObservation.merchant_id.in_(merchant_ids)
                    ).order_by(ProviderAccountObservation.sequence.desc())))
                    for observation in observations:
                        latest_observations.setdefault(observation.merchant_id, observation)

                if merchant_ids:
                    visible_order = or_(
                        MarketOrder.buyer_merchant_id.in_(merchant_ids),
                        MarketOrder.seller_merchant_id.in_(merchant_ids),
                        MarketOrder.id.in_(select(MarketFreight.order_id).where(
                            MarketFreight.carrier_merchant_id.in_(merchant_ids))),
                    )
                    order_query = select(MarketOrder).where(visible_order)
                    if requested_order_id:
                        order_query = order_query.where(MarketOrder.id == requested_order_id)
                    else:
                        order_query = order_query.order_by(MarketOrder.updated_at.desc(),
                            MarketOrder.id.desc()).limit(50)
                    orders = list(db.scalars(order_query))
                    quotes = list(db.scalars(select(MarketQuote).where(or_(
                        MarketQuote.buyer_merchant_id.in_(merchant_ids),
                        MarketQuote.seller_merchant_id.in_(merchant_ids)
                    )).order_by(MarketQuote.updated_at.desc(), MarketQuote.id.desc()).limit(20)))
                else:
                    orders, quotes = [], []

                order_ids = [row.id for row in orders]
                freights = list(db.scalars(select(MarketFreight).where(or_(
                    MarketFreight.order_id.in_(order_ids) if order_ids else False,
                    MarketFreight.carrier_merchant_id.in_(merchant_ids) if merchant_ids else False,
                )).order_by(MarketFreight.updated_at.desc(), MarketFreight.id.desc()).limit(50))) if (order_ids or merchant_ids) else []

                # Use the same payment evidence serializer as the authenticated
                # market API; it reports pey confirmation separately from bank settlement.
                db.info['market_freight_orders'] = {row.order_id: row for row in freights}
                if orders:
                    intents = list(db.scalars(select(Intent).where(
                        Intent.order_id.in_(['market-' + row.id for row in orders]),
                        Intent.merchant_id.in_({row.seller_merchant_id for row in orders}),
                    )))
                    db.info['market_payment_intents'] = {
                        (row.merchant_id, row.order_id): row for row in intents
                    }
                    db.info['market_objects'] = {}
                    for receipt in db.scalars(select(PaymentReceipt).where(
                            PaymentReceipt.intent_id.in_([row.id for row in intents]))):
                        db.info['market_objects'][(PaymentReceipt, receipt.intent_id)] = receipt

                business_status = []
                for merchant, role in owned:
                    profile = profiles.get(merchant.id)
                    secret = secrets.get(merchant.id)
                    observation = latest_observations.get(merchant.id)
                    business_status.append({
                        'id': merchant.id,
                        'name': merchant.name,
                        'role': role,
                        'profile_status': 'publicado' if profile and profile.published else
                            'guardado sin publicar' if profile else 'por configurar',
                        'alcaldia': profile.alcaldia if profile else None,
                        'pey_credential_status': 'llave verificada y guardada' if secret and secret.active_credential_ref else
                            'sin llave verificada guardada',
                        'pey_last_account_observation': observation.status if observation else None,
                        'pey_last_account_observation_at': iso_time(observation.created_at) if observation else None,
                    })

                freight_by_order = {row.order_id: row for row in freights}
                order_status = []
                for order in orders[:20]:
                    view = self.market.order_view(db, order)
                    freight = freight_by_order.get(order.id)
                    order_status.append({
                        'id': order.id,
                        'listing_name': order.listing_name,
                        'status': order.status,
                        'status_label': ORDER_LABELS.get(order.status, order.status.lower()),
                        'role': 'comprador' if order.buyer_merchant_id in merchant_ids else
                            'vendedor' if order.seller_merchant_id in merchant_ids else 'fletero',
                        'total_minor': order.total_minor if (order.buyer_merchant_id in merchant_ids or
                            order.seller_merchant_id in merchant_ids) else None,
                        'payment_status': view['payment']['status'] if (order.buyer_merchant_id in merchant_ids or
                            order.seller_merchant_id in merchant_ids) else 'NOT_SHARED',
                        'payment_label': view['payment']['label'] if (order.buyer_merchant_id in merchant_ids or
                            order.seller_merchant_id in merchant_ids) else 'Estado de pago privado para las partes del pedido',
                        'bank_payment_confirmed': False,
                        'freight_status': FREIGHT_LABELS.get(freight.status, freight.status.lower()) if freight else None,
                        'updated_at': iso_time(order.updated_at),
                    })
                quote_status = [{
                    'id': row.id, 'listing_name': row.listing_name, 'status': row.status,
                    'status_label': QUOTE_LABELS.get(row.status, row.status.lower()),
                    'role': 'comprador' if row.buyer_merchant_id in merchant_ids else 'vendedor',
                    'updated_at': iso_time(row.updated_at),
                } for row in quotes[:10]]

                return {
                    'account': {
                        'email_verified': user.verified_at is not None,
                        'registered_at': iso_time(user.created_at),
                        'business_count': len(business_status),
                    },
                    'businesses': business_status,
                    'orders': order_status,
                    'quotes': quote_status,
                    'freights': [{
                        'id': row.id, 'order_id': row.order_id,
                        'status': row.status,
                        'status_label': FREIGHT_LABELS.get(row.status, row.status.lower()),
                        'updated_at': iso_time(row.updated_at),
                    } for row in freights[:20]],
                    'snapshot_at': datetime.now(timezone.utc).isoformat(),
                    'source': 'DATABASE_CURRENT_READ',
                }
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, 'No pude consultar el estado actual. Intenta de nuevo en unos segundos') from None

    @staticmethod
    def reply(message, status):
        question = message.casefold()
        order_id_match = re.search(r'(?<![0-9a-f])(?:market[-\s]?)?([0-9a-f]{32})(?![0-9a-f])', question)
        if order_id_match:
            order_id = order_id_match.group(1)
            order = next((row for row in status['orders'] if row['id'] == order_id), None)
            if not order:
                return 'No encuentro ese folio entre los pedidos de tus negocios. Revisa el folio o abre Cotizaciones y pedidos; no puedo consultar registros de otros negocios.', status
            payment = order['payment_label']
            freight = f" El flete está {order['freight_status']}." if order['freight_status'] else ''
            return (f"El pedido «{order['listing_name']}» está {order['status_label']}. "
                    f"{payment}. La liquidación bancaria independiente sigue sin verificarse.{freight} "
                    f"Última actualización: {order['updated_at']} UTC."), status

        if any(word in question for word in ('pedido', 'orden', 'compra')):
            if not status['orders']:
                return 'No hay pedidos registrados para los negocios de tu perfil.', status
            lines = [f"{row['listing_name']}: {row['status_label']} · {row['payment_label']} · folio {row['id']}" for row in status['orders'][:5]]
            return 'Estado de tus pedidos más recientes: ' + '; '.join(lines) + '. Los pagos confirmados por pey no equivalen a liquidación bancaria.', status

        if any(word in question for word in ('flete', 'fletero', 'entrega', 'transport')):
            if not status['freights']:
                return 'No hay asignaciones de flete para tus negocios en este momento.', status
            return 'Estado de tus fletes: ' + '; '.join(
                f"pedido {row['order_id']}: {row['status_label']}" for row in status['freights'][:5]
            ) + '.', status

        if any(word in question for word in ('pey', 'codi', 'llave', 'clave', 'cobro', 'pago')):
            if not status['businesses']:
                return 'Tu cuenta no tiene negocios asignados todavía.', status
            lines = []
            for business in status['businesses'][:10]:
                pey = business['pey_credential_status']
                observation = business['pey_last_account_observation']
                observed = f"; última consulta de cuenta en pey: {observation}" if observation else ''
                lines.append(f"{business['name']}: {pey}{observed}")
            return 'Estado de conexión por negocio: ' + '; '.join(lines) + '. Una consulta guardada no garantiza que pey esté disponible ahora y el banco no se verifica aquí.', status

        if any(word in question for word in ('cuenta', 'perfil', 'verific', 'registro', 'negocio')):
            account = status['account']
            verified = 'correo verificado' if account['email_verified'] else 'correo pendiente de verificar'
            if not status['businesses']:
                return f"Tu cuenta está registrada con {verified} y todavía no tiene negocios asignados.", status
            lines = [f"{row['name']}: perfil {row['profile_status']}" for row in status['businesses'][:10]]
            return f"Tu cuenta tiene {verified} y {account['business_count']} negocio(s). " + '; '.join(lines) + '.', status

        account = status['account']
        active = sum(row['status'] not in ('RECEIVED', 'REJECTED', 'CANCELLED') for row in status['orders'])
        return (f"Consulté tu cuenta ahora: {'correo verificado' if account['email_verified'] else 'correo pendiente de verificar'}, "
                f"{account['business_count']} negocio(s), {active} pedido(s) en curso y {len(status['freights'])} flete(s). "
                "Pregunta por cuenta, pey/CoDi, pedidos, fletes o pega el folio de un pedido."), status


def register_status_chatbot(app, accounts):
    service = StatusChatbot(accounts, app.state.production_market)
    app.state.status_chatbot = service

    async def principal(request: Request):
        return await run_in_threadpool(accounts.session, request)

    @app.get('/v1/chatbot/status', include_in_schema=False)
    async def get_status(request: Request, response: Response):
        user = await principal(request)
        response.headers['Cache-Control'] = 'private, no-store, max-age=0'
        return await run_in_threadpool(service.snapshot, user)

    @app.post('/v1/chatbot/message', include_in_schema=False)
    async def send_message(payload: ChatMessage, request: Request, response: Response):
        user = await run_in_threadpool(accounts.session, request, True)
        match = re.search(r'(?<![0-9a-f])(?:market[-\s]?)?([0-9a-f]{32})(?![0-9a-f])', payload.message.casefold())
        status = await run_in_threadpool(service.snapshot, user, match.group(1) if match else None)
        reply, status = service.reply(payload.message, status)
        response.headers['Cache-Control'] = 'private, no-store, max-age=0'
        return {'reply': reply, **status}
