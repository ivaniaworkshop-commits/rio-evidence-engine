"""Regression checks for frontdesk CSP compatibility (no browser or payments required)."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTDESK = ROOT / "demos" / "rio-primer-cobro" / "frontdesk"
ASSETS = (
    "practica-r015-logic.js",
    "practica-r015-chat.js",
    "practica-r015-qrcode.js",
    "practica-r015-persistence.js",
    "practica-r015-app.js",
    "practica-r015-field.js",
)
HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Content-Security-Policy":
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'",
}


class FrontdeskCSPTests(unittest.TestCase):
    def test_vercel_headers_are_exact_and_global(self):
        policy = json.loads((FRONTDESK / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(len(policy["headers"]), 1)
        entry = policy["headers"][0]
        self.assertEqual(entry["source"], "/(.*)")
        headers = entry["headers"]
        self.assertEqual(len(headers), len(HEADERS))
        self.assertEqual({item["key"]: item["value"] for item in headers}, HEADERS)

    def test_practice_has_no_inline_script_style_or_handlers(self):
        html = (FRONTDESK / "practica.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r"<script\b(?![^>]*\bsrc=)[^>]*>")
        self.assertNotRegex(html, r"<style\b")
        self.assertNotRegex(html, r"\bon(?:click|change|input|load|error|submit)\s*=")
        self.assertNotRegex(html, r"\bstyle\s*=")

    def test_same_origin_asset_dependencies_preserve_order(self):
        html = (FRONTDESK / "practica.html").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="practica-r015-style.css">', html)
        found = re.findall(r'<script src="([^"]+)"', html)
        self.assertEqual(found, list(ASSETS))
        for asset in ("practica-r015-style.css", *ASSETS):
            self.assertRegex(asset, r"^[a-z0-9.-]+$")
            path = FRONTDESK / asset
            self.assertTrue(path.is_file(), asset)
            self.assertGreater(path.stat().st_size, 100, asset)


if __name__ == "__main__":
    unittest.main()
