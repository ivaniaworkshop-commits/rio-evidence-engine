"""Tenant-scoped recording of minimized provider account observations."""
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from .models import BeneficiaryClaim, ProviderAccountObservation


def observation_view(row):
    return {'id':row.id, 'status':row.status, 'checked_at':row.created_at,
            'sequence':row.sequence, 'source':'SERVER_PEY_HTTPS_READ_ONLY',
            'merchant_ownership_verified':False, 'bank_payment_confirmed':False,
            'live_payments_enabled':False}


class ProviderObservations:
    def __init__(self, accounts):
        self.accounts = accounts
        self.Session = accounts.Session

    @staticmethod
    def _claim(db, merchant_id):
        return db.scalar(select(BeneficiaryClaim).where(BeneficiaryClaim.merchant_id == merchant_id)
                         .order_by(BeneficiaryClaim.sequence.desc()).limit(1))

    def _begin(self, db, principal, merchant_id):
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        self.accounts._claim_access(db, principal, merchant_id, lock=True)

    def prepare(self, principal, merchant_id, request_id):
        with self.Session.begin() as db:
            self._begin(db, principal, merchant_id)
            prior = db.scalar(select(ProviderAccountObservation.id).where(
                ProviderAccountObservation.merchant_id == merchant_id,
                ProviderAccountObservation.request_id == request_id))
            if prior is not None:
                raise HTTPException(409, 'Account check request already used')
            claim = self._claim(db, merchant_id)
            if claim is None or claim.claim != 'OWNER_REPORTED_VERIFIED' or not claim.provider_account_id:
                raise HTTPException(409, 'A current owner account declaration is required')
            return claim.id, claim.provider_account_id

    def record(self, principal, merchant_id, request_id, claim_id, account_id, credential_ref, status):
        if status not in ('ACTIVE', 'PENDING', 'PROCESSING', 'ERROR', 'NOT_FOUND'):
            raise HTTPException(503, 'Account check unavailable')
        try:
            with self.Session.begin() as db:
                self._begin(db, principal, merchant_id)
                claim = self._claim(db, merchant_id)
                if (claim is None or claim.id != claim_id or claim.claim != 'OWNER_REPORTED_VERIFIED'
                        or claim.provider_account_id != account_id):
                    raise HTTPException(409, 'Account declaration changed during provider lookup')
                prior = db.scalar(select(ProviderAccountObservation.id).where(
                    ProviderAccountObservation.merchant_id == merchant_id,
                    ProviderAccountObservation.request_id == request_id))
                if prior is not None:
                    raise HTTPException(409, 'Account check request already used')
                sequence = db.scalar(select(ProviderAccountObservation.sequence).where(
                    ProviderAccountObservation.merchant_id == merchant_id)
                    .order_by(ProviderAccountObservation.sequence.desc()).limit(1)) or 0
                row = ProviderAccountObservation(id=uuid.uuid4().hex, merchant_id=merchant_id,
                    claim_id=claim_id, actor_id=principal['id'], request_id=request_id,
                    sequence=sequence + 1, credential_ref=credential_ref, status=status,
                    created_at=int(time.time()))
                db.add(row)
                db.flush()
                return observation_view(row)
        except IntegrityError:
            raise HTTPException(503, 'Account check could not be recorded') from None

    def readiness(self, principal, merchant_id, credential_ref):
        with self.Session.begin() as db:
            self._begin(db, principal, merchant_id)
            claim = self._claim(db, merchant_id)
            latest = db.scalar(select(ProviderAccountObservation).where(
                ProviderAccountObservation.merchant_id == merchant_id)
                .order_by(ProviderAccountObservation.sequence.desc()).limit(1))
            current = (latest is not None and claim is not None and latest.claim_id == claim.id
                       and claim.claim == 'OWNER_REPORTED_VERIFIED'
                       and latest.credential_ref == credential_ref)
            return {
                'production':'BLOCKED', 'live_payments_enabled':False,
                'provider_observation':observation_view(latest) if latest is not None else None,
                'provider_observation_matches_current_declaration':current,
                'merchant_ownership_verified':False, 'provider_key_id_bound':False,
                'independent_bank_source_verified':False, 'bank_payment_confirmed':False,
                'secret_management_verified':False, 'specific_operation_authorized':False,
                'gates':{
                    'merchant_account_ownership':'NOT_VERIFIED',
                    'provider_api_key_id_binding':'NOT_VERIFIED',
                    'independent_bank_credit':'NOT_VERIFIED',
                    'provider_webhook_contract_and_trusted_time':'NOT_VERIFIED',
                    'secret_management_and_rotation':'NOT_VERIFIED',
                    'sensitive_data_encryption_and_retention':'NOT_VERIFIED',
                    'production_backup_and_restore':'NOT_VERIFIED',
                    'production_email_and_https':'NOT_VERIFIED',
                    'operational_monitoring_and_recovery':'NOT_VERIFIED',
                    'specific_payment_authorization':'NOT_AUTHORIZED',
                },
            }
