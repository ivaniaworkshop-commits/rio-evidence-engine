"""Persistent, owner-only queue for operational facts that need evidence."""
from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import VerificationTask


DOMAINS = {'pey', 'casetas', 'tarifas', 'bancos', 'pagos', 'productos',
           'mensajeria', 'chatbot', 'logistica', 'legal', 'mercado', 'correo'}
STATUSES = {'PENDING', 'IN_PROGRESS', 'BLOCKED', 'VERIFIED'}
TASKS = (
    ('pey_merchant_accounts', 'pey', 'HIGH', 'Cuentas pey de cada negocio',
     'Confirmar en el portal y por lectura autenticada qué cuentas pertenecen a cada negocio y cuál es su estado operativo. No registrar llaves ni números de cuenta aquí.', 'Portal y documentación de pey', 'https://docs.pey.mx'),
    ('pey_webhook_contract', 'pey', 'HIGH', 'Contrato real de webhooks de pey',
     'Verificar firma, eventos, reintentos, orden, identificadores e idempotencia con la documentación vigente y un evento de prueba recibido.', 'Documentación de pey', 'https://docs.pey.mx'),
    ('pey_payment_confirmation', 'pagos', 'HIGH', 'Confirmación de pago contra pey',
     'Comprobar en un pago autorizado que el evento y la consulta de estado coinciden, sin tratar una solicitud emitida como pago confirmado.', 'Documentación de pey', 'https://docs.pey.mx'),
    ('bank_settlement_confirmation', 'bancos', 'HIGH', 'Abono bancario independiente',
     'Identificar una API o notificación bancaria autorizada y reconciliar un abono real con el pago CoDi. El webhook de pey por sí solo no acredita el abono.', 'Banco receptor por confirmar', None),
    ('beneficiary_account_ownership', 'bancos', 'HIGH', 'Titularidad y cuenta beneficiaria',
     'Validar con evidencia permitida quién es titular de cada cuenta de depósito y que la selección de cuenta se aplique al negocio correcto.', 'Banco receptor por confirmar', None),
    ('email_delivery_inbox', 'correo', 'NORMAL', 'Entrega de correo de verificación y comprobante',
     'Confirmar recepción en buzón real de registro, recuperación y comprobante; un SMTP aceptado no demuestra entrega al destinatario.', 'Prueba de extremo a extremo del buzón', None),
    ('receipt_qr_verification', 'pagos', 'HIGH', 'QR de comprobante verificable',
     'Verificar que cada QR emitido se resuelva en el endpoint público de comprobación y corresponda al pago confirmado, importe y comercio correctos.', 'Aplicación y flujo de pago autorizado', None),
    ('product_photo_rights', 'productos', 'NORMAL', 'Origen y derechos de fotos de producto',
     'Confirmar licencia, atribución y procedencia para imágenes aportadas, galería e imágenes buscadas en internet antes de publicarlas.', 'Proveedor de imágenes y revisión legal por definir', None),
    ('product_price_stock_source', 'productos', 'HIGH', 'Precio y disponibilidad del catálogo',
     'Comprobar que precio, unidad, existencia e identificador publicados provienen del negocio y se actualizan sin crear una confirmación de cobro.', 'Lectura del negocio y pruebas de catálogo', None),
    ('wholesale_public_profiles', 'mercado', 'NORMAL', 'Directorio y perfiles públicos mayoristas',
     'Validar consentimiento de publicación, datos comerciales, localidad y propagación de cada producto entre el mercado general y el perfil público.', 'Comercios participantes y revisión del mercado', None),
    ('market_order_qr_publication', 'mercado', 'HIGH', 'QR de pedido en todas las publicaciones',
     'Verificar que un pedido genere el mismo QR donde se publica el producto, que identifique solo el producto o checkout público y no revele datos privados del pedido.', 'Flujo de publicación del mercado y pruebas de privacidad', None),
    ('product_publication_payment_semantics', 'pagos', 'HIGH', 'Cobro al publicar producto',
     'Aclarar y validar el flujo de cobro asociado a una publicación. La publicación puede crear una solicitud de pago, pero nunca debe registrarse como pago confirmado sin confirmación verificable del proveedor.', 'Reglas de cobro y contrato de pey', 'https://docs.pey.mx'),
    ('market_catalog_profile_consistency', 'mercado', 'NORMAL', 'Catálogo general y perfiles de vendedor',
     'Comprobar que productos, precios, disponibilidad, fotos e identificadores sean iguales en el mercado general y en el perfil público del mismo negocio.', 'Pruebas de mercado y perfiles mayoristas', None),
    ('receiver_location_consent', 'logistica', 'HIGH', 'Ubicación en tiempo real del receptor',
     'Verificar consentimiento revocable, permisos, precisión, marca temporal, acceso por pedido y política de retención antes de compartir ubicación con fleteros.', 'Prueba de permisos y revisión de privacidad', None),
    ('fleet_locality_and_delivery_access', 'logistica', 'HIGH', 'Asignación de fleteros por localidad',
     'Verificar que la asignación use Ciudad de México, permisos del fletero, ubicación vigente y solo la información necesaria del pedido.', 'Pruebas de operación y privacidad', None),
    ('whatsapp_provider_onboarding', 'mensajeria', 'NORMAL', 'WhatsApp para responder a clientes',
     'Confirmar proveedor oficial, número aprobado, plantillas, consentimiento de contacto, límites y entrega real de mensajes.', 'Meta WhatsApp Business Platform', 'https://developers.facebook.com/docs/whatsapp/'),
    ('chatbot_account_and_order_status', 'chatbot', 'HIGH', 'Chatbot y estados privados en tiempo real',
     'Probar autenticación, autorización por titular del pedido, actualización de estados y respuestas sin filtrar información de otros negocios.', 'Pruebas de permisos y estados del servidor', None),
    ('chatgpt_supported_connection', 'chatbot', 'NORMAL', 'Conexión autenticada con ChatGPT',
     'Determinar y validar el mecanismo soportado para conectar el chatbot a los hilos autorizados de ChatGPT; no asumir acceso a conversaciones del usuario.', 'Documentación vigente de OpenAI', 'https://platform.openai.com/docs/'),
    ('codi_iave_authorization', 'casetas', 'HIGH', 'Autorización comercial para TAG y prepago IAVE',
     'Pendiente verificar si existe API, programa de reventa, autorización para recargas y condiciones comerciales. No hay integración ni derecho de venta acreditados.', 'Portal IAVE / CAPUFE', 'https://iave.capufe.gob.mx/'),
    ('tag_registration_and_qr_redemption', 'casetas', 'HIGH', 'Alta de TAG y canje de QR de caseta',
     'Verificar el proceso permitido de alta de TAG, recarga, emisión de prepago y canje del QR con el operador. Un QR de la app no equivale por sí solo a un pase o saldo oficial.', 'Portal IAVE / CAPUFE', 'https://iave.capufe.gob.mx/'),
    ('toll_plaza_identity_50_candidates', 'casetas', 'HIGH', 'Identidad de las 50 plazas candidatas',
     'La lista extraída es una selección preliminar de candidatas cercanas a Ciudad de México; cada plaza, ubicación, carretera, operador, sentido y carriles está pendiente de verificación con fuente oficial y comprobación de campo.', 'Lista preliminar R002; CAPUFE y operador vial por confirmar', 'https://www.gob.mx/capufe'),
    ('toll_tariffs_by_vehicle_route', 'tarifas', 'HIGH', 'Tarifas oficiales por ruta y vehículo',
     'Consultar y fechar tarifas vigentes por plaza, sentido, clase vehicular y combinación de ruta; cualquier precio preliminar queda fuera de venta hasta tener evidencia oficial.', 'CAPUFE / operador vial por confirmar', 'https://www.gob.mx/capufe'),
    ('toll_manual_qr_acceptance', 'casetas', 'HIGH', 'Aceptación del QR en operación manual',
     'Confirmar con cada operador si el personal puede escanear un QR de prepago, qué sistema valida el saldo y qué procedimiento resuelve rechazos.', 'Operador de cada plaza por confirmar', None),
    ('toll_barrier_automation_safety', 'legal', 'HIGH', 'Autorización y seguridad de pluma automática',
     'La apertura automática de una pluma requiere integración y autorización del operador, normas de seguridad, mecanismo de emergencia y pruebas en entorno autorizado. Mantener solo simulación hasta verificarlas.', 'Operador vial y autoridad por confirmar', None),
    ('cdmx_locality_coverage', 'mercado', 'NORMAL', 'Cobertura de localidades de Ciudad de México',
     'Verificar catálogo oficial de alcaldías y localidades, normalización de direcciones y separación de comerciantes y fleteros en los flujos activos.', 'INEGI / catálogo territorial oficial', 'https://www.inegi.org.mx/'),
)

