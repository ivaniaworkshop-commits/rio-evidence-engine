"""R027 no-clone, no-network regression for mandatory email and signed webhook gates.
Source-level contract checks; does not assert SMTP delivery or provider onboarding.
"""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
PLATFORM=(ROOT/"rio_pey_codi/platform.py").read_text()
IDENTITY=(ROOT/"rio_pey_codi/identity.py").read_text()
HTML=(ROOT/"rio_pey_codi/static/index.html").read_text()
JS=(ROOT/"rio_pey_codi/static/app.js").read_text()
ast.parse(PLATFORM);ast.parse(IDENTITY)

class MailAndWebhookPolicy(unittest.TestCase):
 def test_hosted_no_email_signups_rejected(self):
  self.assertIn("self.env != 'local' and self.self_signup_no_email",PLATFORM)
  self.assertIn("Hosted signup without email verification is forbidden",PLATFORM)
 def test_registration_requires_delivery(self):
  self.assertIn("if not self.self_signup_no_email:\n            self.require_email_delivery()",IDENTITY)
  self.assertIn("self.mailer.send('verify',mail,token)",IDENTITY)
 def test_unverified_login_denied(self):
  self.assertIn("raise HTTPException(403,'Account activation required')",IDENTITY)
 def test_verification_one_use_expiring(self):
  self.assertIn("OneTimeToken.purpose == 'verify'",IDENTITY)
  self.assertIn("OneTimeToken.used_at.is_(None)",IDENTITY)
  self.assertIn("OneTimeToken.expires_at > t",IDENTITY)
 def test_password_reset_request_has_mail_delivery(self):
  self.assertIn("def reset_request(self,email):",IDENTITY)
  self.assertIn("self.mailer.send('reset', mail, token)",IDENTITY)
 def test_undelivered_reset_link_invalidated(self):
  self.assertIn("OneTimeToken.token_hash == sha(token)",IDENTITY)
  self.assertIn("OneTimeToken.purpose == 'reset'",IDENTITY)
  self.assertIn(".values(expires_at=now())",IDENTITY)
 def test_password_reset_revokes_prior_sessions(self):
  self.assertIn("delete(SessionRow).where(SessionRow.user_id == user.id)",IDENTITY)
 def test_forgot_password_email_form_accessible(self):
  self.assertIn('id="forgot-password-form"',HTML)
  self.assertIn('id="forgot-email" name="email" type="email"',HTML)
  self.assertIn('id="forgot-password-status" role="status" aria-live="polite"',HTML)
  self.assertIn('id="reset-request" disabled',HTML)
  self.assertIn("$('forgot-password-form').addEventListener('submit'",JS)
 def test_no_prompts_for_recovery(self):
  self.assertNotIn("prompt('Correo de la cuenta')",JS)
  self.assertNotIn("Puedes registrarte sin correo de alta",JS)
 def test_frontend_fail_closed_without_email_provider(self):
  self.assertIn("h.password_reset_enabled===true",JS)
  self.assertIn("h.registration_enabled!==true",JS)
  self.assertIn("SMTP",JS)
 def test_signed_webhook_stays_closed_without_provider_key(self):
  self.assertIn("if not cfg.webhook_secret:raise HTTPException(503,'Webhook signing unavailable')",PLATFORM)
  self.assertIn("verify_and_capture(",PLATFORM)
  self.assertIn("and bool(cfg.webhook_secret) and not cfg.limited_launch",PLATFORM)
 def test_hosted_no_unsigned_webhooks(self):
  self.assertIn("if cfg.limited_launch:raise HTTPException(503,'Webhook desactivado temporalmente')",PLATFORM)
  self.assertIn("if len(request.headers['webhook-signature']) > 2048:",PLATFORM)

if __name__=="__main__": unittest.main()
