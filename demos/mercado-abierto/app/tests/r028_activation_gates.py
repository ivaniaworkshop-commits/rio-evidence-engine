"""RÍO R028: static contracts for activation gating; no secrets, DB or network."""
from pathlib import Path
import ast
import unittest

root=Path(__file__).resolve().parents[1]/"rio_pey_codi"
source=(root/"platform.py").read_text(encoding="utf8")
tree=ast.parse(source)
settings=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="Settings")
validate=next(x for x in settings.body if isinstance(x,ast.FunctionDef) and x.name=="validate")
validate_code=ast.get_source_segment(source,validate)

class ActivationGates(unittest.TestCase):
 def test_hosted_webhook_requires_provider_contract_attestation(self):
  self.assertIn("self.env != 'local' and (self.webhook_secret or self.webhook_previous_keys)", validate_code)
  self.assertIn("not self.webhook_attested",validate_code)
 def test_webhook_public_status_does_not_claim_enabled_without_attestation(self):
  self.assertIn("'webhook_enabled':ready and bool(cfg.webhook_secret) and not cfg.limited_launch and cfg.webhook_attested",source)
 def test_handler_denies_unsigned_and_unattested_events(self):
  self.assertIn("if not cfg.webhook_secret:raise HTTPException(503",source)
  self.assertIn("if cfg.env != 'local' and not cfg.webhook_attested:",source)
  self.assertIn("verify_and_capture(",source)
 def test_limited_launch_keeps_provider_credentials_closed(self):
  self.assertIn("or self.webhook_secret or self.webhook_previous_keys",validate_code)
  self.assertIn("if cfg.limited_launch:raise HTTPException(503,'Webhook desactivado temporalmente')",source)
 def test_provider_event_does_not_claim_bank_settlement(self):
  self.assertIn("'bank_settlement':'NOT_VERIFIED'",source)
 def test_signup_requires_authenticated_email_transport(self):
  self.assertIn("Limited registration requires complete authenticated SMTP",validate_code)
  self.assertIn("Hosted signup without email verification is forbidden",validate_code)
 def test_live_bank_payments_still_refused(self):
  self.assertIn("LIVE blocked pending production gates and operation authorization",validate_code)

if __name__=="__main__": unittest.main()
