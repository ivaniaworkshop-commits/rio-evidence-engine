"""Owner-only, persistent operational events. No payloads, credentials or bearer links."""
import base64
import json
import logging
import re
import time
import uuid
from fastapi import HTTPException, Query, Request
from sqlalchemy import select, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from .models import ActivityEvent

EVENTS = {
 'ACCOUNT_CREATED':('accounts','CREATED'), 'ACCOUNT_EXISTS':('accounts','EXISTS'),
 'VERIFICATION_REQUESTED':('verification','REQUESTED'),
 'VERIFICATION_ACCEPTED':('email','SMTP_ACCEPTED'), 'VERIFICATION_FAILED':('email','FAILED'),
 'EMAIL_VERIFIED':('verification','VERIFIED'), 'VERIFY_LINK_INVALID':('verification','REJECTED'),
 'LOGIN_ACCEPTED':('access','AUTHENTICATED'), 'LOGIN_REJECTED':('access','REJECTED'),
 'LOGIN_PENDING':('access','UNVERIFIED'), 'LOGOUT':('access','SIGNED_OUT'),
 'RESET_REQUESTED':('verification','REQUESTED'), 'RESET_ACCEPTED':('email','SMTP_ACCEPTED'),
 'RESET_FAILED':('email','FAILED'), 'PASSWORD_RESET':('access','COMPLETED'),
 'PEY_OPERATION_SAVED':('pey','SAVED'), 'PEY_OPERATION_CONFIRMED':('pey','CONFIRMED'),
 'PEY_OPERATION_UNCERTAIN':('pey','UNCERTAIN'), 'PEY_OPERATION_REJECTED':('pey','REJECTED'),
 'PEY_BANK_ACCOUNT_HIDDEN':('pey','HIDDEN_LOCAL'), 'PEY_BANK_ACCOUNT_RESTORED':('pey','RESTORED_LOCAL'),
 'PEY_SAVED':('pey','SAVED'), 'PEY_ACTIVATED':('pey','ACTIVE'), 'PEY_REMOVED':('pey','REMOVED'),
 'RECEIPT_ACCEPTED':('email','SMTP_ACCEPTED'), 'RECEIPT_UNCERTAIN':('email','UNCERTAIN'),
 'VERIFY_TASK_CREATED':('verification','CREATED'), 'VERIFY_TASK_UPDATED':('verification','UPDATED'),
 'BUSINESS_ARCHIVED':('accounts','REMOVED_FROM_PROFILE'), 'BUSINESS_RESTORED':('accounts','RESTORED_TO_PROFILE')}
CODES = {'SMTP_AUTH_REJECTED','SMTP_RECIPIENT_REJECTED','SMTP_MESSAGE_REJECTED','SMTP_TLS_FAILED',
         'SMTP_TIMEOUT','SMTP_UNAVAILABLE','VERIFICATION_REQUIRED','INVALID_CREDENTIALS',
         'TASK_CREATED','TASK_PENDING','TASK_IN_PROGRESS','TASK_BLOCKED','TASK_VERIFIED'}


class Activity:
    def __init__(self, factory):self.Session=factory

    def record(self, event_type, *, email=None, reference=None, detail_code=None):
        if event_type not in EVENTS:raise ValueError('Unknown activity event')
        category,outcome=EVENTS[event_type]
        # Only explicit fields are accepted: never a request, exception or provider body.
        row=ActivityEvent(id=uuid.uuid4().hex,occurred_at=int(time.time()),event_type=event_type,
            category=category,outcome=outcome,email=email[:254] if isinstance(email,str) else None,
            reference=reference if isinstance(reference,str) and re.fullmatch('[0-9a-f]{32}',reference) else None,
            detail_code=detail_code if detail_code in CODES else None,source='LIVE_EVENT')
        try:
            with self.Session.begin() as db:db.add(row)
            return True
        except SQLAlchemyError:
            # Auditing must not repeat a payment or undo an email already submitted.
            logging.getLogger(__name__).error('activity_persistence_unavailable')
            return False

    def register(self, app, accounts):
        @app.get('/v1/admin/activity')
        def events(request:Request, limit:int=Query(30,ge=1,le=100), before:str|None=None,
                   category:str|None=None):
            principal=accounts.session(request)
            if not accounts.can_invite(principal):raise HTTPException(403,'Solo el titular puede consultar la actividad')
            query=select(ActivityEvent)
            if category:
                if category not in {value[0] for value in EVENTS.values()}:raise HTTPException(422,'Categoría inválida')
                query=query.where(ActivityEvent.category==category)
            if before:
                try:
                    if len(before)>160:raise ValueError()
                    timestamp,ident=json.loads(base64.urlsafe_b64decode(before+'='*(-len(before)%4)))
                    if type(timestamp) is not int or not 0 <= timestamp <= 2**63-1 or not isinstance(ident,str) or not re.fullmatch('[0-9a-f]{32}',ident):raise ValueError()
                except (ValueError,TypeError,UnicodeError,json.JSONDecodeError):raise HTTPException(422,'Cursor inválido') from None
                query=query.where(or_(ActivityEvent.occurred_at<timestamp,
                    and_(ActivityEvent.occurred_at==timestamp,ActivityEvent.id<ident)))
            with self.Session() as db:
                rows=list(db.scalars(query.order_by(ActivityEvent.occurred_at.desc(),ActivityEvent.id.desc()).limit(limit+1)))
                more=len(rows)>limit;rows=rows[:limit]
                cursor=None
                if more:
                    last=rows[-1]
                    cursor=base64.urlsafe_b64encode(json.dumps([last.occurred_at,last.id]).encode()).decode().rstrip('=')
                return {'events':[{'id':r.id,'event_type':r.event_type,'category':r.category,'outcome':r.outcome,
                    'occurred_at':r.occurred_at,'email':r.email,'reference':r.reference,
                    'detail_code':r.detail_code,'source':r.source} for r in rows], 'next_cursor':cursor}
