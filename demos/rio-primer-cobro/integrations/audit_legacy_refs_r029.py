"""R029 read-only Git reference audit. Never print inspected bank identifiers."""
import argparse,json,re,subprocess,sys
from pathlib import Path
BASE="5ee14ce6ca1a7e76a23d94e9804dabd4911f88dc"
LEGACY="refs/remotes/origin/deploy/primer-cobro"
PATH="demos/rio-primer-cobro/tests/test_pey_r027.mjs"
WF=".github/workflows/rio-primer-cobro-deploy.yml"
PATTERN=re.compile(rb"(?<![0-9])[0-9]{18}(?![0-9])")
class AuditError(Exception):pass
def git(repo,*args,allowed=(0,)):
    p=subprocess.run(["git","-C",str(repo),*args],capture_output=True,timeout=25)
    if p.returncode not in allowed:raise AuditError("GIT_UNAVAILABLE")
    return p
def ancestor(repo,a,b):
    return git(repo,"merge-base","--is-ancestor",a,b,allowed=(0,1)).returncode==0
def valid(b):
    total=sum(((b[i]-48)*(3,7,1)[i%3])%10 for i in range(17))
    return (10-total%10)%10==b[17]-48
def affected(repo,base,ref):
    if not ancestor(repo,base,ref):raise AuditError("DIFFERENT_ANCESTRY")
    commits=git(repo,"rev-list","--reverse",base+".."+ref,"--",PATH).stdout.decode().splitlines()
    if len(commits)>200:raise AuditError("SPAN_TOO_LARGE")
    hits=[]
    for sha in commits:
        data=git(repo,"show",sha+":"+PATH).stdout
        if len(data)>2000000:raise AuditError("SOURCE_TOO_LARGE")
        if any(valid(x.group()) for x in PATTERN.finditer(data)):hits.append(sha)
    return commits,hits
def retired(repo,ref):
    txt=git(repo,"show",ref+":"+WF).stdout.decode()
    m=re.search(r"(?m)^  deploy:\s*$",txt)
    if m is None:raise AuditError("DEPLOY_MISSING")
    tail=txt[m.end():]
    nxt=re.search(r"(?m)^  [A-Za-z][A-Za-z0-9_-]*:\s*$",tail)
    if nxt:tail=tail[:nxt.start()]
    if not re.search(r"(?m)^    if: false\s*$",tail):raise AuditError("OLD_RELEASE_NOT_DISABLED")
    return True
def audit(repo,base=BASE,legacy=LEGACY,clean="HEAD"):
    if not re.fullmatch(r"[a-f0-9]{40}",base):raise AuditError("BAD_BASE")
    git(repo,"cat-file","-e",base+"^{commit}")
    old,bad=affected(repo,base,legacy)
    if not bad:raise AuditError("KNOWN_INCIDENT_NOT_REPRODUCED")
    new,unsafe=affected(repo,base,clean)
    if unsafe or any(ancestor(repo,x,clean) for x in bad):raise AuditError("CLEAN_ANCESTRY_COMPROMISED")
    retired(repo,legacy)
    refs=git(repo,"for-each-ref","--format=%(refname)","refs/heads","refs/remotes","refs/tags").stdout.decode().splitlines()
    reachable=sorted(r for r in refs if any(ancestor(repo,x,r) for x in bad))
    if legacy not in reachable:raise AuditError("OLD_REF_NOT_REACHABLE")
    return {"schema":"RIO_R029_REFERENCE_AUDIT_V1","result":"PASS_LIMITED_SCOPE",
        "safe_base":base,"legacy_ref":legacy,"affected_revisions":len(bad),
        "legacy_path_revisions":len(old),"clean_path_revisions":len(new),
        "refs_examined":len(refs),"reachable_refs":reachable,
        "clean_ancestry_affected":False,"old_deploy_disabled":True,
        "historical_exposure_still_reachable":True,
        "all_host_refs_verified":False,"caches_or_clones_purged":False,
        "global_privacy_remediation_complete":False,"real_payments":False}
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--repo",default=".")
    a=p.parse_args()
    try:
        result=audit(Path(a.repo).resolve())
        dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,sort_keys=True))
    except (AuditError,OSError,ValueError,UnicodeError,subprocess.TimeoutExpired):
        print('{"result":"FAIL_CLOSED","raw_values_logged":false}',file=sys.stderr)
        sys.exit(2)
