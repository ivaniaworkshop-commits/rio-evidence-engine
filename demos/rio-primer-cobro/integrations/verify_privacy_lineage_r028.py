#!/usr/bin/env python3
"""R028 check: scan all revisions of selected payment files, not only latest.
No values from examined sources appear in stdout/stderr.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
BASE="5ee14ce6ca1a7e76a23d94e9804dabd4911f88dc"
PATHS=(
 "demos/rio-primer-cobro/integrations/pey_evidence_r027.mjs",
 "demos/rio-primer-cobro/tests/test_pey_r027.mjs",
 "demos/rio-primer-cobro/integrations/R027_PEY_PROVIDER_RECONCILIATION.md",
 "demos/rio-primer-cobro/integrations/pey_emulated_r026.mjs",
 "demos/rio-primer-cobro/tests/test_pey_r026.mjs")
PATTERN=re.compile(rb"(?<!\d)\d{18}(?!\d)")
def checksum_valid(candidate):
 weights=(3,7,1)
 weighted=sum((int(candidate[i])-48)*weights[i%3]%10 for i in range(17))
 return (10-weighted%10)%10==int(candidate[17])-48

class PrivacyGuardError(Exception):pass
def git(repo,*args):
 p=subprocess.run(["git","-C",str(repo),*args],capture_output=True,timeout=15)
 if p.returncode:raise PrivacyGuardError("GIT_EVIDENCE_UNAVAILABLE")
 return p.stdout
def audit(repo,base=BASE,paths=PATHS):
 if not re.fullmatch(r"[0-9a-f]{40}",base):raise PrivacyGuardError("INVALID_BASE")
 head=git(repo,"rev-parse","HEAD").decode().strip()
 git(repo,"cat-file","-e",base+"^{commit}")
 git(repo,"merge-base","--is-ancestor",base,"HEAD")
 revisions=git(repo,"rev-list","--reverse",base+"..HEAD").decode().splitlines()
 if not 1<=len(revisions)<=128:raise PrivacyGuardError("SPAN_OUTSIDE_POLICY")
 checked=0
 for commit in [base,*revisions]:
  files=set(git(repo,"ls-tree","-r","--name-only",commit).decode().splitlines())
  for path in paths:
   if path not in files:continue
   value=git(repo,"show",commit+":"+path)
   if len(value)>2_000_000:raise PrivacyGuardError("SOURCE_TOO_LARGE")
   checked+=1
   if any(checksum_valid(match.group()) for match in PATTERN.finditer(value)):
    raise PrivacyGuardError("HISTORICAL_CLABE_PATTERN")
 return {"schema":"RIO_R028_PRIVACY_LINEAGE_V1","status":"PASS_SELECTED_PATH_HISTORY",
  "base":base,"head":head,"new_commits":len(revisions),"examined_revisions":checked,
  "checksum_valid_18digit_pattern_found":False,"all_refs_remediated":False,"github_cache_purged":False,
  "historical_incident_closed":False}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--repo",default=".");p.add_argument("--base",default=BASE);p.add_argument("--output")
 a=p.parse_args()
 try:
  result=audit(Path(a.repo).resolve(),a.base)
  if a.output:
   f=Path(a.output);f.parent.mkdir(parents=True,exist_ok=True)
   f.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
  print(json.dumps(result,sort_keys=True))
 except (PrivacyGuardError,OSError,ValueError,UnicodeError,subprocess.TimeoutExpired):
  print(json.dumps({"status":"FAIL_CLOSED","sensitive_values_logged":False}),file=sys.stderr)
  sys.exit(2)
