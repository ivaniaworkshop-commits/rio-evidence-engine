#!/usr/bin/env python3
"""R017: verify and stage a deterministic, public, non-payable front desk."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parent
FILES = ("index.html", "app.html")
PUBLIC_REPO = "https://github.com/ivaniaworkshop-commits/rio-evidence-engine"

def verify(output):
    index = (SOURCE / "index.html").read_bytes()
    app = (SOURCE / "app.html").read_bytes()
    checks = {
        "entry_is_html": b"<!doctype html>" in index[:100].lower(),
        "app_is_html": b"<!doctype html>" in app[:100].lower(),
        "local_app_link": b'href="./app.html"' in index,
        "public_source_link": PUBLIC_REPO.encode("utf-8") in index,
        "educational_qr": b"RIO-QR-DEMO" in app and b"NO-PAGABLE" in app,
        "separate_app": index != app,
        "self_contained_app": b"<script" in app and b"<style" in app,
    }
    if not all(checks.values()):
        raise ValueError("release checks failed: " + json.dumps(checks))
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name in FILES:
        source = SOURCE / name
        target = output / name
        shutil.copyfile(source, target)
        payload = target.read_bytes()
        if payload != source.read_bytes():
            raise ValueError("staging byte mismatch: " + name)
        inventory.append({"path": name, "bytes": len(payload),
                          "sha256": hashlib.sha256(payload).hexdigest()})
    result = {"schema": "RIO_PRIMER_COBRO_RELEASE_R017",
              "result": "PASS_LOCAL_STATIC_RELEASE",
              "scope": "SOURCE_BYTE_IDENTITY_AND_STATIC_CHECKS_ONLY",
              "real_payments": False,
              "android_physical": "NOT_OBSERVED",
              "independent_unauth_browser": "NOT_OBSERVED",
              "checks": checks, "files": inventory}
    (output / "release-receipt.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="output/rio-primer-cobro")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(Path(args.output)), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(2)
