import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_privacy_lineage_r028 import audit,PrivacyGuardError
PATH="demos/rio-primer-cobro/tests/test_pey_r027.mjs"
def git(repo,*args):
 return subprocess.run(["git","-C",str(repo),*args],check=True,
   stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode().strip()
class CleanLineageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.repo=Path(self.temp.name)
  git(self.repo,"init","-q")
  git(self.repo,"config","user.name","R028")
  git(self.repo,"config","user.email","ci@invalid.example")
  self.file=self.repo/PATH;self.file.parent.mkdir(parents=True)
  self.file.write_text("safe",encoding="utf-8");self.commit()
  self.base=git(self.repo,"rev-parse","HEAD")
 def commit(self):
  git(self.repo,"add",".");git(self.repo,"commit","-qm","fixture")
 def test_clean_commit_pass(self):
  self.file.write_text("still safe");self.commit()
  self.assertEqual(audit(self.repo,self.base,(PATH,))["new_commits"],1)
 def test_historical_exposure_detected_after_head_cleanup(self):
  candidate="".join(str(i%10) for i in range(18))
  self.file.write_text(candidate);self.commit()
  self.file.write_text("restored safe");self.commit()
  with self.assertRaisesRegex(PrivacyGuardError,"HISTORICAL_SENSITIVE_PATTERN"):
   audit(self.repo,self.base,(PATH,))
 def test_no_delta_rejected(self):
  with self.assertRaisesRegex(PrivacyGuardError,"SPAN_OUTSIDE_POLICY"):
   audit(self.repo,self.base,(PATH,))
 def test_missing_base_rejected(self):
  self.file.write_text("new");self.commit()
  with self.assertRaises(PrivacyGuardError):
   audit(self.repo,"0"*40,(PATH,))
 def test_orphan_branch_rejected(self):
  git(self.repo,"checkout","--orphan","other")
  self.file.write_text("other");self.commit()
  with self.assertRaises(PrivacyGuardError):
   audit(self.repo,self.base,(PATH,))
 def test_sensitive_value_not_in_error(self):
  candidate="".join(str(i%10) for i in range(18))
  self.file.write_text(candidate);self.commit()
  try:audit(self.repo,self.base,(PATH,))
  except PrivacyGuardError as error:self.assertNotIn(candidate,str(error))
if __name__=="__main__":unittest.main()
