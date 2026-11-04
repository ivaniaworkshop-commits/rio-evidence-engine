"""Read-only Sphere Mother receipt consumer for a public Evidence Engine.

No imports, source code, credentials or network access to private RIO.
The commit pin only checks equality to a declared revision; it is NOT
independent proof that the private source was used or executed.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

# RIO PR #182 candidate head; not a released/published upstream version.
CANDIDATE_SOURCE_COMMIT = "6dce836f7b57d8b716a8a63fec641b6bc4428375"
SOURCE_SCHEMA = "RIO_SPHERE_ENGINE_RECEIPT/1.0"
RESULT_SCHEMA = "RIO_EVIDENCE_SPHERE_CONSUMER/1.0"


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("NON_CANONICAL_JSON") from exc


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def screen_bridge(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Screen declared engine/evidence/authority bindings; never execute.

    All inputs are untrusted. A matching hash or source commit does not prove
    origin, independent verification or permission to write.
    """
    if not isinstance(envelope, Mapping):
        raise ValueError("ENVELOPE_MUST_BE_MAPPING")

    def receipt(status: str, reason: str, digest: str | None = None) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "status": status,
            "reason": reason,
            "payload_sha256": digest,
            "source_commit": CANDIDATE_SOURCE_COMMIT,
            "source_revision_authenticated": False,
            "source_executed_attested": False,
            "evidence_authenticated": False,
            "authority_authenticated": False,
            "external_host_required": True,
            "write_allowed": False,
            "action_performed": False,
            "candidate_promoted": False,
            "production_ready": False,
        }

    if set(envelope) != {"source_commit", "engine", "evidence", "authority"}:
        return receipt("HOLD", "ENVELOPE_FIELDS_INVALID")
    if envelope["source_commit"] != CANDIDATE_SOURCE_COMMIT:
        return receipt("HOLD", "SOURCE_REVISION_UNPINNED")
    engine, evidence, authority = (envelope[key] for key in ("engine", "evidence", "authority"))
    if not all(isinstance(value, Mapping) for value in (engine, evidence, authority)):
        return receipt("HOLD", "RECEIPT_FIELDS_INVALID")
    if engine.get("schema") != SOURCE_SCHEMA or not _nonempty(engine.get("engine_id")):
        return receipt("HOLD", "ENGINE_SCHEMA_OR_ID_INVALID")
    if not isinstance(engine.get("payload"), Mapping):
        return receipt("HOLD", "ENGINE_PAYLOAD_INVALID")
    claimed_digest = engine.get("payload_sha256")
    if not isinstance(claimed_digest, str) or re.fullmatch(r"[0-9a-f]{64}", claimed_digest) is None:
        return receipt("HOLD", "ENGINE_DIGEST_INVALID")
    try:
        real_digest = hashlib.sha256(
            _canonical(dict(engine["payload"])).encode("utf-8")
        ).hexdigest()
    except ValueError:
        return receipt("HOLD", "ENGINE_PAYLOAD_INVALID")
    if real_digest != claimed_digest:
        return receipt("HOLD", "ENGINE_DIGEST_MISMATCH", claimed_digest)

    if evidence.get("subject_sha256") != claimed_digest:
        return receipt("HOLD", "EVIDENCE_SUBJECT_MISMATCH", claimed_digest)
    if not _nonempty(evidence.get("source_ref")) or not _nonempty(evidence.get("verifier_id")):
        return receipt("HOLD", "EVIDENCE_PROVENANCE_MISSING", claimed_digest)
    if evidence["verifier_id"].strip() == engine["engine_id"].strip():
        return receipt("HOLD", "VERIFIER_NOT_DISTINCT", claimed_digest)
    if evidence.get("result") != "PASS":
        return receipt("HOLD", "EVIDENCE_NOT_PASS", claimed_digest)

    if authority.get("decision") == "DENY":
        return receipt("DENY", "AUTHORITY_DECLARED_DENY", claimed_digest)
    if authority.get("decision") != "APPROVE":
        return receipt("HOLD", "AUTHORITY_NOT_APPROVED", claimed_digest)
    if authority.get("subject_sha256") != claimed_digest:
        return receipt("HOLD", "AUTHORITY_SUBJECT_MISMATCH", claimed_digest)
    if not _nonempty(authority.get("operation")) or not _nonempty(authority.get("target")):
        return receipt("HOLD", "AUTHORITY_SCOPE_MISSING", claimed_digest)
    if not _nonempty(authority.get("issuer_id")) or not _nonempty(authority.get("approval_ref")):
        return receipt("HOLD", "AUTHORITY_PROVENANCE_MISSING", claimed_digest)
    ids = {engine["engine_id"].strip(), evidence["verifier_id"].strip(), authority["issuer_id"].strip()}
    if len(ids) != 3:
        return receipt("HOLD", "ACTOR_IDS_NOT_DISTINCT", claimed_digest)

    # Deliberately cannot return ALLOW even with superficially complete inputs.
    return receipt("HOST_VERIFICATION_REQUIRED", "DECLARED_BINDINGS_CONSISTENT", claimed_digest)
