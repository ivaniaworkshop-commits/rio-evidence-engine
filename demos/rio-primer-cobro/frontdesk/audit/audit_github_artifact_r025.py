#!/usr/bin/env python3
"""R025 independent audit: GitHub API run+artifact metadata, original ZIP and job log."""
import argparse
import hashlib
import hmac
import io
import json
import re
import sys
import zipfile
from pathlib import Path

RUN=42199945830
ARTIFACT=13492779462
SHA="5eba35f0b8a28133a07d29a02f71218871e66b1c"
ALIAS="rio-primer-cobro-frontdesk.vercel.app"
PROJECT="prj_J7YrJusN08qUXrZNPDBmspVRKW6d"
EXPECTED={
 "missing.json":("ALIAS_UNKNOWN_MANUAL_REVIEW","ABSENT",47),
 "corrupt.json":("EVIDENCE_CORRUPT_MANUAL_REVIEW","INVALID",49),
}

class EvidenceError(ValueError):
    pass

def require(condition,reason):
    if not condition: raise EvidenceError(reason)

def json_object(b):
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,"DUPLICATE_JSON_KEY")
            d[k]=v
        return d
    value=json.loads(b,object_pairs_hook=unique)
    require(type(value) is dict,"OBJECT_EXPECTED")
    return value

def audit(archive,metadata,run,log):
    require(type(archive) is bytes and 0<len(archive)<=2000000,"ZIP_SIZE_INVALID")
    require(type(metadata) is dict and type(run) is dict and type(log) is str,"INVALID_INPUT")
    digest=hashlib.sha256(archive).hexdigest()
    md=metadata.get("digest")
    require(type(md) is str and md.startswith("sha256:"),"MISSING_GITHUB_DIGEST")
    require(hmac.compare_digest(digest,md[7:]),"ZIP_DIGEST_MISMATCH")
    require(metadata.get("id")==ARTIFACT and metadata.get("name")=="rio-r024-incidents","ARTIFACT_IDENTITY_INVALID")
    require(metadata.get("size_in_bytes")==len(archive) and metadata.get("expired") is False,"ARTIFACT_SIZE_OR_EXPIRY_INVALID")
    require(run.get("id")==RUN and run.get("head_sha")==SHA and
            run.get("event")=="push" and run.get("conclusion")=="success","RUN_PROVENANCE_MISMATCH")
    wf=metadata.get("workflow_run")
    require(type(wf) is dict and wf.get("id")==RUN and wf.get("head_sha")==SHA and
            wf.get("head_branch")=="deploy/primer-cobro","ARTIFACT_RUN_MISMATCH")
    files=[]
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            infos=z.infolist()
            require(len(infos)==2 and sorted(x.filename for x in infos)==sorted(EXPECTED),"FILE_SET_MISMATCH")
            require(z.testzip() is None,"ZIP_CRC_FAILED")
            for info in infos:
                require(not info.is_dir() and not info.flag_bits&1 and
                        info.compress_type in (zipfile.ZIP_DEFLATED,zipfile.ZIP_STORED) and
                        info.file_size<=10000,"UNSAFE_ZIP_MEMBER")
                name=info.filename
                require(name in EXPECTED and "/" not in name and "\\" not in name,"ZIP_PATH_INVALID")
                data=z.read(info)
                obj=json_object(data.decode("utf-8"))
                kind,evidence,exit_code=EXPECTED[name]
                require(obj.get("schema")=="RIO_RELEASE_INCIDENT_R023_V1" and
                        obj.get("result")=="INCIDENT_OPEN" and
                        obj.get("classification")==kind,"INCIDENT_STATE_INVALID")
                require(obj.get("commit")==SHA and obj.get("alias")==ALIAS and
                        obj.get("project")==PROJECT,"RECEIPT_IDENTITY_MISMATCH")
                require(obj.get("baseline_receipt")==evidence and
                        obj.get("fence_receipt")==evidence and
                        obj.get("promotion_step_outcome")=="failure" and
                        obj.get("alias_observation")=="UNKNOWN","EVIDENCE_CONTRADICTION")
                require(all(obj.get(k) is False for k in
                    ("automatic_rollback","production_write","incident_closed")),"UNSAFE_OR_CLOSED_INCIDENT")
                fault=obj.get("controlled_fault")
                require(type(fault) is dict and fault.get("exit_code")==exit_code and
                        fault.get("step_outcome")=="failure" and
                        fault.get("real_vercel_calls") is False,"INJECTION_REPORT_INVALID")
                files.append({"name":name,"bytes":len(data),
                              "sha256":hashlib.sha256(data).hexdigest(),"classification":kind})
    except (zipfile.BadZipFile,UnicodeError,json.JSONDecodeError) as e:
        raise EvidenceError("ZIP_OR_JSON_CORRUPT") from e
    for code,label in ((47,"MISSING"),(49,"CORRUPT")):
        require("R024_EXPECTED_EXIT_"+str(code) in log,"INJECTION_MARKER_ABSENT")
        require(re.search(r"Process completed with exit code "+str(code)+r"\.",log),"FAILURE_LOG_ABSENT")
        require("R024_"+label+"_READBACK_PASS" in log,"READBACK_LOG_ABSENT")
    return {"schema":"RIO_R025_INDEPENDENT_ARTIFACT_AUDIT",
            "result":"PASS_ARTIFACT_BYTES_PROVENANCE_AND_FAILURE_LOG",
            "source_run_id":RUN,"artifact_id":ARTIFACT,"commit":SHA,
            "archive_sha256":digest,"archive_bytes":len(archive),
            "files":sorted(files,key=lambda x:x["name"]),
            "observed_failure_codes_in_log":[47,49],
            "evidence_basis":"GITHUB_API_RUN_METADATA_PLUS_ARTIFACT_DIGEST_PLUS_JOB_LOG",
            "real_vercel_incident":False,"real_bank_payment":False,
            "android_physical":"NOT_OBSERVED","hash_proves_semantic_truth":False}

def main():
    parser=argparse.ArgumentParser()
    for key in ("zip","metadata","run","job-log","output"):
        parser.add_argument("--"+key,required=True)
    a=parser.parse_args()
    try:
        result=audit(Path(a.zip).read_bytes(),
           json_object(Path(a.metadata).read_bytes()),json_object(Path(a.run).read_bytes()),
           Path(a.job_log).read_text(encoding="utf-8"))
        p=Path(a.output);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("R025_INDEPENDENT_ARTIFACT_AUDIT_PASS")
        return 0
    except (OSError,ValueError,TypeError) as e:
        print(json.dumps({"result":"FAIL_CLOSED","reason":str(e)[:160]}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
