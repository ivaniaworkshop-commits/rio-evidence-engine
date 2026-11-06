import io
import hashlib
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_github_artifact_r025 import audit,EvidenceError,SHA,RUN,ARTIFACT,ALIAS,PROJECT

LOG=("R024_EXPECTED_EXIT_47\n##[error]Process completed with exit code 47.\n"
     "R024_MISSING_READBACK_PASS\nR024_EXPECTED_EXIT_49\n"
     "##[error]Process completed with exit code 49.\nR024_CORRUPT_READBACK_PASS\n")

def fixture():
    z=io.BytesIO()
    with zipfile.ZipFile(z,"w",compression=zipfile.ZIP_DEFLATED) as writer:
        for name,classification,state,code in (
            ("missing.json","ALIAS_UNKNOWN_MANUAL_REVIEW","ABSENT",47),
            ("corrupt.json","EVIDENCE_CORRUPT_MANUAL_REVIEW","INVALID",49)):
            record={"schema":"RIO_RELEASE_INCIDENT_R023_V1","result":"INCIDENT_OPEN",
                    "classification":classification,"commit":SHA,"alias":ALIAS,"project":PROJECT,
                    "baseline_receipt":state,"fence_receipt":state,"promotion_step_outcome":"failure",
                    "alias_observation":"UNKNOWN","automatic_rollback":False,
                    "production_write":False,"incident_closed":False,
                    "controlled_fault":{"exit_code":code,"step_outcome":"failure","real_vercel_calls":False}}
            writer.writestr(name,json.dumps(record))
    raw=z.getvalue()
    meta={"id":ARTIFACT,"name":"rio-r024-incidents",
          "digest":"sha256:"+hashlib.sha256(raw).hexdigest(),
          "size_in_bytes":len(raw),"expired":False,
          "workflow_run":{"id":RUN,"head_sha":SHA,"head_branch":"deploy/primer-cobro"}}
    run={"id":RUN,"head_sha":SHA,"event":"push","conclusion":"success"}
    return raw,meta,run,LOG

class EvidenceAudit(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(len(audit(*fixture())["files"]),2)
    def test_modified_zip(self):
        z,m,r,l=fixture()
        with self.assertRaisesRegex(EvidenceError,"ZIP_DIGEST_MISMATCH"):
            audit(z+b"tamper",m,r,l)
    def test_wrong_hash(self):
        z,m,r,l=fixture();m["digest"]="sha256:"+"0"*64
        with self.assertRaisesRegex(EvidenceError,"ZIP_DIGEST_MISMATCH"):audit(z,m,r,l)
    def test_wrong_run(self):
        z,m,r,l=fixture();r["id"]=55
        with self.assertRaisesRegex(EvidenceError,"RUN_PROVENANCE_MISMATCH"):audit(z,m,r,l)
    def test_wrong_provenance(self):
        z,m,r,l=fixture();m["workflow_run"]["head_sha"]="b"*40
        with self.assertRaisesRegex(EvidenceError,"ARTIFACT_RUN_MISMATCH"):audit(z,m,r,l)
    def test_expired(self):
        z,m,r,l=fixture();m["expired"]=True
        with self.assertRaisesRegex(EvidenceError,"ARTIFACT_SIZE_OR_EXPIRY_INVALID"):audit(z,m,r,l)
    def test_failure_log_missing(self):
        z,m,r,l=fixture();l=l.replace("Process completed with exit code 49.","")
        with self.assertRaisesRegex(EvidenceError,"FAILURE_LOG_ABSENT"):audit(z,m,r,l)
    def test_readback_missing(self):
        z,m,r,l=fixture();l=l.replace("R024_MISSING_READBACK_PASS","")
        with self.assertRaisesRegex(EvidenceError,"READBACK_LOG_ABSENT"):audit(z,m,r,l)
    def test_traversal(self):
        z,m,r,l=fixture();target=io.BytesIO()
        with zipfile.ZipFile(target,"w") as writer:writer.writestr("../escape.json","{}")
        z=target.getvalue();m["digest"]="sha256:"+hashlib.sha256(z).hexdigest()
        m["size_in_bytes"]=len(z)
        with self.assertRaisesRegex(EvidenceError,"FILE_SET_MISMATCH"):audit(z,m,r,l)
    def test_reported_rollback_rejected(self):
        z,m,r,l=fixture()
        with zipfile.ZipFile(io.BytesIO(z)) as original:
            docs={name:json.loads(original.read(name)) for name in original.namelist()}
        docs["missing.json"]["automatic_rollback"]=True
        target=io.BytesIO()
        with zipfile.ZipFile(target,"w") as writer:
            for name,doc in docs.items():writer.writestr(name,json.dumps(doc))
        z=target.getvalue();m["digest"]="sha256:"+hashlib.sha256(z).hexdigest()
        m["size_in_bytes"]=len(z)
        with self.assertRaisesRegex(EvidenceError,"UNSAFE_OR_CLOSED_INCIDENT"):audit(z,m,r,l)
    def test_missing_digest(self):
        z,m,r,l=fixture();del m["digest"]
        with self.assertRaisesRegex(EvidenceError,"MISSING_GITHUB_DIGEST"):audit(z,m,r,l)

if __name__=="__main__":unittest.main()
