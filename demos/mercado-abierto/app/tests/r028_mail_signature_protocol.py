"""RÍO R028: isolated executable tests of Mailer and HMAC verifier.

No database, no network, no email delivery, no provider account.
Tests protocol implementation, NOT proof of actual SMTP or pey contract.
"""
from __future__ import annotations
import ast
import base64
import dataclasses
from email.message import EmailMessage
import importlib.util
from pathlib import Path
import re
import smtplib
import ssl
import sys
import unittest
from urllib.parse import quote, urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1] / "rio_pey_codi"
SOURCE = (ROOT / "identity.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
MAIL_CLASSES = [node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name in ("EmailConfig", "Mailer")]
assert len(MAIL_CLASSES) == 2
MAIL_NS = dict(
    dataclass=dataclasses.dataclass, field=dataclasses.field, EmailMessage=EmailMessage,
    quote=quote, ssl=ssl, smtplib=smtplib,
)
exec(compile(ast.Module(body=MAIL_CLASSES, type_ignores=[]), str(ROOT / "identity.py"), "exec"), MAIL_NS)
EmailConfig = MAIL_NS["EmailConfig"]
Mailer = MAIL_NS["Mailer"]
spec = importlib.util.spec_from_file_location("rio_signatures_r028", ROOT / "signatures.py")
sig = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sig
spec.loader.exec_module(sig)

class FakeSMTP:
    last = None
    def __init__(self, host, port, timeout=10, context=None):
        assert host == "smtp.example.test"
        assert port in (465, 587)
        assert timeout == 10
        self.sent = []
        self.user = None
        self.encrypted = port == 465
        FakeSMTP.last = self
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def ehlo(self): pass
    def starttls(self, context=None): self.encrypted = True
    def login(self, username, password):
        assert self.encrypted
        assert (username, password) == ("sender", "SYNTHETIC_NOT_REAL")
        self.user = username
    def send_message(self, message):
        assert self.encrypted and self.user == "sender"
        self.sent.append(message)

class MailerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.smtp = smtplib.SMTP
        self.smtp_ssl = smtplib.SMTP_SSL
        smtplib.SMTP = FakeSMTP
        smtplib.SMTP_SSL = FakeSMTP
        self.addCleanup(self.restore)
        self.config = EmailConfig(mode="smtp", public_url="https://app.example.test",
                                  host="smtp.example.test", port=587,
                                  username="sender", password="SYNTHETIC_NOT_REAL",
                                  sender="no-reply@example.test")
    def restore(self):
        smtplib.SMTP = self.smtp
        smtplib.SMTP_SSL = self.smtp_ssl
    def test_verification_email_has_https_fragment_token(self):
        mail = Mailer(self.config)
        mail.send("verify", "user@example.test", "synthetic_token_123")
        message = FakeSMTP.last.sent[0]
        body = message.get_content()
        self.assertIn("https://app.example.test/verify-email#token=synthetic_token_123", body)
        self.assertEqual(message["To"], "user@example.test")
        self.assertEqual(message["From"], "no-reply@example.test")
    def test_password_reset_email_has_reset_path(self):
        Mailer(self.config).send("reset", "user@example.test", "another_token_123")
        self.assertIn("/reset-password#token=another_token_123", FakeSMTP.last.sent[0].get_content())
    def test_starttls_and_login_required(self):
        Mailer(self.config).send("verify", "user@example.test", "token")
        self.assertTrue(FakeSMTP.last.encrypted)
        self.assertEqual(FakeSMTP.last.user, "sender")
    def test_smtps_port_465(self):
        cfg = dataclasses.replace(self.config, port=465)
        Mailer(cfg).send("reset", "user@example.test", "token")
        self.assertTrue(FakeSMTP.last.encrypted)
        self.assertEqual(FakeSMTP.last.user, "sender")
    def test_disabled_mail_is_rejected(self):
        with self.assertRaises(smtplib.SMTPException):
            Mailer(dataclasses.replace(self.config, mode="disabled")).send("verify", "x@example.test", "t")
    def test_sender_and_https_required(self):
        with self.assertRaises(ValueError):
            Mailer(dataclasses.replace(self.config, public_url="http://localhost"))
        with self.assertRaises(ValueError):
            Mailer(dataclasses.replace(self.config, sender=""))
    def test_no_token_in_reset_link_query(self):
        Mailer(self.config).send("reset", "u@example.test", "test_token_ABC")
        m = re.search(r"https://[^\s]+", FakeSMTP.last.sent[0].get_content())
        parsed = urlparse(m.group(0))
        self.assertEqual(parsed.query, "")
        self.assertEqual(parse_qs(parsed.fragment)["token"], ["test_token_ABC"])

class HmacProtocolTests(unittest.TestCase):
    SECRET = "whsec_" + base64.b64encode(bytes(range(32))).decode("ascii")
    BODY = b'{"type":"codi.qr.payment_received","test":true}'
    TIME = 1794410000
    def make_headers(self, *, body=None, timestamp=None):
        b = self.BODY if body is None else body
        t = self.TIME if timestamp is None else timestamp
        return {"webhook-id":"evt_test_001", "webhook-timestamp":str(t),
                "webhook-signature":sig.make_signature(self.SECRET,"evt_test_001",t,b)}
    def test_signature_passes_when_bytes_match(self):
        self.assertEqual(sig.verify_signature(self.make_headers(),self.BODY,self.SECRET,now=self.TIME),"evt_test_001")
    def test_signature_rejects_mutated_body(self):
        with self.assertRaises(sig.InvalidWebhook):
            sig.verify_signature(self.make_headers(),self.BODY+b" ",self.SECRET,now=self.TIME)
    def test_signature_rejects_wrong_key(self):
        wrong="whsec_"+base64.b64encode(bytes(range(32,64))).decode("ascii")
        with self.assertRaises(sig.InvalidWebhook):
            sig.verify_signature(self.make_headers(),self.BODY,wrong,now=self.TIME)
    def test_signature_rejects_old_timestamp(self):
        with self.assertRaises(sig.InvalidWebhook):
            sig.verify_signature(self.make_headers(),self.BODY,self.SECRET,now=self.TIME+301)
    def test_signature_rejects_future_timestamp(self):
        with self.assertRaises(sig.InvalidWebhook):
            sig.verify_signature(self.make_headers(timestamp=self.TIME+301),self.BODY,self.SECRET,now=self.TIME)
    def test_signature_rejects_missing_metadata(self):
        headers=self.make_headers()
        del headers["webhook-signature"]
        with self.assertRaises(sig.InvalidWebhook):
            sig.verify_signature(headers,self.BODY,self.SECRET,now=self.TIME)
    def test_signature_captures_nonsecret_evidence(self):
        event_id, evidence=sig.verify_and_capture(self.make_headers(),self.BODY,self.SECRET,"pey-contract-unverified",now=self.TIME)
        self.assertEqual(event_id,"evt_test_001")
        self.assertEqual(evidence.key_ref,"pey-contract-unverified")
        self.assertEqual(evidence.timestamp,self.TIME)
        self.assertNotIn(self.SECRET,repr(evidence))
    def test_keyring_rejects_too_short_key(self):
        short="whsec_"+base64.b64encode(b"small").decode("ascii")
        with self.assertRaises(ValueError):
            sig.validate_webhook_keyring("candidate",short,())
    def test_keyring_accepts_synthetic_key(self):
        sig.validate_webhook_keyring("candidate",self.SECRET,())
    def test_tampered_signature_rejected(self):
        headers=self.make_headers()
        headers["webhook-signature"]="v1,"+base64.b64encode(bytes(32)).decode("ascii")
        with self.assertRaises(sig.InvalidWebhook):
            sig.verify_signature(headers,self.BODY,self.SECRET,now=self.TIME)

if __name__ == "__main__":
    unittest.main()
