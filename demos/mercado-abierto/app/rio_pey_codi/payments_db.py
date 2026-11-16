"""Transactional payment-state repository for PostgreSQL and local SQLite.

Provider status is NOT settlement.  Caller controls external network sends.
"""
import hashlib
import hmac
import json
import re
import time
import uuid
from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from .models import (BeneficiaryClaim, Event, Intent, Membership, Merchant,
                     PendingEvent, ReconciliationReview, SessionRow, User)
from .account_consistency import account_consistency
from .reconciliation import compare_for_review, stored_provider_report
from .signatures import reverify_stored_events

class PaymentConflict(ValueError):
    pass


class ReferenceConflict(PaymentConflict):
    pass


class ReviewAccessError(ValueError):
    def __init__(self, status):
        self.status = status


class ReviewRequestConflict(ValueError):
    pass


class ReviewWriteError(ValueError):
    pass


def review_view(row):
    return {'id':row.id, 'intent_id':row.intent_id, 'actor_id':row.actor_id,
            'classification':row.classification, 'bank_record_count':row.bank_record_count,
            'provider_event_count':row.provider_event_count,
            'provider_event_count_capped':row.provider_event_count > 100,
            'event_ids_hashes_sha256':row.event_ids_hashes_sha256,
            'created_at':row.created_at, 'source':'USER_REPORTED_UNVERIFIED',
            'signature_assessment_at_review':row.signature_assessment or 'NOT_RECORDED',
            'account_assessment_at_review':row.account_assessment or 'NOT_RECORDED'}

def view(row):
    live = row.pey_credential_ref is not None
    observed_at = int(time.time())
    status = row.status
    if live and status == 'QR_REQUESTING' and observed_at >= row.created_at + 60:
        status = 'PROVIDER_UNCERTAIN'
    return {'id':row.id,'merchant_id':row.merchant_id,'order_id':row.order_id,
            'amount_minor':row.amount_minor,'numref':row.numref,'concept':row.concept,
            'expiration_s':row.expiration_s,'status':status,
            'qr_display':None if live else row.qr_display,'created_at':row.created_at,
            'mode':'LIVE' if live else 'DEMO',
            'provider_qr_id':row.provider_qr_id if live else None,
            'provider_transaction_id':row.transaction_id if live else None,
            'provider_payment_source':row.provider_payment_source,
            'provider_payment_observed_at':row.provider_payment_observed_at,
            'provider_payment_sha256':row.provider_payment_sha256,
            'qr_image_url':f'/v1/checkout/qr/{row.id}/image' if live and row.qr_display else None,
            'expires_at':row.created_at + row.expiration_s,
            'expired':observed_at >= row.created_at + row.expiration_s,
            'bank_payment_confirmed':False}

