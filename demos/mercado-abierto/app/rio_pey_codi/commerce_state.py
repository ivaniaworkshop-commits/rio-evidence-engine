"""R016: isolated, versioned DEMO commercial state per real gateway account.

No external payment provider. Uses existing gateway cookie+CSRF and SQLAlchemy DB.
Migration required when auto_create=False. Snapshot is NOT authoritative payment proof.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

from fastapi import HTTPException, Request
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Text, update
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from starlette.concurrency import run_in_threadpool

from .models import Base

MAX_BYTES = 1024 * 1024
COLLECTIONS = ("businesses", "products", "rfqs", "offers", "orders", "freights", "sales", "events")


class DemoCommercialState(Base):
    __tablename__ = "hackaton_commercial_states"
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_hackaton_commercial_revision_positive"),)
    user_id = Column(String(32), ForeignKey("users.id"), primary_key=True)
    revision = Column(Integer, nullable=False)
    state_json = Column(Text, nullable=False)
    updated_at = Column(Integer, nullable=False)


def _decode(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Demo state exceeds 1 MiB")
    def unique_pairs(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("Duplicate JSON key")
            output[key] = value
        return output
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise HTTPException(422, "Invalid demo JSON")


def _validate(data):
    if not isinstance(data, dict) or set(data) != {"revision", "state"}:
        raise HTTPException(422, "Expected revision and state")
    revision = data["revision"]
    value = data["state"]
    if type(revision) is not int or not 0 <= revision <= 2147483646:
        raise HTTPException(422, "Invalid revision")
    if not isinstance(value, dict) or value.get("schema") != "RIO_MERCADO_DEMO_R001":
        raise HTTPException(422, "Invalid demo state schema")
    if not all(isinstance(value.get(key), list) and len(value[key]) <= 10000 for key in COLLECTIONS):
        raise HTTPException(422, "Invalid demo collections")
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > 24:
            raise HTTPException(422, "Demo state nesting too deep")
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise HTTPException(422, "Non-finite demo number")
    for key in COLLECTIONS:
        ids = []
        for row in value[key]:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not 1 <= len(row["id"]) <= 128:
                raise HTTPException(422, "Invalid record identifier")
            ids.append(row["id"])
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "Duplicate record identifier")
    return revision, value


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def register_commerce_state_routes(app, accounts):
    def load(uid):
        try:
            with accounts.Session() as db:
                row = db.get(DemoCommercialState, uid)
                if row is None:
                    return {"revision": 0, "state": None}
                return {"revision": row.revision, "state": json.loads(row.state_json)}
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, "Commercial-state schema not ready")

    def save(uid, revision, state):
        serialized = _canonical(state)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        try:
            with accounts.Session.begin() as db:
                if revision == 0:
                    if db.get(DemoCommercialState, uid) is not None:
                        raise HTTPException(409, "Stale commercial-state revision")
                    db.add(DemoCommercialState(user_id=uid, revision=1, state_json=serialized,
                                               updated_at=int(time.time())))
                    db.flush()
                    return {"revision": 1, "sha256": digest}
                result = db.execute(
                    update(DemoCommercialState)
                    .where(DemoCommercialState.user_id == uid,
                           DemoCommercialState.revision == revision)
                    .values(revision=revision + 1, state_json=serialized, updated_at=int(time.time()))
                )
                if result.rowcount != 1:
                    raise HTTPException(409, "Stale commercial-state revision")
                return {"revision": revision + 1, "sha256": digest}
        except IntegrityError:
            raise HTTPException(409, "Stale commercial-state revision")
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, "Commercial-state schema not ready")

    @app.get("/api/hackaton/commercial-state", include_in_schema=False)
    async def get_commerce(request: Request):
        principal = await run_in_threadpool(accounts.session, request)
        return await run_in_threadpool(load, principal["id"])

    @app.put("/api/hackaton/commercial-state", include_in_schema=False)
    async def put_commerce(request: Request):
        principal = await run_in_threadpool(accounts.session, request, True)
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > MAX_BYTES:
            raise HTTPException(413, "Demo state exceeds 1 MiB")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "Demo state exceeds 1 MiB")
            payload.extend(chunk)
        revision, value = _validate(_decode(bytes(payload)))
        return await run_in_threadpool(save, principal["id"], revision, value)
