"""Single-process SQLite journal for local verification / durable single-host use.
NOT safe as a serverless database or as proof of bank settlement.
"""
import contextlib
import hashlib
import json
import sqlite3
import time
import uuid


class StoreError(ValueError):
    pass


class PaymentStore:
    def __init__(self, filename: str):
        self.filename = filename
        self._init()

    @contextlib.contextmanager
    def connection(self):
        db = sqlite3.connect(self.filename, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    def _init(self):
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS intents (
                  id TEXT PRIMARY KEY,
                  merchant TEXT NOT NULL,
                  order_id TEXT NOT NULL,
                  amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                  concept TEXT NOT NULL,
                  numref TEXT NOT NULL,
                  expiration_s INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  provider_qr_id TEXT UNIQUE,
                  qr_display TEXT,
                  transaction_id TEXT UNIQUE,
                  created_at INTEGER NOT NULL,
                  UNIQUE(merchant,order_id),
                  UNIQUE(merchant,numref)
                );
                CREATE TABLE IF NOT EXISTS pending_events (
                  event_id TEXT PRIMARY KEY,
                  sha256 TEXT NOT NULL,
                  qr_id TEXT NOT NULL,
                  amount_minor INTEGER NOT NULL,
                  numref TEXT NOT NULL,
                  transaction_id TEXT NOT NULL,
                  received_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pending_qr ON pending_events(qr_id);
                CREATE TABLE IF NOT EXISTS events (
                  event_id TEXT PRIMARY KEY,
                  sha256 TEXT NOT NULL,
                  intent_id TEXT,
                  processed_at INTEGER NOT NULL,
                  FOREIGN KEY(intent_id) REFERENCES intents(id)
                );
            """)

    @staticmethod
    def public(row):
        if row is None:
            return None
        return {k: row[k] for k in ["id", "merchant", "order_id", "amount_minor", "numref", "status", "qr_display", "created_at"]}

    def get(self, intent_id: str):
        with self.connection() as db:
            return db.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone()

    def reserve(self, *, merchant, order_id, amount_minor, concept, numref, expiration_s):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prev = db.execute("SELECT * FROM intents WHERE merchant=? AND order_id=?", (merchant,order_id)).fetchone()
            if prev is not None:
                if (prev["amount_minor"],prev["concept"],prev["numref"],prev["expiration_s"]) != (amount_minor,concept,numref,expiration_s):
                    db.rollback()
                    raise StoreError("Order idempotency conflict")
                db.commit()
                return prev, False
            ident = uuid.uuid4().hex
            try:
                db.execute("INSERT INTO intents VALUES (?,?,?,?,?,?,?,? ,NULL,NULL,NULL,?)",
                           (ident, merchant, order_id, amount_minor,concept,numref,expiration_s,"QR_REQUESTING",int(time.time())))
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise StoreError("Unique reference conflict") from exc
            row = db.execute("SELECT * FROM intents WHERE id=?", (ident,)).fetchone()
            db.commit()
            return row, True

    def qr_issued(self, intent_id, provider_qr_id: str, display: str):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                res = db.execute("UPDATE intents SET status='QR_ISSUED',provider_qr_id=?,qr_display=? WHERE id=? AND status='QR_REQUESTING'",
                                 (provider_qr_id,display,intent_id))
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise StoreError("Provider QR id collision") from exc
            if res.rowcount != 1:
                db.rollback()
                raise StoreError("Invalid state for QR issue")
            # Authenticated webhook may have arrived before QR mapping was stored.
            # Atomic with QR issue: no window for losing pre-link events.
            pending=db.execute("SELECT * FROM pending_events WHERE qr_id=? ORDER BY received_at,event_id",(provider_qr_id,)).fetchall()
            for event in pending:
                row=db.execute("SELECT * FROM intents WHERE id=?",(intent_id,)).fetchone()
                if (row["amount_minor"] != event["amount_minor"] or row["numref"] != event["numref"]):
                    # Keep contradiction as evidence in the pending inbox. Do not mark PAID.
                    continue
                if row["status"] not in ("QR_ISSUED", "PROVIDER_REPORTED"):
                    continue
                if row["transaction_id"] and row["transaction_id"] != event["transaction_id"]:
                    continue
                duplicate_tx=db.execute("SELECT id FROM intents WHERE transaction_id=? AND id!=?",(event["transaction_id"],intent_id)).fetchone()
                if duplicate_tx:
                    continue
                db.execute("UPDATE intents SET status='PROVIDER_REPORTED',transaction_id=? WHERE id=?",(event["transaction_id"],intent_id))
                db.execute("INSERT INTO events VALUES (?,?,?,?)",(event["event_id"],event["sha256"],intent_id,int(time.time())))
                db.execute("DELETE FROM pending_events WHERE event_id=?",(event["event_id"],))
            db.commit()

    def uncertain(self, intent_id):
        with self.connection() as db:
            db.execute("UPDATE intents SET status='PROVIDER_UNCERTAIN' WHERE id=? AND status='QR_REQUESTING'", (intent_id,))

    def confirm_event(self, *, event_id, raw_body: bytes, qr_id: str, amount_minor: int, numref: str, transaction_id: str):
        digest = hashlib.sha256(raw_body).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            event = db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
            if event is not None:
                if event["sha256"] != digest:
                    db.rollback()
                    raise StoreError("Event id collision with modified payload")
                db.commit()
                return {"outcome":"DUPLICATE_EVENT", "intent_id":event["intent_id"]}
            prior_pending=db.execute("SELECT * FROM pending_events WHERE event_id=?", (event_id,)).fetchone()
            if prior_pending is not None:
                if prior_pending["sha256"] != digest:
                    db.rollback()
                    raise StoreError("Pending event id collision with modified payload")
                db.commit()
                return {"outcome":"PENDING_LINKAGE_DUPLICATE", "intent_id":None, "bank_settled":False}
            row = db.execute("SELECT * FROM intents WHERE provider_qr_id=?", (qr_id,)).fetchone()
            if row is None:
                db.execute("INSERT INTO pending_events VALUES (?,?,?,?,?,?,?)",
                           (event_id,digest,qr_id,amount_minor,numref,transaction_id,int(time.time())))
                db.commit()
                return {"outcome":"PENDING_LINKAGE", "intent_id":None, "bank_settled":False}
            if row["amount_minor"] != amount_minor or row["numref"] != numref:
                db.rollback()
                raise StoreError("Payment amount or reference mismatch")
            if row["status"] not in ("QR_ISSUED", "PROVIDER_REPORTED"):
                db.rollback()
                raise StoreError("Invalid payment transition")
            if row["transaction_id"] and row["transaction_id"] != transaction_id:
                db.rollback()
                raise StoreError("Contradictory transactions for one QR")
            prior = row["status"] == "PROVIDER_REPORTED"
            try:
                db.execute("UPDATE intents SET status='PROVIDER_REPORTED',transaction_id=? WHERE id=?",(transaction_id,row["id"]))
                db.execute("INSERT INTO events VALUES (?,?,?,?)",(event_id,digest,row["id"],int(time.time())))
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise StoreError("Transaction reused or event collision") from exc
            db.commit()
            return {"outcome":"DUPLICATE_TRANSACTION" if prior else "PROVIDER_REPORTED", "intent_id":row["id"],"bank_settled":False}