# Extracted from R002's RNC 2025 source-derived ranking. The 50 entries are
# individual *candidates*, not 50 confirmed physical toll plazas. Keep each
# pending until an operator/source and field check establish identity.
RNC_TOLL_CANDIDATES = (
    (1, '1254', 'Conscripto Poniente'), (2, '1309', 'CDI Oriente'),
    (3, '1304', 'Conscripto Oriente'), (4, '1445', 'VB Oriente'),
    (5, '1793', 'Río Remedios (D/E)'), (6, '1313', 'Entronque Autopista Urbana Norte'),
    (7, '1314', 'VB Poniente'), (8, '1308', 'CDI Poniente'),
    (9, '1886', 'Río de los Remedios'), (10, '1230', 'Vallejo'),
    (11, '1816', 'Río Remedios (A)'), (12, '1817', 'Río Remedios (TNS)'),
    (13, '1301', 'Periférico - Toreo'), (14, '1888', 'Río de los Remedios'),
    (15, '1234', 'Cien Metros'), (16, '1240', 'Puente de Vigas'),
    (17, '1249', 'Río San Joaquín'), (18, '1300', 'San Joaquín'),
    (19, '1560', 'México - Pachuca'), (20, '1310', 'Ejército Nacional Poniente'),
    (21, '1231', 'Ceylan'), (22, '1256', 'Ejército Nacional Oriente'),
    (23, '1795', 'Río Remedios (TSN)'), (24, '1235', 'Cien Metros'),
    (25, '1628', 'Dr. Gustavo Baz'), (26, '1124', 'Gustavo Baz'),
    (27, '1631', '1o. de Mayo'), (28, '1097', 'Gustavo Baz'),
    (29, '619', 'La Venta 2'), (30, '1156', 'Palmas Poniente'),
    (31, '1796', 'Alfredo del Mazo (A)'), (32, '1814', 'Alfredo del Mazo (D)'),
    (33, '965', 'La Venta'), (34, '621', 'La Venta'),
    (35, '617', 'Interlomas'), (36, '1157', 'Reforma Centro Poniente'),
    (37, '600', 'Peñón'), (38, '1799', 'Alfredo del Mazo (E)'),
    (39, '1813', 'Alfredo del Mazo (C)'), (40, '623', 'Contadero'),
    (41, '1155', 'Parque Pelvoux Poniente'), (42, '1115', 'Parque Naucalli'),
    (43, '1116', 'Lomas Verdes'), (44, '1303', 'Campo Marte Oriente'),
    (45, '1159', 'Rosario Castellanos Poniente'), (46, '1114', 'Circunvalación'),
    (47, '624', 'Santa Fe'), (48, '845', 'Santa Fe'),
    (49, '1149', 'Reforma Centro Oriente (Chapultepec)'), (50, '1118', 'Santa Mónica'),
)
RNC_SOURCE_URL = 'https://rnc.imt.mx/recursos/ShapeFiles/Plaza_cobro_shapefiles2025.zip'


