"""R030-A deterministic gate tests. No network, secrets, DB, or credential activation."""
import ast
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import unittest

SRC = (Path(__file__).resolve().parents[1]/"rio_pey_codi"/"platform.py").read_text()
TREE = ast.parse(SRC)
NODE = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name=="Settings")
NS={"dataclass":dataclass,"field":field,"os":os,"re":re,
    "parse_previous_webhook_keys": lambda _: (),
    "validate_webhook_keyring": lambda *args: None,
    "valid_readonly_token": lambda _: True}
exec(compile(ast.Module(body=[NODE],type_ignores=[]), "<isolated-settings>", "exec"), NS)
Settings=NS["Settings"]

def settings(**overrides):
    base=dict(env="staging",mode="DEMO",limited_launch=True,
        limited_registration_enabled=True,self_signup_no_email=False,
        email_mode="smtp",public_url="https://example.test",origin="https://example.test",
        smtp_host="smtp.example.test",smtp_port=465,smtp_user="test_sender",
        smtp_password="SYNTHETIC_ONLY",smtp_sender="no-reply@example.test",
        database_url="postgresql+psycopg://test:fake@localhost/example",auto_create=False,
        webhook_key_ref="provider-unverified")
    base.update(overrides)
    return Settings(**base)

class MailActivationGate(unittest.TestCase):
    def test_no_attestation_denies_fully_configured_smtp(self):
        with self.assertRaisesRegex(ValueError,"Email delivery evidence required"):
            settings().validate()
    def test_explicit_attestation_allows_synthetic_valid_configuration(self):
        settings(email_delivery_attested=True).validate()
    def test_attestation_not_substitute_for_smtp_password(self):
        with self.assertRaisesRegex(ValueError,"Limited registration requires complete authenticated SMTP"):
            settings(email_delivery_attested=True,smtp_password="").validate()
    def test_attestation_not_substitute_for_smtp_host(self):
        with self.assertRaisesRegex(ValueError,"Limited registration requires complete authenticated SMTP"):
            settings(email_delivery_attested=True,smtp_host="").validate()
    def test_attestation_not_substitute_for_sender(self):
        with self.assertRaisesRegex(ValueError,"Limited registration requires complete authenticated SMTP"):
            settings(email_delivery_attested=True,smtp_sender="").validate()
    def test_attestation_not_substitute_for_email_verification(self):
        with self.assertRaises(ValueError):
            settings(email_delivery_attested=True,self_signup_no_email=True).validate()
    def test_attestation_without_registration_leaves_registration_disabled(self):
        settings(email_delivery_attested=False,limited_registration_enabled=False).validate()
    def test_production_same_gate(self):
        with self.assertRaisesRegex(ValueError,"Email delivery evidence required"):
            settings(env="production").validate()
    def test_env_binding_is_explicit_and_opt_in(self):
        self.assertIn("flag('RPG_EMAIL_DELIVERY_ATTESTED')",SRC)
    def test_status_never_confuses_attestation_with_observed_delivery(self):
        self.assertIn("'email_delivery_verified':False",SRC)
        self.assertIn("'email_delivery_attested':bool(cfg.email_delivery_attested)",SRC)

if __name__=="__main__":unittest.main()
