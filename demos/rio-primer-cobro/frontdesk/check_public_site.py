#!/usr/bin/env python3
"""R018: read a public static site without auth and distinguish HTTP from browser evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

FILES = {"/": "index.html", "/app.html": "app.html"}
DEFAULT_URL = "https://rio-primer-cobro-frontdesk.vercel.app"
MAX_BYTES = 2_000_000

class RedirectOnSameHost(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        a, b = urlparse(request.full_url), urlparse(newurl)
        if (a.scheme, a.netloc) != (b.scheme, b.netloc):
            raise ValueError("REDIRECT_DIFFERENT_ORIGIN")
        return super().redirect_request(request, fp, code, msg, headers, newurl)

def valid_base(url, allow_local=False):
    p = urlparse(url)
    safe_local = allow_local and p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost")
    safe_public = p.scheme == "https" and p.hostname is not None and (
        p.hostname == "rio-primer-cobro-frontdesk.vercel.app" or p.hostname.endswith(".vercel.app"))
    if not (safe_local or safe_public) or p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise ValueError("BAD_BASE_URL")
    return url.rstrip("/")

def download(opener, url, timeout):
    req = Request(url, headers={
        "User-Agent": "RIO-Independent-HTTP-R018/1.0",
        "Accept": "text/html",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
    })
    with opener.open(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP_{resp.status}")
        content_type = resp.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            raise ValueError("UNEXPECTED_CONTENT_TYPE")
        data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("RESPONSE_TOO_LARGE")
        if b"<!doctype html>" not in data[:160].lower():
            raise ValueError("HTML_DOCTYPE_MISSING")
        if b"Vercel Authentication" in data or b"Sign in to Vercel" in data:
            raise ValueError("AUTHENTICATION_PAGE")
        return data

def probe(base_url=DEFAULT_URL, source=None, mode="access", allow_local=False,
          timeout=15.0, attempts=3):
    base = valid_base(base_url, allow_local=allow_local)
    if mode not in ("access", "exact"):
        raise ValueError("BAD_MODE")
    if mode == "exact" and not source:
        raise ValueError("SOURCE_REQUIRED_FOR_EXACT")
    opener = build_opener(RedirectOnSameHost())
    paths = []
    for route, name in FILES.items():
        last_error = None
        for turn in range(attempts):
            try:
                body = download(opener, base + route, timeout)
                if mode == "exact":
                    expected = (Path(source) / name).read_bytes()
                    if body != expected:
                        raise ValueError("PUBLIC_BYTES_DIFFER_FROM_RELEASE")
                paths.append({"route": route, "http_status": 200,
                              "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                              "matches_source": True if mode == "exact" else "NOT_CHECKED"})
                break
            except (HTTPError, URLError, OSError, ValueError) as exc:
                last_error = str(exc)
                if turn < attempts - 1:
                    time.sleep(1)
        else:
            raise ValueError("PUBLIC_READBACK_FAILED " + route + ": " + str(last_error))
    return {"schema": "RIO_ANONYMOUS_HTTP_R018_V1", "result": "PASS",
            "origin": base, "mode": mode, "authorization_header": "NOT_SENT",
            "cookie_header": "NOT_SENT", "external_HTTP_from_runner": "OBSERVED_BY_CALLER",
            "browser_UI": "NOT_OBSERVED", "android_physical": "NOT_OBSERVED",
            "bank_payments": "NOT_SUPPORTED", "pages": paths}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=DEFAULT_URL)
    p.add_argument("--source", default=None)
    p.add_argument("--mode", choices=("access", "exact"), default="access")
    p.add_argument("--allow-local", action="store_true")
    p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--timeout", type=float, default=15)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    try:
        result = probe(base_url=args.base_url, source=args.source, mode=args.mode,
                       allow_local=args.allow_local, timeout=args.timeout,
                       attempts=max(1, min(6, args.attempts)))
    except (ValueError, OSError) as exc:
        result = {"schema": "RIO_ANONYMOUS_HTTP_R018_V1", "result": "FAIL", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