def _seed_catalog():
    rows = list(TASKS)
    for rank, record_id, plaza_name in RNC_TOLL_CANDIDATES:
        key = f'rnc25_plaza_{rank:02d}_{record_id}'
        title = f'Verificar candidata {rank:02d}: {plaza_name}'
        description = (f'RNC 2025, registro {record_id}; candidata #{rank} de la selección geográfica R002. '
                       'Verificar identidad física, ubicación, carretera, operador, sentido y carriles con fuente oficial y campo. '
                       'La fuente y agrupación son analíticas y no prueban una plaza física única. Mantener fuera de venta hasta verificar.')
        source_label = f'IMT/INEGI · Red Nacional de Caminos 2025 · candidata #{rank}'
        rows.append((key, 'casetas', 'HIGH', title, description, source_label, RNC_SOURCE_URL))
    return tuple(rows)


def _stable_id(key: str) -> str:
    return hashlib.sha256(('verification-task:' + key).encode()).hexdigest()[:32]


def _safe_text(value: str) -> bool:
    # Keep these records free of direct contact data, account numbers and credentials.
    lowered = value.casefold()
    if re.search(r'\b[^\s@]+@[^\s@]+\.[a-z]{2,}\b', value, re.I):
        return False
    if re.search(r'(?<!\d)(?:\d[ -]?){16,20}(?!\d)', value):
        return False
    if re.search(r'\b(password|contraseñ|api[_ -]?key|secret|token|clabe|credential|bearer)\s*[:=]', lowered):
        return False
    return True


