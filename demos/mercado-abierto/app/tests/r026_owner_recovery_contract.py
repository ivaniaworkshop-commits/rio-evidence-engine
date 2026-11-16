"""R026 hermetic owner-recovery contract tests, no DB copies or network."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SVC = (ROOT / "rio_pey_codi" / "identity.py").read_text(encoding="utf-8")
HTML = (ROOT / "rio_pey_codi" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "rio_pey_codi" / "static" / "app.js").read_text(encoding="utf-8")
TREE = ast.parse(SVC)

def method(name):
    svc = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "AccountService")
    matches = [node for node in svc.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f"Missing or duplicate method {name}")
    return ast.get_source_segment(SVC, matches[0])

def route(name):
    func = method("foo") if False else next(
        n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name
        and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == "post" for d in n.decorator_list)
    )
    return ast.get_source_segment(SVC, func)

class OwnerRecoveryTests(unittest.TestCase):
    def test_owner_pin_deny_by_default(self):
        self.assertIn("return bool(owner and", method("can_invite"))
        self.assertIn("hmac.compare_digest(owner, identifier)", method("can_invite"))

    def test_admin_issuer_requires_owner_session(self):
        source = method("admin_reset_link")
        self.assertIn("if not self.can_invite(principal)", source)
        self.assertIn("self._session_access(db, principal, lock=True)", source)

    def test_admin_issuer_denies_owner_and_older_accounts(self):
        source = method("admin_reset_link")
        self.assertIn("not eligible_later_account(owner, target)", source)
        self.assertIn("HTTPException(404", source)

    def test_one_time_ttl_and_previous_token_invalidation(self):
        source = method("admin_reset_link")
        self.assertIn("self._token(db, target.id, 'admin_reset', 900)", source)
        self.assertIn("OneTimeToken.used_at.is_(None)", source)
        self.assertIn(".values(expires_at=t)", source)

    def test_token_is_not_password_and_url_has_fragment(self):
        source = method("admin_reset_link")
        self.assertIn("/reset-password#token={token}", source)
        self.assertNotIn("HASHER.hash(", source)

    def test_confirmation_requires_valid_unused_token(self):
        source = method("reset_confirm")
        self.assertIn("record.used_at is not None", source)
        self.assertIn("record.expires_at <= t", source)
        self.assertIn("claimed.rowcount != 1", source)

    def test_confirmation_revalidates_owner_order(self):
        source = method("reset_confirm")
        self.assertIn("not eligible_later_account(owner, user)", source)

    def test_confirmation_revokes_sessions_and_other_links(self):
        source = method("reset_confirm")
        self.assertIn("delete(SessionRow).where(SessionRow.user_id == user.id)", source)
        self.assertIn("('reset', 'admin_reset', 'owner_recovery')", source)
        self.assertIn("user.password_hash = HASHER.hash(password)", source)

    def test_original_owner_recovery_requires_pinned_identity(self):
        source = method("reset_confirm")
        self.assertIn("if purpose == 'owner_recovery':", source)
        self.assertIn("not self.platform_owner_id", source)
        self.assertIn("hmac.compare_digest(user.id, self.platform_owner_id)", source)
        self.assertIn("('reset', 'admin_reset', 'owner_recovery')", source)

    def test_email_reset_still_requires_delivery(self):
        source = method("reset_confirm")
        self.assertIn("if purpose not in ('admin_reset', 'owner_recovery'):", source)
        self.assertIn("self.require_email_delivery()", source)

    def test_endpoint_requires_csrf_and_server_owner_check(self):
        source = route("admin_reset_links")
        self.assertIn("svc.session(request, csrf=True)", source)
        self.assertIn("svc.can_invite(principal)", source)
        self.assertIn("svc.limit(request, 'admin-reset', req.email)", source)

    def test_reset_page_uses_form_not_password_prompt(self):
        self.assertIn('id="rio-password-reset-form"', HTML)
        self.assertIn("history.replaceState(null,'',isReset?'/reset-password':'/')", JS)
        self.assertNotIn("prompt('Ingresa una nueva contraseña", JS)
        self.assertIn("password!==confirmation", JS)

    def test_owner_panel_hidden_by_default(self):
        self.assertIn('id="rio-admin-recovery" hidden', HTML)
        self.assertIn("user.can_invite!==true", JS)
        self.assertIn("id=\"rio-admin-reset-form\"", HTML)

    def test_client_validates_server_reset_destination(self):
        self.assertIn("url.origin!==location.origin", JS)
        self.assertIn("url.pathname!=='/reset-password'", JS)
        self.assertIn("result.expires_in!==900", JS)

if __name__ == "__main__":
    unittest.main()