class PaymentRepository:
    def __init__(self,session_factory,webhook_secret='',webhook_key_ref='',webhook_previous_keys=(),
                 merchant_signing_keys=None):
        self.Session=session_factory
        self._webhook_secret=webhook_secret
        self._webhook_key_ref=webhook_key_ref
        self._webhook_previous_keys=webhook_previous_keys
        self._merchant_signing_keys=merchant_signing_keys

    @staticmethod
    def _latest_claim(db, merchant_id):
        return db.scalar(select(BeneficiaryClaim).where(BeneficiaryClaim.merchant_id == merchant_id)
                         .order_by(BeneficiaryClaim.sequence.desc()).limit(1))

    def latest_claim_marker(self, merchant_id):
        with self.Session() as db:
            claim = self._latest_claim(db, merchant_id)
            return claim.id if claim is not None else None

    @staticmethod
    def _review_event_marker(events):
        """Fingerprint exactly the bounded inputs read for a review.

        This internal marker is not an attestation or proof of provider identity.
        """
        fields = [[event.id, event.sha256,
                   None if event.raw_body is None else hashlib.sha256(bytes(event.raw_body)).hexdigest(),
                   event.processed_at, event.signature, event.signature_timestamp,
                   event.signature_received_at, event.signature_key_ref] for event in events]
        return hashlib.sha256(json.dumps(fields, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()

    def review_event_marker(self, intent_id, merchant_id):
        """Read at most 101 events, as in the review's evidence-limit check."""
        with self.Session() as db:
            events = db.scalars(select(Event).join(Intent, Event.intent_id == Intent.id).where(
                Intent.id == intent_id, Intent.merchant_id == merchant_id
            ).order_by(Event.processed_at, Event.id).limit(101)).all()
            return self._review_event_marker(events)

    def _review_assessment(self, intent, events, bank_records, claim):
        status, report = stored_provider_report(intent, events)
        secret, reference, previous = self._webhook_secret, self._webhook_key_ref, self._webhook_previous_keys
        if intent.pey_credential_ref and self._merchant_signing_keys:
            reference = intent.pey_credential_ref
            secret, previous = self._merchant_signing_keys(intent, [event.signature_key_ref for event in events])
        signature = reverify_stored_events(events, secret, reference, historical_keys=previous)
        account = account_consistency(status, signature, events, claim)
        if status is not None:
            return status, signature, account
        if signature != 'VERIFIED':
            failures = {'NOT_RECORDED':'PROVIDER_SIGNATURE_NOT_RECORDED',
                        'KEY_UNAVAILABLE':'PROVIDER_SIGNATURE_KEY_UNAVAILABLE',
                        'INVALID':'PROVIDER_SIGNATURE_INVALID'}
            return failures.get(signature, 'PROVIDER_SIGNATURE_NOT_RECORDED'), signature, account
        if account == 'MISMATCH_OWNER_REPORT':
            return 'OWNER_ACCOUNT_MISMATCH', signature, account
        return compare_for_review(report, bank_records), signature, account

    def get(self,ident):
        with self.Session() as db:
            return db.get(Intent,ident)

    def get_by_order(self, merchant_id, order_id):
        with self.Session() as db:
            return db.scalar(select(Intent).where(
                Intent.merchant_id == merchant_id, Intent.order_id == order_id,
            ))

    def history(self, merchant_id):
        with self.Session() as db:
            rows = db.scalars(select(Intent).where(Intent.merchant_id == merchant_id)
                              .order_by(Intent.created_at.desc(), Intent.id.desc()).limit(50))
            return [view(row) for row in rows]

    def unresolved_page(self, merchant_id, limit, after=None):
        """List unresolved attempts for one merchant, oldest first.

        A keyset cursor preserves ordering among rows sharing the same second.
        The caller must restart at the first page to see concurrent earlier rows.
        """
        query = select(Intent).where(
            Intent.merchant_id == merchant_id,
            Intent.status.in_(('QR_REQUESTING', 'PROVIDER_UNCERTAIN')),
        )
        if after is not None:
            created_at, ident = after
            query = query.where(or_(Intent.created_at > created_at,
                                    and_(Intent.created_at == created_at, Intent.id > ident)))
        query = query.order_by(Intent.created_at.asc(), Intent.id.asc()).limit(limit + 1)
        with self.Session() as db:
            rows = list(db.scalars(query))
            has_more = len(rows) > limit
            rows = rows[:limit]
            cursor = {'created_at':rows[-1].created_at, 'id':rows[-1].id} if has_more else None
            return [view(row) for row in rows], cursor

    def reconciliation_preview(self, intent_id, merchant_id, bank_records):
        with self.Session() as db:
            intent = db.scalar(select(Intent).where(Intent.id == intent_id, Intent.merchant_id == merchant_id))
            if intent is None:
                raise PaymentConflict('Payment intent not found')
            events = db.scalars(select(Event).where(Event.intent_id == intent_id)
                                .order_by(Event.processed_at, Event.id).limit(101)).all()
            claim = self._latest_claim(db, merchant_id)
            marker = self._review_event_marker(events)
            return (*self._review_assessment(intent, events, bank_records, claim), marker)

    @staticmethod
    def _review_access(db, intent_id, actor_id, session_hash, csrf_hash, *, lock):
        def locked(query):
            return query.with_for_update() if lock else query
        session = db.scalar(locked(select(SessionRow).where(SessionRow.token_hash == session_hash)))
        if (session is None or session.user_id != actor_id or session.revoked_at is not None
                or session.expires_at <= int(time.time())):
            raise ReviewAccessError(401)
        if (not isinstance(session.csrf_hash, str) or not isinstance(csrf_hash, str)
                or not re.fullmatch(r'[0-9a-f]{64}', session.csrf_hash)
                or not re.fullmatch(r'[0-9a-f]{64}', csrf_hash)
                or not hmac.compare_digest(session.csrf_hash, csrf_hash)):
            raise ReviewAccessError(403)
        user = db.scalar(locked(select(User).where(User.id == actor_id)))
        if user is None or user.verified_at is None:
            raise ReviewAccessError(401)
        merchant_id = db.scalar(select(Intent.merchant_id).where(Intent.id == intent_id))
        if merchant_id is None:
            raise ReviewAccessError(404)
        # Claim writes lock user -> merchant -> membership. Acquire the same
        # ordering before reading the latest claim to serialize its updates.
        merchant = db.scalar(locked(select(Merchant).where(Merchant.id == merchant_id)))
        if merchant is None:
            raise ReviewAccessError(404)
        intent = db.scalar(locked(select(Intent).where(Intent.id == intent_id, Intent.merchant_id == merchant_id)))
        if intent is None:
            raise ReviewAccessError(404)
        member = db.scalar(locked(select(Membership).where(Membership.merchant_id == intent.merchant_id,
                                                            Membership.user_id == actor_id)))
        if member is None:
            raise ReviewAccessError(404)
        if member.role not in ('owner', 'admin'):
            raise ReviewAccessError(403)
        return intent

    def record_reconciliation_review(self, intent_id, actor_id, session_hash, csrf_hash, request_id, bank_records):
        try:
            with self.Session.begin() as db:
                if db.bind.dialect.name == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                intent = self._review_access(db, intent_id, actor_id, session_hash, csrf_hash, lock=True)
                prior = db.scalar(select(ReconciliationReview.id).where(
                    ReconciliationReview.intent_id == intent_id, ReconciliationReview.request_id == request_id))
                if prior is not None:
                    raise ReviewRequestConflict('Review request already used')
                events = db.scalars(select(Event).where(Event.intent_id == intent_id)
                                    .order_by(Event.processed_at, Event.id).limit(101).with_for_update()).all()
                claim = self._latest_claim(db, intent.merchant_id)
                classification, signature_assessment, account_assessment = self._review_assessment(intent, events, bank_records, claim)
                digest = None
                if len(events) <= 100:
                    identities = [[event.id, event.sha256] for event in events]
                    digest = hashlib.sha256(json.dumps(identities, separators=(',', ':'),
                                                       ensure_ascii=True).encode()).hexdigest()
                row = ReconciliationReview(id=uuid.uuid4().hex, intent_id=intent_id, actor_id=actor_id,
                    request_id=request_id, classification=classification, bank_record_count=len(bank_records),
                    provider_event_count=len(events), event_ids_hashes_sha256=digest,
                    signature_assessment=signature_assessment, account_assessment=account_assessment,
                    owner_claim_id=claim.id if claim is not None else None, created_at=int(time.time()))
                db.add(row)
                db.flush()
                return review_view(row)
        except IntegrityError as exc:
            raise ReviewWriteError('Review could not be persisted') from exc

    def read_reconciliation_reviews(self, intent_id, actor_id, session_hash, csrf_hash, request_id=None):
        with self.Session() as db:
            self._review_access(db, intent_id, actor_id, session_hash, csrf_hash, lock=False)
            query = select(ReconciliationReview).where(ReconciliationReview.intent_id == intent_id)
            if request_id is not None:
                row = db.scalar(query.where(ReconciliationReview.request_id == request_id))
                return None if row is None else review_view(row)
            rows = db.scalars(query.order_by(ReconciliationReview.created_at.desc(),
                                             ReconciliationReview.id.desc()).limit(51)).all()
            return {'reviews':[review_view(row) for row in rows[:50]], 'truncated':len(rows) > 50}

    def reserve(self,merchant_id,order_id,amount_minor,concept,numref,expiration_s,*,authorize=None,live_gateway=None,on_created=None):
        with self.Session.begin() as db:
            query = select(Intent).where(Intent.merchant_id == merchant_id, Intent.order_id == order_id)
            gateway = None
            if live_gateway is not None:
                if db.bind.dialect.name == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                authorize(db)
                prior = db.scalar(query)
                if prior is not None:
                    self._check_order(prior, amount_minor, concept, numref, expiration_s)
                    return prior, False, None
                gateway = live_gateway(db)
            ident = uuid.uuid4().hex
            insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
            stmt = insert(Intent).values(
                id=ident, merchant_id=merchant_id, order_id=order_id, amount_minor=amount_minor,
                concept=concept, numref=numref, expiration_s=expiration_s, status='QR_REQUESTING',
                created_at=int(time.time()), pey_credential_ref=gateway.reference if gateway else None,
            ).on_conflict_do_nothing().returning(Intent.id)
            try:
                created = db.scalar(stmt) is not None
            except IntegrityError as exc:
                raise PaymentConflict('Unique merchant reference or order collision') from exc
            row = db.scalar(query)
            if row is None:
                existing_reference = db.scalar(select(Intent.id).where(
                    Intent.merchant_id == merchant_id, Intent.numref == numref,
                ))
                if existing_reference is not None:
                    raise ReferenceConflict('Reference already belongs to another order')
                raise PaymentConflict('Unique intent collision')
            self._check_order(row, amount_minor, concept, numref, expiration_s)
            if created and on_created is not None:
                on_created(db, row)
            if live_gateway is not None:
                return row, created, gateway if created else None
            return row, created

    @staticmethod
    def _check_order(row, amount_minor, concept, numref, expiration_s):
        if (row.amount_minor, row.concept, row.numref, row.expiration_s) != (amount_minor, concept, numref, expiration_s):
            raise PaymentConflict('Order idempotency conflict')

    def uncertain(self,ident):
        with self.Session.begin() as db:
            row=db.scalar(select(Intent).where(Intent.id==ident).with_for_update())
            if row and row.status=='QR_REQUESTING':row.status='PROVIDER_UNCERTAIN'

    def reject(self, ident):
        with self.Session.begin() as db:
            row = db.scalar(select(Intent).where(Intent.id==ident).with_for_update())
            if row and row.status == 'QR_REQUESTING':
                row.status = 'PROVIDER_REJECTED'
            return row

    def pending_provider_events(self, row):
        with self.Session() as db:
            return list(db.scalars(select(PendingEvent).where(
                PendingEvent.intent_id == row.id,
                PendingEvent.merchant_id == row.merchant_id,
                PendingEvent.pey_credential_ref == row.pey_credential_ref,
            ).order_by(PendingEvent.received_at, PendingEvent.id).limit(6)))

    @staticmethod
    def _lock_events(db, qr_id, event_id=None):
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
            return
        # Take the event lock before the QR lock. Issuance needs only the QR lock.
        keys = [('event', event_id), ('qr', qr_id)] if event_id else [('qr', qr_id)]
        for namespace, identifier in keys:
            key = int.from_bytes(hashlib.sha256(f'{namespace}:{identifier}'.encode()).digest()[:4], 'big', signed=True)
            domain = 1 if namespace == 'event' else 2
            db.execute(text('SELECT pg_advisory_xact_lock(:domain, :key)'), {'domain': domain, 'key': key})

    def qr_issued(self,ident,qr_id,display):
        if not qr_id or not display:raise PaymentConflict('Empty provider response')
        with self.Session.begin() as db:
            self._lock_events(db, qr_id)
            row=db.scalar(select(Intent).where(Intent.id==ident).with_for_update())
            if row is not None and row.pey_credential_ref and row.status == 'PROVIDER_REPORTED' and row.provider_qr_id == qr_id:
                row.qr_display = display
                return
            if row is None or row.status!='QR_REQUESTING':raise PaymentConflict('Invalid issue state')
            row.provider_qr_id=qr_id
            row.qr_display=display
            row.status='QR_ISSUED'
            db.flush()
            pending=db.scalars(select(PendingEvent).where(
                PendingEvent.qr_id==qr_id,
                PendingEvent.merchant_id == (row.merchant_id if row.pey_credential_ref else None),
                PendingEvent.pey_credential_ref == row.pey_credential_ref,
                PendingEvent.intent_id == (row.id if row.pey_credential_ref else None),
            ).order_by(PendingEvent.received_at,PendingEvent.id).with_for_update()).all()
            for ev in pending:
                if row.pey_credential_ref and not ev.provider_verified:
                    continue
                if self._apply(row,ev.amount_minor,ev.numref,ev.transaction_id):
                    self._attach_pending(db, row, ev)
                    if row.pey_credential_ref:
                        self._mark_provider_readback(row, 'PEY_WEBHOOK_AND_API', ev.provider_payment_sha256)

    @staticmethod
    def _mark_provider_readback(row, source, digest):
        if row.provider_payment_source == 'PEY_WEBHOOK_AND_API':
            return
        row.provider_payment_source = source
        row.provider_payment_observed_at = int(time.time())
        row.provider_payment_sha256 = digest

    @staticmethod
    def _attach_pending(db, row, pending):
        db.add(Event(id=pending.id, sha256=pending.sha256, raw_body=pending.raw_body,
                     intent_id=row.id, processed_at=int(time.time()), signature=pending.signature,
                     signature_timestamp=pending.signature_timestamp,
                     signature_received_at=pending.signature_received_at,
                     signature_key_ref=pending.signature_key_ref))
        db.delete(pending)

    @staticmethod
    def _apply(row,amount_minor,numref,tx):
        if row.amount_minor!=amount_minor or row.numref!=numref:return False
        if row.status not in ('QR_ISSUED','PROVIDER_REPORTED'):return False
        if row.transaction_id and row.transaction_id!=tx:return False
        row.status='PROVIDER_REPORTED'
        row.transaction_id=tx
        return True

    def confirm_event(self,event_id,raw_body,qr_id,amount_minor,numref,transaction_id,signature_evidence=None,
                      *,merchant_id=None,credential_ref=None,intent_id=None,provider_digest=None):
        digest=hashlib.sha256(raw_body).hexdigest()
        signature_fields = {} if signature_evidence is None else {
            'signature':signature_evidence.signature, 'signature_timestamp':signature_evidence.timestamp,
            'signature_received_at':signature_evidence.received_at, 'signature_key_ref':signature_evidence.key_ref}
        with self.Session.begin() as db:
            self._lock_events(db, qr_id, event_id)
            prior=db.get(Event,event_id)
            if prior:
                if merchant_id is not None:
                    linked = db.get(Intent, prior.intent_id) if prior.intent_id else None
                    if (linked is None or linked.merchant_id != merchant_id
                            or (credential_ref and (linked.pey_credential_ref != credential_ref or linked.id != intent_id))):
                        raise PaymentConflict('Event does not belong to merchant')
                if prior.sha256!=digest:raise PaymentConflict('Event ID reused with different payload')
                return {'outcome':'DUPLICATE_EVENT','intent_id':prior.intent_id}
            pending=db.get(PendingEvent,event_id)
            if pending:
                if pending.sha256!=digest:raise PaymentConflict('Pending event modified')
                if (pending.merchant_id, pending.pey_credential_ref, pending.intent_id) != (
                        merchant_id, credential_ref, intent_id):
                    raise PaymentConflict('Pending event does not belong to this payment')
                if provider_digest is None and not pending.provider_verified:
                    return {'outcome':'PENDING_LINKAGE_DUPLICATE','intent_id':None}
            if credential_ref is not None:
                intent = db.scalar(select(Intent).where(Intent.id==intent_id).with_for_update())
                if (intent is None or intent.merchant_id != merchant_id or intent.pey_credential_ref != credential_ref
                        or intent.amount_minor != amount_minor or intent.numref != numref
                        or (intent.provider_qr_id is not None and intent.provider_qr_id != qr_id)):
                    raise PaymentConflict('Event does not match the reserved merchant payment')
            row=db.scalar(select(Intent).where(Intent.provider_qr_id==qr_id).with_for_update())
            if row is not None and (row.pey_credential_ref != credential_ref
                                    or (merchant_id is not None and row.merchant_id != merchant_id)
                                    or (intent_id is not None and row.id != intent_id)):
                raise PaymentConflict('QR does not belong to this merchant payment')
            if row is None and credential_ref and provider_digest and intent.status in ('QR_REQUESTING', 'PROVIDER_UNCERTAIN'):
                intent.provider_qr_id = qr_id
                intent.status = 'QR_ISSUED'
                row = intent
            if row is None or (credential_ref is not None and provider_digest is None):
                if merchant_id is not None and credential_ref is None:
                    raise PaymentConflict('QR not linked yet')
                if pending is None:
                    db.add(PendingEvent(id=event_id,sha256=digest,raw_body=raw_body,qr_id=qr_id,amount_minor=amount_minor,
                                        numref=numref,transaction_id=transaction_id,received_at=int(time.time()),
                                        merchant_id=merchant_id, pey_credential_ref=credential_ref, intent_id=intent_id,
                                        provider_verified=provider_digest is not None,
                                        provider_payment_sha256=provider_digest, **signature_fields))
                elif provider_digest is not None:
                    pending.provider_verified = True
                    pending.provider_payment_sha256 = provider_digest
                return {'outcome':'PENDING_LINKAGE','intent_id':None}
            prior_paid=row.status=='PROVIDER_REPORTED'
            if not self._apply(row,amount_minor,numref,transaction_id):
                raise PaymentConflict('Amount, reference or transaction contradiction')
            if pending is not None:
                self._attach_pending(db, row, pending)
            else:
                db.add(Event(id=event_id,sha256=digest,raw_body=raw_body,intent_id=row.id,
                             processed_at=int(time.time()),**signature_fields))
            if credential_ref is not None:
                self._mark_provider_readback(row, 'PEY_WEBHOOK_AND_API', provider_digest)
            db.flush()
            return {'outcome':'DUPLICATE_TRANSACTION' if prior_paid else 'PROVIDER_REPORTED','intent_id':row.id}

    def confirm_provider_lookup(self, snapshot, tx, digest):
        with self.Session.begin() as db:
            self._lock_events(db, snapshot.provider_qr_id)
            row = db.scalar(select(Intent).where(Intent.id == snapshot.id).with_for_update())
            if (row is None or row.merchant_id != snapshot.merchant_id
                    or row.provider_qr_id != snapshot.provider_qr_id
                    or row.pey_credential_ref != snapshot.pey_credential_ref
                    or not row.pey_credential_ref
                    or not self._apply(row, snapshot.amount_minor, snapshot.numref, tx)):
                raise PaymentConflict('Provider lookup contradicts payment')
            pending = db.scalars(select(PendingEvent).where(
                PendingEvent.qr_id == row.provider_qr_id,
                PendingEvent.merchant_id == row.merchant_id,
                PendingEvent.pey_credential_ref == row.pey_credential_ref,
                PendingEvent.intent_id == row.id,
                PendingEvent.transaction_id == tx,
                PendingEvent.amount_minor == row.amount_minor,
                PendingEvent.numref == row.numref,
            ).with_for_update()).all()
            for event in pending:
                self._attach_pending(db, row, event)
            self._mark_provider_readback(row, 'PEY_WEBHOOK_AND_API' if pending else 'PEY_API_READBACK', digest)
            db.flush()
            return row
