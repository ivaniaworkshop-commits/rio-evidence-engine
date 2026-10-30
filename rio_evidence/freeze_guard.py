"""H14 source freeze: verify local file bytes equal a pre-external-data receipt.

This check is change detection, NOT signed attestation or code isolation.
"""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
RECEIPT="evaluation/H14_SOURCE_FREEZE_R001.json"
FILES={"candidate":"rio_evidence/candidate_v1.py","baseline":"rio_evidence/extended_graph.py"}

def verify_freeze(root=ROOT):
    root=Path(root)
    receipt=json.loads((root/RECEIPT).read_text(encoding="utf-8"))
    if receipt.get("schema")!="RIO_H14_SOURCE_FREEZE_R001" or receipt.get("candidate_promoted") is not False:
        raise ValueError("INVALID_FREEZE_RECEIPT")
    if receipt.get("independent_holdout_available_at_freeze") is not False:
        raise ValueError("FALSE_EXTERNAL_HOLDOUT_CLAIM")
    details={}
    for role,path in FILES.items():
        record=receipt.get(role)
        if not isinstance(record,dict) or record.get("path")!=path:
            raise ValueError("UNEXPECTED_FROZEN_SOURCE_PATH")
        if not isinstance(record.get("sha256"),str) or not re.fullmatch("[0-9a-f]{64}",record["sha256"]):
            raise ValueError("INVALID_FROZEN_DIGEST")
        if not isinstance(record.get("source_commit"),str) or not re.fullmatch("[0-9a-f]{40}",record["source_commit"]):
            raise ValueError("INVALID_FROZEN_COMMIT")
        data=(root/path).read_bytes()
        if len(data)!=record["bytes"] or hashlib.sha256(data).hexdigest()!=record["sha256"]:
            raise ValueError("FROZEN_SOURCE_BYTE_DRIFT:"+role)
        details[role+"_sha256"]=record["sha256"]
        details[role+"_source_commit"]=record["source_commit"]
    return {"status":"FROZEN_SOURCE_BYTES_MATCH_LOCAL_RECEIPT",
       "scope":"LOCAL_BYTE_CHANGE_DETECTION_NOT_SIGNED_REVISION_OR_EXTERNAL_EVALUATION",
       "candidate_promoted":False,
       "external_evaluator_authenticated":False,**details}