def _valid_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use una URL pública HTTPS sin credenciales.')
    if parsed.query or parsed.fragment:
        raise ValueError('La fuente no puede incluir parámetros ni fragmentos.')
    return value


class CreateTask(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    task_key: str = Field(min_length=3, max_length=64, pattern=r'^[a-z0-9]+(?:_[a-z0-9]+)*$')
    domain: str = Field(min_length=2, max_length=24)
    priority: str = Field(pattern=r'^(HIGH|NORMAL)$')
    title: str = Field(min_length=4, max_length=140)
    description: str = Field(min_length=8, max_length=1000)
    source_label: str = Field(min_length=2, max_length=120)
    source_url: str | None = Field(default=None, max_length=300)

    @field_validator('source_url')
    @classmethod
    def validate_url(cls, value):
        return _valid_url(value)


class UpdateTask(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=1)
    status: str = Field(pattern=r'^(PENDING|IN_PROGRESS|BLOCKED|VERIFIED)$')
    evidence_reference: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=500)


def _ensure_seeded(factory):
    with factory() as db:
        dialect = db.get_bind().dialect.name
        values = []
        now = int(time.time())
        for key, domain, priority, title, description, source_label, source_url in _seed_catalog():
            values.append({'id': _stable_id(key), 'task_key': key, 'domain': domain,
                           'priority': priority, 'title': title, 'description': description,
                           'source_label': source_label, 'source_url': source_url,
                           'status': 'PENDING', 'created_at': now, 'updated_at': now,
                           'revision': 1})
        if dialect == 'sqlite':
            statement = sqlite_insert(VerificationTask).values(values).on_conflict_do_nothing(index_elements=['task_key'])
        elif dialect == 'postgresql':
            statement = pg_insert(VerificationTask).values(values).on_conflict_do_nothing(index_elements=['task_key'])
        else:
            # Other database engines are not production-supported; retain an
            # idempotent read/insert fallback for local developer environments.
            statement = None
        with db.begin_nested():
            if statement is not None:
                db.execute(statement)
            else:
                for value in values:
                    if not db.scalar(select(VerificationTask.id).where(VerificationTask.task_key == value['task_key'])):
                        db.add(VerificationTask(**value))
        db.commit()


def _view(row):
    return {'id': row.id, 'task_key': row.task_key, 'domain': row.domain,
            'priority': row.priority, 'title': row.title, 'description': row.description,
            'source_label': row.source_label, 'source_url': row.source_url,
            'status': row.status, 'evidence_reference': row.evidence_reference,
            'note': row.note, 'created_at': row.created_at, 'updated_at': row.updated_at,
            'verified_at': row.verified_at, 'revision': row.revision}


