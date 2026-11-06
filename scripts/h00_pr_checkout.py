"""Verify pull-request merge checkout ancestry using real local Git objects.

This is runner-side consistency evidence, not independent authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.h00_ci_receipt import _pull_request_context

SCHEMA = "RIO_H00_PR_PARENT_BINDING/1.0"
PASS = "RUNNER_GIT_PARENT_BINDING_PASS"
SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        text=True, timeout=8,
    ).stdout.strip()


def verify_checkout(root: Path, env: dict) -> dict:
    report = {
        "schema": SCHEMA, "status": "BLOCKED", "reason_code": None,
        "authority": "RUNNER_GIT_OBJECT_AND_EVENT_NOT_INDEPENDENT",
        "run_id": env.get("GITHUB_RUN_ID"),
        "attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "checkout_sha": env.get("GITHUB_SHA"),
        "pr_number": None, "head_sha": None, "base_sha": None,
        "parent_shas": None, "event_merge_matches_checkout": None,
        "candidate_promoted": False, "production_ready": False,
        "external_holdout_authenticated": False,
    }
    if env.get("GITHUB_EVENT_NAME") != "pull_request":
        report["reason_code"] = "NOT_PR_EVENT"
        return report
    pr, ok = _pull_request_context(env)
    if not ok or not isinstance(pr, dict):
        report["reason_code"] = "INVALID_PR_EVENT_CONTEXT"
        return report
    report["pr_number"] = pr["number"]
    report["head_sha"] = pr["head_sha"]
    report["base_sha"] = pr["base_sha"]
    report["event_merge_matches_checkout"] = pr["event_merge_matches_checkout"]
    expected = env.get("GITHUB_SHA", "")
    if not SHA.fullmatch(expected):
        report["reason_code"] = "INVALID_GITHUB_SHA"
        return report
    try:
        if git(root, "rev-parse", "--verify", "HEAD") != expected:
            report["reason_code"] = "CHECKOUT_SHA_MISMATCH"
            return report
        if git(root, "cat-file", "-t", "HEAD") != "commit":
            report["reason_code"] = "NOT_COMMIT"
            return report
        # Raw commit headers retain parents even with fetch-depth: 1.
        headers = git(root, "cat-file", "-p", "HEAD").partition("\n\n")[0].splitlines()
        if not headers or not headers[0].startswith("tree "):
            report["reason_code"] = "COMMIT_HEADER_INVALID"
            return report
        parents = []
        for line in headers:
            if line.startswith("parent"):
                if not line.startswith("parent ") or not SHA.fullmatch(line[7:]):
                    report["reason_code"] = "PARENT_HEADER_INVALID"
                    return report
                parents.append(line[7:])
        report["parent_shas"] = parents
        if len(parents) != 2:
            report["reason_code"] = "PR_MERGE_PARENT_COUNT_INVALID"
        elif parents[0] != pr["base_sha"]:
            report["reason_code"] = "FIRST_PARENT_NOT_BASE"
        elif parents[1] != pr["head_sha"]:
            report["reason_code"] = "SECOND_PARENT_NOT_HEAD"
        else:
            report["status"] = PASS
        return report
    except subprocess.TimeoutExpired:
        report["reason_code"] = "GIT_TIMEOUT"
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        report["reason_code"] = "GIT_READ_FAILED"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify_checkout(Path.cwd(), dict(os.environ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    args.output.write_bytes(raw)
    print(json.dumps({
        "schema": SCHEMA, "status": result["status"],
        "reason_code": result["reason_code"],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, sort_keys=True))
    return 0 if result["status"] == PASS else 2


if __name__ == "__main__":
    sys.exit(main())
