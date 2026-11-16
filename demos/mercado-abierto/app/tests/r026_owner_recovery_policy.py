"""Unit tests for the owner account chronological boundary, without DB or network."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SRC=Path(__file__).resolve().parents[1]/"rio_pey_codi"/"owner_recovery_policy.py"
SPEC=importlib.util.spec_from_file_location("owner_recovery_policy_r026",SRC)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

def u(identifier, created):
    return SimpleNamespace(id=identifier,created_at=created)

class AccountBoundaryTests(unittest.TestCase):
    def test_later_account_pass(self):
        self.assertTrue(mod.eligible_later_account(u("owner",10),u("later",11)))
    def test_owner_self_fails(self):
        self.assertFalse(mod.eligible_later_account(u("owner",10),u("owner",15)))
    def test_older_account_fails(self):
        self.assertFalse(mod.eligible_later_account(u("owner",10),u("older",9)))
    def test_same_second_fails_closed(self):
        self.assertFalse(mod.eligible_later_account(u("owner",10),u("other",10)))
    def test_missing_owner_fails(self):
        self.assertFalse(mod.eligible_later_account(None,u("other",99)))
    def test_missing_account_fails(self):
        self.assertFalse(mod.eligible_later_account(u("owner",1),None))
    def test_noninteger_time_fails(self):
        self.assertFalse(mod.eligible_later_account(u("owner",1),u("other","2")))
        self.assertFalse(mod.eligible_later_account(u("owner",True),u("other",2)))
    def test_invalid_identity_fails(self):
        self.assertFalse(mod.eligible_later_account(u("",1),u("target",2)))
        self.assertFalse(mod.eligible_later_account(u("owner",1),u("",2)))
    def test_missing_attributes_fails(self):
        self.assertFalse(mod.eligible_later_account(SimpleNamespace(id="owner"),u("other",2)))

if __name__ == "__main__":
    unittest.main()