def register_verification_tasks(app, accounts):
    factory = accounts.Session

    def owner(request, csrf=False):
        principal = accounts.session(request, csrf=csrf)
        if not accounts.can_invite(principal):
            raise HTTPException(403, 'Solo la cuenta titular puede administrar verificaciones')
        return principal

    @app.get('/v1/admin/verification-tasks')
    def list_tasks(request: Request, domain: str | None = None,
                   status: str | None = None):
        owner(request)
        if domain is not None and domain not in DOMAINS:
            raise HTTPException(422, 'Dominio inválido')
        if status is not None and status not in STATUSES:
            raise HTTPException(422, 'Estado inválido')
        try:
            _ensure_seeded(factory)
            with factory() as db:
                query = select(VerificationTask)
                if domain:
                    query = query.where(VerificationTask.domain == domain)
                if status:
                    query = query.where(VerificationTask.status == status)
                rows = list(db.scalars(query.order_by(VerificationTask.priority.desc(),
                                                       VerificationTask.domain,
                                                       VerificationTask.title)))
                counts = dict(db.query(VerificationTask.status, func.count()).group_by(VerificationTask.status).all())
                return {'tasks': [_view(row) for row in rows],
                        'counts': {key.lower(): counts.get(key, 0) for key in STATUSES}}
        except SQLAlchemyError:
            raise HTTPException(503, 'La cola de verificaciones no está disponible') from None

    @app.post('/v1/admin/verification-tasks', status_code=201)
    def create_task(request: Request, body: CreateTask):
        principal = owner(request, csrf=True)
        if body.domain not in DOMAINS:
            raise HTTPException(422, 'Dominio inválido')
        if not all(_safe_text(value) for value in (body.task_key, body.title, body.description,
                                                    body.source_label, body.source_url or '')):
            raise HTTPException(422, 'No incluyas datos personales, bancarios ni secretos en esta cola')
        now = int(time.time())
        row = VerificationTask(id=_stable_id(body.task_key), task_key=body.task_key,
            domain=body.domain, priority=body.priority, title=body.title,
            description=body.description, source_label=body.source_label,
            source_url=body.source_url, status='PENDING', created_at=now,
            updated_at=now, updated_by=principal['id'], revision=1)
        try:
            with factory.begin() as db:
                db.add(row)
                db.flush()
        except IntegrityError:
            raise HTTPException(409, 'La tarea ya existe') from None
        accounts.activity.record('VERIFY_TASK_CREATED', reference=row.id, detail_code='TASK_CREATED')
        return {'task': _view(row)}

    @app.patch('/v1/admin/verification-tasks/{task_id}')
    def update_task(task_id: str, request: Request, body: UpdateTask):
        principal = owner(request, csrf=True)
        if not re.fullmatch(r'[0-9a-f]{32}', task_id):
            raise HTTPException(404, 'Tarea no encontrada')
        reference = (body.evidence_reference or '').strip() or None
        note = (body.note or '').strip() or None
        if any(not _safe_text(value) for value in (reference, note) if value):
            raise HTTPException(422, 'No incluyas datos personales, bancarios ni secretos en la evidencia')
        if body.status == 'VERIFIED' and (not reference or not note):
            raise HTTPException(422, 'Para verificar una tarea agrega referencia de evidencia y nota')
        if reference and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/#-]{1,159}', reference):
            raise HTTPException(422, 'La referencia debe ser un folio o URL pública sin datos sensibles')
        if reference and reference.startswith('http'):
            try:
                _valid_url(reference)
            except ValueError:
                raise HTTPException(422, 'La referencia URL debe ser pública, HTTPS y sin parámetros') from None
        now = int(time.time())
        try:
            with factory.begin() as db:
                query = select(VerificationTask).where(VerificationTask.id == task_id).with_for_update()
                row = db.scalar(query)
                if row is None:
                    raise HTTPException(404, 'Tarea no encontrada')
                if body.revision != row.revision:
                    raise HTTPException(409, 'La tarea cambió; vuelve a cargarla')
                row.status = body.status
                row.evidence_reference = reference
                row.note = note
                row.updated_at = now
                row.updated_by = principal['id']
                row.verified_at = now if body.status == 'VERIFIED' else None
                row.verified_by = principal['id'] if body.status == 'VERIFIED' else None
                row.revision += 1
                result = _view(row)
        except SQLAlchemyError:
            raise HTTPException(503, 'No se pudo guardar la verificación') from None
        accounts.activity.record('VERIFY_TASK_UPDATED', reference=task_id,
                                 detail_code='TASK_' + body.status)
        return {'task': result}
