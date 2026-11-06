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
def sample_valid_numeric():
 prefix="".join(str(i%10) for i in range(17))
 w=(3,7,1)
 digit=(10-sum((int(prefix[i])*w[i%3])%10 for i in range(17))%10)%10
 return prefix+str(digit)
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
  candidate=sample_valid_numeric()
  self.file.write_text(candidate);self.commit()
  self.file.write_text("restored safe");self.commit()
  with self.assertRaisesRegex(PrivacyGuardError,"HISTORICAL_CLABE_PATTERN"):
   audit(self.repo,self.base,(PATH,))
 def test_non_checksum_numeric_reference_is_still_rejected(self):
  candidate="".join(str(i%10) for i in range(18))
  self.file.write_text(candidate);self.commit()
  with self.assertRaisesRegex(PrivacyGuardError,"HISTORICAL_18DIGIT_IDENTIFIER"):
   audit(self.repo,self.base,(PATH,))
 def install_reviewed_fixture(self):
  from verify_privacy_lineage_r028 import REVIEWED_FIXTURE_PATH,REVIEWED_FIXTURE_BLOB
  original=Path(__file__).resolve().parents[2]/"tests"/"test_pey_r026.mjs"
  dest=self.repo/REVIEWED_FIXTURE_PATH
  dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_bytes(original.read_bytes())
  self.commit()
  self.assertEqual(git(self.repo,"hash-object",REVIEWED_FIXTURE_PATH),REVIEWED_FIXTURE_BLOB)
  return dest,git(self.repo,"rev-parse","HEAD"),REVIEWED_FIXTURE_PATH
 def test_exact_unchanged_legacy_fixture_allowed_only_by_blob(self):
  dest,base,legacy=self.install_reviewed_fixture()
  self.file.write_text("safe new source",encoding="utf-8");self.commit()
  result=audit(self.repo,base,(PATH,legacy))
  self.assertEqual(result["reviewed_fixture_reuses"],2)
  self.assertEqual(result["status"],"PASS_SELECTED_PATH_HISTORY")
 def test_modified_legacy_fixture_is_reexamined(self):
  dest,base,legacy=self.install_reviewed_fixture()
  dest.write_bytes(dest.read_bytes()+bytes([10])+b"// reviewed fixture edited"+bytes([10]))
  self.commit()
  with self.assertRaisesRegex(PrivacyGuardError,"HISTORICAL_18DIGIT_IDENTIFIER"):
   audit(self.repo,base,(PATH,legacy))
 def test_unreviewed_base_cannot_claim_fixture_exception(self):
  dest,base,legacy=self.install_reviewed_fixture()
  dest.write_text("safe unrelated fixture",encoding="utf-8");self.commit()
  new_base=git(self.repo,"rev-parse","HEAD")
  self.file.write_text("safe progression",encoding="utf-8");self.commit()
  with self.assertRaisesRegex(PrivacyGuardError,"REVIEWED_FIXTURE_BASE_MISMATCH"):
   audit(self.repo,new_base,(PATH,legacy))
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
  candidate=sample_valid_numeric()
  self.file.write_text(candidate);self.commit()
  try:audit(self.repo,self.base,(PATH,))
  except PrivacyGuardError as error:self.assertNotIn(candidate,str(error))
if __name__=="__main__":unittest.main()
