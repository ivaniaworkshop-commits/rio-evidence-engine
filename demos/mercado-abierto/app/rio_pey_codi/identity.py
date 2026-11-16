"""Account onboarding, owner-backed merchants, tokenized server-side sessions.

Only hashed bearer/session/one-time tokens are stored.  SMTP delivery is mandatory
outside isolated local tests. Never email passwords or secret keys.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import re
import secrets
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal
from email.message import EmailMessage
from urllib.parse import quote

from argon2 import PasswordHasher, exceptions as argon_exc
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, ValidationError, field_validator, model_validator
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from .activity import Activity
from .models import AuthLimit, Beneficiary, BeneficiaryClaim, Membership, MembershipChange, Merchant, OneTimeToken, SessionRow, User
from .owner_recovery_policy import eligible_later_account

HASHER=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2)

def sha(token):return hashlib.sha256(token.encode('utf-8')).hexdigest()
def uid():return uuid.uuid4().hex

def csrf_for_session(session_token):
    return hmac.new(session_token.encode('utf-8'), b'rio-csrf-v1', hashlib.sha256).hexdigest()

def now():return int(time.time())

def canonical(email):return email.strip().casefold()

class Signup(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr
    password:SecretStr
    business_name:str=Field(min_length=2,max_length=120)
    @field_validator('business_name')
    @classmethod
    def valid_business_name(cls, value):
        value=value.strip()
        if len(value)<2:raise ValueError('Business name must have at least two characters')
        return value
    @field_validator('password')
    @classmethod
    def password_policy(cls,v):
        p=v.get_secret_value()
        if not 12<=len(p)<=256 or len(p.encode())>1024:
            raise ValueError('Password length must be 12..256 characters')
        return v

class Login(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr
    password:SecretStr

class EmailOnly(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr

class TokenOnly(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=30,max_length=256)

class ResetConfirm(TokenOnly):
    password:SecretStr
    @field_validator('password')
    @classmethod
    def password_policy(cls,v):
        p=v.get_secret_value()
        if not 12<=len(p)<=256 or len(p.encode())>1024:
            raise ValueError('Password length must be 12..256 characters')
        return v

class NewMerchant(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=120)

class ConfirmMerchant(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm_name:str=Field(min_length=2,max_length=120)

class InviteMerchant(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr
    business_name:str=Field(min_length=2,max_length=120)

    @field_validator('business_name')
    @classmethod
    def valid_business_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError('El nombre del comercio debe tener al menos dos caracteres')
        return value

class MemberRole(EmailOnly):
    role: Literal['admin', 'cashier', 'reader']


class BeneficiaryClaimInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    claim: Literal['OWNER_REPORTED_VERIFIED', 'OWNER_WITHDREW_REPORT']
    provider_account_id: str | None = Field(default=None, pattern=r'^[0-7][0-9A-HJKMNP-TV-Z]{25}$')

    @model_validator(mode='after')
    def check_withdrawal(self):
        if self.claim == 'OWNER_WITHDREW_REPORT' and self.provider_account_id is not None:
            raise ValueError('A withdrawal cannot name an account')
        return self


def beneficiary_claim_view(row):
    return {'id':row.id, 'merchant_id':row.merchant_id, 'actor_id':row.actor_id,
            'sequence':row.sequence, 'claim':row.claim,
            'provider_account_id':row.provider_account_id, 'created_at':row.created_at}


def beneficiary_claim_flags():
    return {'provider_status_verified':False, 'bank_payment_confirmed':False,
            'live_payments_enabled':False}


async def read_beneficiary_claim(request):
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > 2048:
            raise HTTPException(413, 'Beneficiary claim too large')
        chunks.extend(chunk)
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        value = json.loads(bytes(chunks), object_pairs_hook=unique_pairs,
                           parse_constant=lambda _v: (_ for _ in ()).throw(ValueError('invalid constant')))
        return BeneficiaryClaimInput.model_validate(value)
    except (ValidationError, ValueError, TypeError, RecursionError):
        # Never echo rejected fields, which could contain credentials or bank data.
        raise HTTPException(422, 'Invalid beneficiary claim') from None


@dataclass(frozen=True)
class EmailConfig:
    mode:str='memory'  # memory ONLY for isolated tests/local development
    public_url:str='http://localhost:3000'
    host:str=''
    port:int=587
    username:str=''
    password:str=field(default='',repr=False)
    sender:str=''

class AuthFlowError(HTTPException):
    def __init__(self, status_code, detail, code, **flags):
        super().__init__(status_code, detail)
        self.code, self.flags = code, flags


def auth_result(operation):
    try:
        return operation()
    except AuthFlowError as error:
        return JSONResponse({'detail':error.detail, 'code':error.code, **error.flags},
                            status_code=error.status_code, headers={'Cache-Control':'no-store'})


def mail_failure_code(error):
    if isinstance(error, smtplib.SMTPAuthenticationError): return 'SMTP_AUTH_REJECTED'
    if isinstance(error, smtplib.SMTPRecipientsRefused): return 'SMTP_RECIPIENT_REJECTED'
    if isinstance(error, smtplib.SMTPDataError): return 'SMTP_MESSAGE_REJECTED'
    if isinstance(error, ssl.SSLError): return 'SMTP_TLS_FAILED'
    if isinstance(error, TimeoutError): return 'SMTP_TIMEOUT'
    return 'SMTP_UNAVAILABLE'


class Mailer:
    def __init__(self,config:EmailConfig):
        self.cfg=config
        self.outbox=[]
        if config.mode not in ('memory','smtp','disabled'):
            raise ValueError('Email delivery is disabled or unconfigured')
        if config.mode=='smtp':
            if not config.host or not config.sender or not config.public_url.startswith('https://'):
                raise ValueError('SMTP host, sender and HTTPS public URL required')

    def send(self,kind,email,token):
        if self.cfg.mode == 'disabled':
            raise smtplib.SMTPException('Email delivery is disabled')
        url=f'{self.cfg.public_url.rstrip("/")}/{"verify-email" if kind=="verify" else "reset-password"}#token={quote(token)}'
        subject='Verifica tu correo en Mercado Abierto' if kind=='verify' else 'Restablece tu acceso a Mercado Abierto'
        body=(f'{subject}\n\nTu cuenta de comercio en Pey / Mercado Abierto está pendiente de verificación.\n'
              f'Abre este enlace para confirmar tu correo (vence en 24 horas):\n{url}\n\n'
              'Al confirmar el correo, tu sesión se iniciará automáticamente y abrirás Mercado Abierto. No necesitas registrar el negocio otra vez.\n\n'
              'Si no solicitaste el registro, ignora este mensaje.\n') if kind=='verify' else f'{subject}\n\nAbre este enlace antes de su vencimiento:\n{url}\n\nSi no solicitaste el cambio, ignora este correo.\n'
        if self.cfg.mode=='memory':
            self.outbox.append({'kind':kind,'email':email,'token':token,'link':url})
            return
        msg=EmailMessage()
        msg['Subject']=subject
        msg['From']=self.cfg.sender
        msg['To']=email
        msg.set_content(body)
        ctx=ssl.create_default_context()
        if self.cfg.port==465:
            with smtplib.SMTP_SSL(self.cfg.host,self.cfg.port,timeout=10,context=ctx) as smtp:
                if self.cfg.username:smtp.login(self.cfg.username,self.cfg.password)
                refused=smtp.send_message(msg)
                if refused: raise smtplib.SMTPRecipientsRefused(refused)
        else:
            with smtplib.SMTP(self.cfg.host,self.cfg.port,timeout=10) as smtp:
                smtp.ehlo();smtp.starttls(context=ctx);smtp.ehlo()
                if self.cfg.username:smtp.login(self.cfg.username,self.cfg.password)
                refused=smtp.send_message(msg)
                if refused: raise smtplib.SMTPRecipientsRefused(refused)

class AccountService:
    def __init__(self,sessions,mailer,cookie_secure=False,cookie_name='rio_sid',platform_owner_id='',
                 self_signup_no_email=False):
        self.Session=sessions
        self.activity=Activity(sessions)
        self.mailer=mailer
        self.cookie_secure=cookie_secure
        self.cookie_name=cookie_name
        self.platform_owner_id=platform_owner_id
        self.self_signup_no_email=self_signup_no_email
        self.dummy=HASHER.hash('dummy-unique-padding-string')

    def can_invite(self, principal):
        owner = self.platform_owner_id
        identifier = principal.get('id')
        return bool(owner and isinstance(identifier, str) and hmac.compare_digest(owner, identifier))

    def require_email_delivery(self):
        if self.mailer.cfg.mode == 'disabled':
            raise HTTPException(503, 'Registro y recuperación por correo no disponibles temporalmente')

    @staticmethod
    def access_origin(db, user):
        if user is None:
            return None
        if user.verified_at is not None:
            return 'email_verified'
        invitation = db.scalar(select(OneTimeToken.purpose).where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose.in_(('owner_invitation', 'merchant_invite', 'self_signup')),
            OneTimeToken.used_at.is_not(None),
        ).limit(1))
        return invitation

    def _token(self,db,user_id,kind,ttl):
        token=secrets.token_urlsafe(32)
        db.add(OneTimeToken(token_hash=sha(token),user_id=user_id,purpose=kind,expires_at=now()+ttl))
        return token

    def limit(self, request, action, email):
        window = now() // 900
        client = request.client.host if request.client else 'unknown'
        # Use the transport address. Forwarded headers require a trusted proxy.
        limits = [(sha(f'{action}:ip:{client}'), 60), (sha(f'{action}:email:{canonical(str(email))}'), 7)]
        with self.Session.begin() as db:
            insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
            db.execute(delete(AuthLimit).where(AuthLimit.window < window - 1))
            for key, maximum in limits:
                stmt = insert(AuthLimit).values(key=key, window=window, attempts=1)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['key', 'window'],
                    set_={'attempts': AuthLimit.attempts + 1},
                    where=AuthLimit.attempts < maximum,
                ).returning(AuthLimit.attempts)
                if db.scalar(stmt) is None:
                    raise HTTPException(429, 'Demasiados intentos. Espera unos minutos y vuelve a intentarlo.')

    def signup(self,req:Signup):
        if not self.self_signup_no_email:
            self.require_email_delivery()
        requested_mail=str(req.email)
        mail=canonical(requested_mail)
        pwd=req.password.get_secret_value()
        t=now()
        with self.Session.begin() as db:
            if db.scalar(select(User.id).where(User.email==mail)):
                raise AuthFlowError(409,'Este correo ya tiene una cuenta. Inicia sesión, reenvía la verificación o recupera tu acceso.','ACCOUNT_EXISTS')
            if requested_mail.rsplit('@',1)[0] != mail.rsplit('@',1)[0]:
                raise HTTPException(422,'Esta dirección cambiaría al guardarse. Usa por ahora otro correo.')
            user_id=uid(); merchant_id=uid()
            db.add(User(id=user_id,email=mail,password_hash=HASHER.hash(pwd),created_at=t))
            try:
                db.flush()
            except IntegrityError:
                raise AuthFlowError(409,'Este correo ya tiene una cuenta. Inicia sesión, reenvía la verificación o recupera tu acceso.','ACCOUNT_EXISTS') from None
            db.add(Merchant(id=merchant_id,name=req.business_name.strip(),owner_id=user_id,created_at=t))
            db.flush()
            db.add(Membership(user_id=user_id,merchant_id=merchant_id,role='owner'))
            if self.self_signup_no_email:
                # This consumed, non-delivered token is an activation marker;
                # it does not assert that the mailbox is owned or verified.
                db.add(OneTimeToken(token_hash=sha(secrets.token_urlsafe(32)), user_id=user_id,
                                    purpose='self_signup', expires_at=t, used_at=t))
            else:
                token=self._token(db,user_id,'verify',24*3600)
        self.activity.record('ACCOUNT_CREATED',email=mail,reference=user_id)
        if self.self_signup_no_email:
            return {'status':'ACCOUNT_ACTIVE_UNVERIFIED_EMAIL', 'merchant_id':merchant_id,
                    'email_verified':False}
        self.activity.record('VERIFICATION_REQUESTED',email=mail,reference=user_id)
        try:
            self.mailer.send('verify',mail,token)
            self.activity.record('VERIFICATION_ACCEPTED',email=mail,reference=user_id)
        except (OSError,smtplib.SMTPException) as exc:
            self._verification_delivery_failed(token, exc, mail)
            raise AuthFlowError(503,'La cuenta quedó creada, pero no pudimos enviar el correo. Solicita el reenvío de verificación.',
                                'VERIFICATION_DELIVERY_UNAVAILABLE',account_created=True) from None
        return {'status':'VERIFICATION_REQUIRED','merchant_id':merchant_id}

    def _verification_delivery_failed(self, token, error, email=None):
        # Do not log SMTP exception text: it may contain addresses or provider payloads.
        logging.getLogger(__name__).warning('auth_verification_delivery_failed code=%s',mail_failure_code(error))
        self.activity.record('VERIFICATION_FAILED',email=email,detail_code=mail_failure_code(error))
        with self.Session.begin() as db:
            db.execute(update(OneTimeToken).where(OneTimeToken.token_hash==sha(token),
                OneTimeToken.purpose=='verify', OneTimeToken.used_at.is_(None)).values(expires_at=now()))

    def resend_verification(self,email):
        self.require_email_delivery()
        mail=canonical(str(email));token=None
        with self.Session.begin() as db:
            user=db.scalar(select(User).where(User.email==mail))
            if user and user.verified_at is None:
                token=self._token(db,user.id,'verify',24*3600)
        if token:
            self.activity.record('VERIFICATION_REQUESTED',email=mail)
            try:
                self.mailer.send('verify',mail,token)
                self.activity.record('VERIFICATION_ACCEPTED',email=mail)
            except (OSError,smtplib.SMTPException) as error:
                self._verification_delivery_failed(token, error, mail)
                raise AuthFlowError(503,'No pudimos enviar el correo de verificación. Vuelve a intentarlo más tarde.',
                                    'EMAIL_DELIVERY_UNAVAILABLE') from None
        return {'status':'IF_ELIGIBLE_EMAIL_SENT'}

    def verify(self,token,response=None,request=None):
        # Redeeming an issued link does not depend on SMTP availability.
        token_hash=sha(token); t=now()
        sid=None; csrf=None
        with self.Session.begin() as db:
            link=db.get(OneTimeToken,token_hash)
            if not link or link.purpose != 'verify' or link.expires_at <= t:
                raise HTTPException(400,'El enlace de verificación no es válido o venció. Solicita uno nuevo; si ya verificaste tu correo, inicia sesión.')
            user=db.scalar(select(User).where(User.id==link.user_id).with_for_update())
            if user is None:
                raise HTTPException(400,'El enlace de verificación no es válido.')
            claimed=db.execute(update(OneTimeToken).where(
                OneTimeToken.token_hash == token_hash, OneTimeToken.purpose == 'verify',
                OneTimeToken.used_at.is_(None), OneTimeToken.expires_at > t,
            ).values(used_at=t))
            if claimed.rowcount != 1:
                # A response may be lost after its cookie was set. Retry only
                # with an existing valid session for this exact verified user.
                current=request.cookies.get(self.cookie_name,'') if request else ''
                session=db.get(SessionRow,sha(current)) if current and len(current)<=256 else None
                if (session and session.user_id==user.id and not session.revoked_at
                        and session.expires_at>t and user.verified_at is not None):
                    return {'status':'EMAIL_VERIFIED','user_id':user.id,'csrf_token':csrf_for_session(current)}
                raise HTTPException(400,'Este enlace ya se utilizó. Inicia sesión con tu correo y contraseña.')
            user.verified_at=user.verified_at if user.verified_at is not None else t
            user_id=user.id; verified_email=user.email
            # Older resend links must never become additional login credentials.
            db.execute(update(OneTimeToken).where(
                OneTimeToken.user_id==user_id, OneTimeToken.purpose=='verify',
                OneTimeToken.used_at.is_(None),
            ).values(used_at=t))
            if response is not None:
                sid=secrets.token_urlsafe(32); csrf=csrf_for_session(sid)
                db.add(SessionRow(token_hash=sha(sid),csrf_hash=sha(csrf),user_id=user_id,
                                  created_at=t,expires_at=t+7*24*3600))
        self.activity.record('EMAIL_VERIFIED',email=verified_email,reference=user_id)
        if sid is not None:
            response.set_cookie(self.cookie_name,sid,max_age=7*24*3600,httponly=True,
                                secure=self.cookie_secure,samesite='lax',path='/')
        return {'status':'EMAIL_VERIFIED','user_id':user_id,**({'csrf_token':csrf} if csrf else {})}

    def login(self,req:Login,response:Response):
        email=canonical(str(req.email)); t=now()
        with self.Session.begin() as db:
            user=db.scalar(select(User).where(User.email==email).with_for_update())
            try:
                valid=HASHER.verify(user.password_hash if user else self.dummy,req.password.get_secret_value())
            except (argon_exc.VerifyMismatchError,argon_exc.VerificationError):
                valid=False
            if not user or not valid:
                raise HTTPException(401,'Invalid credentials')
            if self.access_origin(db, user) is None:
                raise AuthFlowError(403,'Verifica tu correo o activa tu invitación antes de iniciar sesión.','ACCOUNT_ACTIVATION_REQUIRED')
            sid=secrets.token_urlsafe(32);csrf=csrf_for_session(sid)
            db.add(SessionRow(token_hash=sha(sid),csrf_hash=sha(csrf),user_id=user.id,
                              created_at=t,expires_at=t+7*24*3600))
            user_id=user.id
        self.activity.record('LOGIN_ACCEPTED',email=email,reference=user_id)
        response.set_cookie(self.cookie_name,sid,max_age=7*24*3600,httponly=True,secure=self.cookie_secure,samesite='lax',path='/')
        return {'status':'AUTHENTICATED','user_id':user_id,'csrf_token':csrf}

    def session(self,request:Request,csrf=False):
        sid=request.cookies.get(self.cookie_name)
        if not sid or len(sid)>256:raise HTTPException(401,'Sign in required')
        with self.Session() as db:
            row=db.get(SessionRow,sha(sid))
            if not row or row.revoked_at or row.expires_at<=now():raise HTTPException(401,'Session expired')
            user=db.get(User,row.user_id)
            origin = self.access_origin(db, user)
            if origin is None:raise HTTPException(401,'Account unverified')
            if csrf:
                c=request.headers.get('x-csrf-token','')
                if not c or not secrets.compare_digest(row.csrf_hash,sha(c)):
                    raise HTTPException(403,'CSRF verification failed')
            return {'id':user.id,'email':user.email,'verified':user.verified_at is not None,
                    'access_origin':origin,'csrf_hash':row.csrf_hash,'session_hash':row.token_hash}

    def activate_owner_invitation(self, token, password):
        token_hash = sha(token)
        with self.Session.begin() as db:
            user_id = db.scalar(select(OneTimeToken.user_id).where(
                OneTimeToken.token_hash == token_hash,
                OneTimeToken.purpose.in_(('owner_invitation', 'merchant_invite')),
            ))
            user = db.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
            if user is None or self.access_origin(db, user) is not None:
                raise HTTPException(400, 'Invitación inválida, utilizada o vencida')
            t = now()
            claimed = db.scalar(update(OneTimeToken).where(
                OneTimeToken.token_hash == token_hash,
                OneTimeToken.user_id == user.id,
                OneTimeToken.purpose.in_(('owner_invitation', 'merchant_invite')),
                OneTimeToken.used_at.is_(None),
                OneTimeToken.expires_at > t,
            ).values(used_at=t).returning(OneTimeToken.user_id))
            if claimed is None:
                raise HTTPException(400, 'Invitación inválida, utilizada o vencida')
            user.password_hash = HASHER.hash(password)
            db.execute(update(SessionRow).where(
                SessionRow.user_id == user.id, SessionRow.revoked_at.is_(None),
            ).values(revoked_at=t))
        return {'status':'OWNER_ACCESS_ACTIVATED','email_verified':False}

    def invite_merchant(self, principal, req):
        if not self.can_invite(principal):
            raise HTTPException(403, 'Solo el titular de la plataforma puede crear invitaciones')
        requested_mail = str(req.email)
        mail = canonical(requested_mail)
        if requested_mail.rsplit('@',1)[0] != mail.rsplit('@',1)[0]:
            raise HTTPException(422, 'Esta dirección cambiaría al guardarse. Usa por ahora otro correo.')
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._session_access(db, principal, lock=True)
            user = db.scalar(select(User).where(User.email == mail).with_for_update())
            t = now()
            if user is None:
                user_id = uid()
                merchant_id = uid()
                db.add(User(id=user_id, email=mail,
                            password_hash=HASHER.hash(secrets.token_urlsafe(64)), created_at=t))
                try:
                    db.flush()
                except IntegrityError as exc:
                    raise HTTPException(409, 'No se pudo crear la cuenta; vuelve a intentarlo') from exc
                db.add(Merchant(id=merchant_id, name=req.business_name, owner_id=user_id, created_at=t))
                db.flush()
                db.add(Membership(user_id=user_id, merchant_id=merchant_id, role='owner'))
            else:
                user_id = user.id
                previous = db.scalar(select(OneTimeToken.token_hash).where(
                    OneTimeToken.user_id == user_id,
                    OneTimeToken.purpose == 'merchant_invite',
                ).limit(1))
                if self.access_origin(db, user) is not None or previous is None:
                    raise HTTPException(409, 'Esta cuenta ya existe o está activa')
                # Expire, do not mark as used: only activation grants access.
                db.execute(update(OneTimeToken).where(
                    OneTimeToken.user_id == user_id,
                    OneTimeToken.purpose == 'merchant_invite',
                    OneTimeToken.used_at.is_(None),
                ).values(expires_at=t))
            token = self._token(db, user_id, 'merchant_invite', 24*3600)
        return {'status':'INVITATION_CREATED',
                'invitation_url':f'{self.mailer.cfg.public_url.rstrip("/")}/#owner_invite={token}',
                'expires_in':24*3600, 'email_verified':False}

    def session_csrf(self,request:Request):
        info=self.session(request)
        token=csrf_for_session(request.cookies[self.cookie_name])
        with self.Session.begin() as db:
            row=db.get(SessionRow,info['session_hash'])
            if not row or row.revoked_at or row.expires_at<=now():raise HTTPException(401,'Session expired')
            # Upgrade preexisting sessions whose CSRF value was randomly generated.
            if row.csrf_hash != sha(token):
                row.csrf_hash=sha(token)
        return token

    def logout(self,request:Request,response:Response):
        user=self.session(request,csrf=True)
        with self.Session.begin() as db:
            row=db.get(SessionRow,user['session_hash'])
            if row:row.revoked_at=now()
        response.delete_cookie(self.cookie_name,path='/',secure=self.cookie_secure,httponly=True,samesite='lax')
        self.activity.record('LOGOUT',email=user['email'],reference=user['id'])
        return {'status':'SIGNED_OUT'}

    def admin_reset_link(self, principal, email):
        """Issue a short-lived one-use recovery URL; never choose the target's password.

        Authorization is the pinned, already authenticated owner identity, not
        an email string or a historical SUPERADMIN role. No SMTP required:
        the recipient must receive the link through a trusted private channel.
        """
        if not self.can_invite(principal):
            raise HTTPException(403, 'Owner authorization required')
        mail = canonical(str(email))
        with self.Session.begin() as db:
            # Recheck session and owner binding *inside* the write transaction.
            self._session_access(db, principal, lock=True)
            owner = db.get(User, self.platform_owner_id)
            target = db.scalar(select(User).where(User.email == mail).with_for_update())
            if not eligible_later_account(owner, target):
                raise HTTPException(404, 'Eligible account not found')
            # A recovery link grants password replacement to its holder.
            # Invalidate prior unused admin links before minting a fresh one.
            t = now()
            db.execute(update(OneTimeToken).where(
                OneTimeToken.user_id == target.id,
                OneTimeToken.purpose == 'admin_reset',
                OneTimeToken.used_at.is_(None),
            ).values(expires_at=t))
            token = self._token(db, target.id, 'admin_reset', 900)
        return {'status': 'ADMIN_RESET_LINK_CREATED', 'expires_in': 900,
                'account_email': mail,
                'reset_url': f'{self.mailer.cfg.public_url.rstrip("/")}/reset-password#token={token}'}

    def reset_request(self,email):
        self.require_email_delivery()
        mail=canonical(str(email));token=None
        with self.Session.begin() as db:
            user=db.scalar(select(User).where(User.email==mail))
            if user:token=self._token(db,user.id,'reset',1800)
        if token:
            self.activity.record('RESET_REQUESTED',email=mail)
            try:
                self.mailer.send('reset', mail, token)
                self.activity.record('RESET_ACCEPTED',email=mail)
            except (OSError, smtplib.SMTPException) as error:
                self.activity.record('RESET_FAILED',email=mail,detail_code=mail_failure_code(error))
                # An undelivered bearer must not stay usable. Do not reveal
                # whether the mailbox exists, even when delivery fails.
                with self.Session.begin() as db:
                    db.execute(update(OneTimeToken).where(
                        OneTimeToken.token_hash == sha(token),
                        OneTimeToken.purpose == 'reset',
                        OneTimeToken.used_at.is_(None),
                    ).values(expires_at=now()))
        return {'status':'IF_ELIGIBLE_EMAIL_SENT'}

    def reset_confirm(self,token,password):
        with self.Session.begin() as db:
            token_hash = sha(token)
            record = db.scalar(select(OneTimeToken).where(
                OneTimeToken.token_hash == token_hash).with_for_update())
            purpose = record.purpose if record is not None else None
            # Ordinary email recovery remains disabled without delivery;
            # the separate owner-issued one-time flow needs no SMTP.
            if purpose not in ('admin_reset', 'owner_recovery'):
                self.require_email_delivery()
            if purpose not in ('reset', 'admin_reset', 'owner_recovery'):
                raise HTTPException(400, 'Invalid or expired reset token')
            user = db.scalar(select(User).where(User.id == record.user_id).with_for_update())
            t = now()
            if user is None or record.used_at is not None or record.expires_at <= t:
                raise HTTPException(400, 'Invalid or expired reset token')
            if purpose == 'admin_reset':
                owner = db.get(User, self.platform_owner_id) if self.platform_owner_id else None
                if not eligible_later_account(owner, user):
                    raise HTTPException(400, 'Invalid or expired reset token')
            if purpose == 'owner_recovery':
                if not self.platform_owner_id or not hmac.compare_digest(user.id, self.platform_owner_id):
                    raise HTTPException(400, 'Invalid or expired reset token')
            claimed = db.execute(update(OneTimeToken).where(
                OneTimeToken.token_hash == token_hash,
                OneTimeToken.purpose == purpose,
                OneTimeToken.used_at.is_(None),
                OneTimeToken.expires_at > t,
            ).values(used_at=t))
            if claimed.rowcount != 1:
                raise HTTPException(400, 'Invalid or expired reset token')
            user.password_hash = HASHER.hash(password)
            db.execute(update(OneTimeToken).where(
                OneTimeToken.user_id == user.id,
                OneTimeToken.purpose.in_(('reset', 'admin_reset', 'owner_recovery', 'verify')),
                OneTimeToken.used_at.is_(None),
            ).values(used_at=t))
            db.execute(delete(SessionRow).where(SessionRow.user_id == user.id))
        self.activity.record('PASSWORD_RESET',email=user.email,reference=user.id)
        return {'status': 'PASSWORD_CHANGED_SESSIONS_REVOKED'}

    def merchants(self,user_id):
        with self.Session() as db:
            rows=db.execute(select(Merchant.id,Merchant.name,Membership.role).join(Membership,Merchant.id==Membership.merchant_id)
                         .where(Membership.user_id==user_id, Merchant.archived_at.is_(None))).all()
            return [{'id':r.id,'name':r.name,'role':r.role} for r in rows]

    def archived_merchants(self,user_id):
        with self.Session() as db:
            rows=db.execute(select(Merchant.id,Merchant.name,Membership.role,Merchant.archived_at)
                .join(Membership,Merchant.id==Membership.merchant_id)
                .where(Membership.user_id==user_id, Merchant.archived_at.is_not(None))).all()
            return [{'id':r.id,'name':r.name,'role':r.role,'archived_at':r.archived_at} for r in rows]

    def archive_merchant(self, principal, merchant_id, confirm_name):
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._session_access(db, principal, lock=True)
            merchant=db.get(Merchant, merchant_id, with_for_update=True)
            if merchant is None:
                raise HTTPException(404, 'Negocio no encontrado')
            self._member_role(db, principal['id'], merchant_id, {'owner'}, lock=True)
            if merchant.owner_id != principal['id']:
                raise HTTPException(403, 'Solo el titular puede retirar este negocio de su perfil')
            if confirm_name.strip() != merchant.name:
                raise HTTPException(422, 'El nombre de confirmación no coincide')
            if merchant.archived_at is None:
                merchant.archived_at=now()
        self.activity.record('BUSINESS_ARCHIVED', email=None, reference=merchant_id)
        return {'id':merchant_id,'status':'REMOVED_FROM_PROFILE','records_preserved':True}

    def restore_merchant(self, principal, merchant_id):
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._session_access(db, principal, lock=True)
            merchant=db.get(Merchant, merchant_id, with_for_update=True)
            if merchant is None:
                raise HTTPException(404, 'Negocio no encontrado')
            self._member_role(db, principal['id'], merchant_id, {'owner'}, lock=True)
            if merchant.owner_id != principal['id']:
                raise HTTPException(403, 'Solo el titular puede devolver este negocio a su perfil')
            merchant.archived_at=None
        self.activity.record('BUSINESS_RESTORED', email=None, reference=merchant_id)
        return {'id':merchant_id,'status':'RESTORED_TO_PROFILE','records_preserved':True}

    def create_merchant(self,principal,name):
        merchant_id=uid()
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._session_access(db, principal, lock=True)
            db.add(Merchant(id=merchant_id,name=name.strip(),owner_id=principal['id'],created_at=now()))
            db.flush()
            db.add(Membership(merchant_id=merchant_id,user_id=principal['id'],role='owner'))
        return {'id':merchant_id,'name':name.strip(),'role':'owner'}

    def assert_member(self,user_id,merchant_id,roles=None):
        with self.Session() as db:
            return self._member_role(db, user_id, merchant_id, roles)

    @staticmethod
    def _member_role(db, user_id, merchant_id, roles, *, lock=False):
        row = db.get(Membership, {'merchant_id':merchant_id,'user_id':user_id}, with_for_update=lock)
        if row is None:
            raise HTTPException(404, 'Merchant not found')
        if roles is not None and row.role not in roles:
            raise HTTPException(403, 'Merchant role cannot perform this operation')
        return row.role

    def authorize_checkout(self, db, principal, merchant_id):
        self._session_access(db, principal, lock=True)
        # Use the same merchant -> membership lock order as owner settings.
        if db.get(Merchant, merchant_id, with_for_update=True) is None:
            raise HTTPException(404, 'Merchant not found')
        self._member_role(db, principal['id'], merchant_id, {'owner', 'admin', 'cashier'}, lock=True)

    def request_beneficiary_onboarding(self, principal, merchant_id):
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._claim_access(db, principal, merchant_id, lock=True, conceal_non_owner=True)
            insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
            db.execute(insert(Beneficiary).values(
                merchant_id=merchant_id, consent_by=principal['id'], consent_at=now(), status='pending',
            ).on_conflict_do_nothing(index_elements=['merchant_id']))
            row = db.get(Beneficiary, merchant_id)
            return {'merchant_id': merchant_id, 'status': row.status, 'consent_at': row.consent_at}

    @staticmethod
    def _session_access(db, principal, *, lock):
        def locked(query):
            return query.with_for_update() if lock else query
        if (not isinstance(principal, dict) or not isinstance(principal.get('id'), str)
                or not isinstance(principal.get('session_hash'), str)):
            raise HTTPException(401, 'Session expired')
        session = db.scalar(locked(select(SessionRow).where(SessionRow.token_hash == principal['session_hash'])))
        if (session is None or session.user_id != principal['id'] or session.revoked_at is not None
                or session.expires_at <= now()):
            raise HTTPException(401, 'Session expired')
        csrf_hash = principal.get('csrf_hash')
        if (not isinstance(session.csrf_hash, str) or not isinstance(csrf_hash, str)
                or not re.fullmatch(r'[0-9a-f]{64}', session.csrf_hash)
                or not re.fullmatch(r'[0-9a-f]{64}', csrf_hash)
                or not hmac.compare_digest(session.csrf_hash, csrf_hash)):
            raise HTTPException(403, 'Session changed')
        user = db.scalar(locked(select(User).where(User.id == principal['id'])))
        if AccountService.access_origin(db, user) is None:
            raise HTTPException(401, 'Account unverified')

    @staticmethod
    def _claim_access(db, principal, merchant_id, *, lock, conceal_non_owner=False):
        def locked(query):
            return query.with_for_update() if lock else query
        AccountService._session_access(db, principal, lock=lock)
        merchant = db.scalar(locked(select(Merchant).where(Merchant.id == merchant_id)))
        membership = db.scalar(locked(select(Membership).where(
            Membership.merchant_id == merchant_id, Membership.user_id == principal['id'])))
        if merchant is None or membership is None:
            raise HTTPException(404, 'Merchant not found')
        if merchant.owner_id != principal['id']:
            raise HTTPException(404 if conceal_non_owner else 403, 'Merchant not found' if conceal_non_owner
                                else 'Only the merchant owner may manage beneficiary claims')
        if membership.role != 'owner':
            raise HTTPException(403, 'Only the merchant owner may manage beneficiary claims')

    def record_beneficiary_claim(self, principal, merchant_id, request_id, claim):
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._claim_access(db, principal, merchant_id, lock=True)
            prior = db.scalar(select(BeneficiaryClaim).where(
                BeneficiaryClaim.merchant_id == merchant_id, BeneficiaryClaim.request_id == request_id))
            if prior is not None:
                if prior.claim != claim.claim or prior.provider_account_id != claim.provider_account_id:
                    raise HTTPException(409, 'Request key already used with different data')
                return beneficiary_claim_view(prior)
            last = db.scalar(select(BeneficiaryClaim.sequence).where(
                BeneficiaryClaim.merchant_id == merchant_id).order_by(BeneficiaryClaim.sequence.desc()).limit(1)) or 0
            row = BeneficiaryClaim(id=uid(), merchant_id=merchant_id, actor_id=principal['id'],
                sequence=last + 1, request_id=request_id, claim=claim.claim,
                provider_account_id=claim.provider_account_id, created_at=now())
            db.add(row)
            db.flush()
            return beneficiary_claim_view(row)

    def read_beneficiary_claims(self, principal, merchant_id):
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._claim_access(db, principal, merchant_id, lock=True)
            rows = db.scalars(select(BeneficiaryClaim).where(BeneficiaryClaim.merchant_id == merchant_id)
                              .order_by(BeneficiaryClaim.sequence.desc()).limit(51)).all()
            return {'claims':[beneficiary_claim_view(row) for row in rows[:50]], 'truncated':len(rows) > 50}

    def set_role(self, principal, merchant_id, req):
        with self.Session.begin() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            self._claim_access(db, principal, merchant_id, lock=True, conceal_non_owner=True)
            actor_id = principal['id']
            target = db.scalar(select(User).where(User.email == canonical(str(req.email)), User.verified_at.is_not(None)))
            if target is None or target.id == actor_id:
                raise HTTPException(422, 'A different verified member is required')
            key = {'merchant_id': merchant_id, 'user_id': target.id}
            row = db.get(Membership, key)
            previous = row.role if row else None
            if previous == 'owner':
                raise HTTPException(409, 'Owner membership cannot be changed')
            if previous != req.role:
                if row:
                    row.role = req.role
                else:
                    db.add(Membership(**key, role=req.role))
                db.add(MembershipChange(id=uid(), **key, actor_id=actor_id, previous_role=previous,
                                        new_role=req.role, created_at=now()))
            return {'user_id': target.id, 'role': req.role}


def router_for(svc:AccountService):
    router=APIRouter(prefix='/v1')
    @router.post('/auth/signup',status_code=201)
    def signup(req:Signup,request:Request):
        if not svc.self_signup_no_email:
            svc.require_email_delivery()
        svc.limit(request,'signup',req.email)
        def create():
            try:return svc.signup(req)
            except AuthFlowError as error:
                if error.code=='ACCOUNT_EXISTS':svc.activity.record('ACCOUNT_EXISTS',email=canonical(str(req.email)))
                raise
        return auth_result(create)
    @router.post('/auth/verify-email')
    def verify(req:TokenOnly,response:Response,request:Request):
        try:return svc.verify(req.token,response,request)
        except HTTPException as error:
            if error.status_code==400:svc.activity.record('VERIFY_LINK_INVALID')
            raise
    @router.post('/auth/resend-verification')
    def resend(req:EmailOnly,request:Request):
        svc.require_email_delivery()
        svc.limit(request,'resend',req.email)
        return auth_result(lambda:svc.resend_verification(req.email))
    @router.post('/auth/login')
    def login(req:Login,response:Response,request:Request):
        svc.limit(request,'login',req.email)
        def sign_in():
            try:
                return svc.login(req,response)
            except AuthFlowError as error:
                if error.code == 'ACCOUNT_ACTIVATION_REQUIRED':
                    svc.activity.record('LOGIN_PENDING',email=canonical(str(req.email)))
                    # Password was checked; release its user lock before SMTP.
                    # Share the explicit resend limit so login cannot bypass it.
                    svc.limit(request,'resend',req.email)
                    svc.resend_verification(req.email)
                    error.flags['verification_requested'] = True
                raise
            except HTTPException as error:
                if error.status_code==401:svc.activity.record('LOGIN_REJECTED',email=canonical(str(req.email)),detail_code='INVALID_CREDENTIALS')
                raise
        return auth_result(sign_in)
    @router.post('/auth/activate-owner')
    def activate_owner(req:ResetConfirm):
        return svc.activate_owner_invitation(req.token, req.password.get_secret_value())
    @router.get('/auth/me')
    def me(request:Request):
        info=svc.session(request)
        token=svc.session_csrf(request)
        return {'id':info['id'],'email':info['email'],'verified':info['verified'],
                'access_origin':info['access_origin'],'csrf_token':token,'can_invite':svc.can_invite(info)}
    @router.post('/admin/invitations',status_code=201)
    def invite_merchant(req:InviteMerchant,request:Request):
        info=svc.session(request,csrf=True)
        if not svc.can_invite(info):
            raise HTTPException(403, 'Solo el titular de la plataforma puede crear invitaciones')
        svc.limit(request, 'invite', req.email)
        return svc.invite_merchant(info,req)
    @router.post('/admin/reset-links', status_code=201)
    def admin_reset_links(req: EmailOnly, request: Request):
        principal = svc.session(request, csrf=True)
        if not svc.can_invite(principal):
            raise HTTPException(403, 'Owner authorization required')
        svc.limit(request, 'admin-reset', req.email)
        return svc.admin_reset_link(principal, req.email)

    @router.post('/auth/logout')
    def logout(request:Request,response:Response):return svc.logout(request,response)
    @router.post('/auth/reset-request')
    def reset_request(req:EmailOnly,request:Request):
        svc.require_email_delivery()
        svc.limit(request,'reset',req.email)
        return svc.reset_request(req.email)
    @router.post('/auth/reset-confirm')
    def reset_confirm(req:ResetConfirm):return svc.reset_confirm(req.token,req.password.get_secret_value())
    @router.get('/merchants')
    def merchants(request:Request):return {'merchants':svc.merchants(svc.session(request)['id'])}
    @router.get('/merchants/archived')
    def archived_merchants(request:Request):return {'merchants':svc.archived_merchants(svc.session(request)['id'])}
    @router.post('/merchants',status_code=201)
    def add_merchant(req:NewMerchant,request:Request):
        info=svc.session(request,csrf=True)
        return svc.create_merchant(info,req.name)
    @router.post('/merchants/{merchant_id}/archive')
    def archive_merchant(merchant_id:str,req:ConfirmMerchant,request:Request):
        return svc.archive_merchant(svc.session(request,csrf=True),merchant_id,req.confirm_name)
    @router.post('/merchants/{merchant_id}/restore')
    def restore_merchant(merchant_id:str,request:Request):
        return svc.restore_merchant(svc.session(request,csrf=True),merchant_id)
    @router.put('/merchants/{merchant_id}/members')
    def set_role(merchant_id: str, req: MemberRole, request: Request):
        return svc.set_role(svc.session(request, csrf=True), merchant_id, req)

    @router.post('/merchants/{merchant_id}/beneficiary-onboarding')
    def beneficiary_onboarding(merchant_id: str, request: Request):
        return svc.request_beneficiary_onboarding(svc.session(request, csrf=True), merchant_id)

    @router.post('/merchants/{merchant_id}/beneficiary-claims', status_code=201)
    async def record_beneficiary_claim(merchant_id: str, request: Request):
        principal = await run_in_threadpool(svc.session, request, csrf=True)
        keys = request.headers.getlist('idempotency-key')
        if len(keys) != 1 or not re.fullmatch(r'[0-9a-f]{32}', keys[0]):
            raise HTTPException(422, 'A 32-character lowercase request key is required')
        claim = await read_beneficiary_claim(request)
        result = await run_in_threadpool(svc.record_beneficiary_claim, principal, merchant_id, keys[0], claim)
        return {'claim':result, **beneficiary_claim_flags()}

    @router.get('/merchants/{merchant_id}/beneficiary-claims')
    async def read_beneficiary_claims(merchant_id: str, request: Request):
        principal = await run_in_threadpool(svc.session, request)
        result = await run_in_threadpool(svc.read_beneficiary_claims, principal, merchant_id)
        return {**result, **beneficiary_claim_flags()}

    return router
