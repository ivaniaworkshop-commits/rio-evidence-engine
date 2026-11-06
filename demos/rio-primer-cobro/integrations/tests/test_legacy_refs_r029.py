import subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_legacy_refs_r029 import audit,valid,retired,AuditError,PATH,WF
def git(repo,*args):
    return subprocess.run(["git","-C",str(repo),*args],check=True,
      stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode().strip()
def sample():
    prefix="".join(str(i%10) for i in range(17))
    total=sum((int(prefix[i])*(3,7,1)[i%3])%10 for i in range(17))
    return prefix+str((10-total%10)%10)
class R029Tests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.repo=Path(self.temp.name)
    git(self.repo,"init","-q")
    git(self.repo,"config","user.name","R029")
    git(self.repo,"config","user.email","ci@example.invalid")
    self.path=self.repo/PATH;self.path.parent.mkdir(parents=True)
    self.wf=self.repo/WF;self.wf.parent.mkdir(parents=True)
    self.path.write_text("safe")
    self.wf.write_text("jobs:\n  deploy:\n    if: false\n")
    self.commit();self.base=git(self.repo,"rev-parse","HEAD")
    git(self.repo,"checkout","-qb","old")
    self.path.write_text(sample());self.commit()
    self.path.write_text("fixed");self.commit()
    self.old="refs/heads/old"
    git(self.repo,"checkout","-qb","clean",self.base)
    self.path.write_text("sanitized");self.commit()
 def commit(self):
    git(self.repo,"add",".");git(self.repo,"commit","-qm","synthetic")
 def test_reachability(self):
    r=audit(self.repo,self.base,self.old)
    self.assertIn(self.old,r["reachable_refs"])
    self.assertFalse(r["global_privacy_remediation_complete"])
 def test_old_release_disabled(self):
    self.assertTrue(retired(self.repo,self.old))
 def test_disabled_job_guard_rejects_enabled(self):
    git(self.repo,"checkout","-q","old")
    self.wf.write_text("jobs:\n  deploy:\n    if: true\n")
    self.commit();git(self.repo,"checkout","-q","clean")
    with self.assertRaisesRegex(AuditError,"NOT_DISABLED"):
        audit(self.repo,self.base,self.old)
 def test_contaminated_clean_branch_rejected(self):
    with self.assertRaisesRegex(AuditError,"CLEAN_ANCESTRY"):
        audit(self.repo,self.base,self.old,self.old)
 def test_valid_checksum(self):
    self.assertTrue(valid(sample().encode()))
 def test_invalid_checksum(self):
    self.assertFalse(valid("".join(str(i%10) for i in range(18)).encode()))
 def test_report_never_includes_identifier(self):
    self.assertNotIn(sample(),str(audit(self.repo,self.base,self.old)))
if __name__=="__main__":unittest.main()
