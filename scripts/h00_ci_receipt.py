"""Emit self-reported, fail-closed GitHub Actions evidence receipts.

Runner-generated receipts prove neither independent evaluation nor authenticity.
Does not perform writes outside its explicit --output path.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "RIO_H00_CI_RECEIPT/1.0"
VERIFY_FILES = {
    "h08_independent_gate": "h08.json",
    "h11_blocked": "h11_blocked.json",
    "h11_h09": "h11_h09.json",
    "h11_legacy": "h11_legacy.json",
    "h12_power": "h12.json",
    "h14_development": "h14.json",
    "h14_paired": "h14_h11.json",
    "h14_freeze": "h14_freeze.json",
}


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate JSON key: " + key)
        data[key] = value
    return data


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _load_json(raw):
    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def _file_record(path):
    raw = path.read_bytes()
    if len(raw) > 4_000_000:
        raise ValueError("receipt input exceeds 4 MB")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, _load_json(raw)


def _verify_checks(data):
    return {
        "h08_independence_fail_closed": data["h08_independent_gate"]["status"] == "BLOCKED_NO_EXTERNAL_HOLDOUT"
            and data["h08_independent_gate"]["candidate_promoted"] is False,
        "h11_no_unearned_promotion": data["h11_blocked"]["status"] == "BLOCKED_NO_EVALUATION_INPUT"
            and data["h11_h09"]["candidate_promoted"] is False
            and data["h11_legacy"]["source_class_verified"] is False,
        "h12_no_unearned_promotion": data["h12_power"]["candidate_promoted"] is False,
        "h14_no_unearned_promotion": data["h14_development"]["candidate_promoted"] is False
            and data["h14_paired"]["candidate_promoted"] is False
            and data["h14_paired"]["source_class_verified"] is False,
        "h14_freeze_local_only": data["h14_freeze"]["status"] == "FROZEN_SOURCE_BYTES_MATCH_LOCAL_RECEIPT"
            and data["h14_freeze"]["candidate_promoted"] is False
            and data["h14_freeze"]["external_evaluator_authenticated"] is False,
    }


def _strict_checks(log_text):
    summaries = []
    for line in log_text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = _load_json(line)
                if isinstance(parsed, dict) and parsed.get("status") in {"PASS_NO_SKIPS", "FAIL_OR_SKIPPED"}:
                    summaries.append(parsed)
            except (ValueError, TypeError):
                continue
    if len(summaries) != 1:
        return {"exactly_one_strict_summary": False}, None
    summary = summaries[0]
    ok = (summary.get("status") == "PASS_NO_SKIPS"
          and type(summary.get("tests_run")) is int and summary["tests_run"] > 0
          and all(type(summary.get(k)) is int and summary[k] == 0 for k in ("failed", "errors", "skipped")))
    return {"strict_tests_pass_no_skips": ok}, summary


def _pull_request_context(env):
    """Bind PR head and base to checkout using the runner-supplied event JSON.

    Consistency only, not an external attestation. A missing or conflicting PR
    event is invalid; no PR identity is invented from GITHUB_SHA.
    """
    if env.get("GITHUB_EVENT_NAME") != "pull_request":
        return None, True
    try:
        raw = Path(env["GITHUB_EVENT_PATH"]).read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError("PR_EVENT_OVERSIZE")
        event = _load_json(raw)
        if not isinstance(event, dict):
            raise ValueError("PR_EVENT_NOT_OBJECT")
        pr = event["pull_request"]
        number = pr["number"]
        if type(number) is not int or number <= 0 or event["number"] != number:
            raise ValueError("PR_NUMBER_INVALID")
        if env.get("GITHUB_REF") != "refs/pull/{}/merge".format(number):
            raise ValueError("PR_REF_NUMBER_MISMATCH")
        repository = env["GITHUB_REPOSITORY"]
        if event["repository"]["full_name"] != repository or pr["base"]["repo"]["full_name"] != repository:
            raise ValueError("PR_REPOSITORY_MISMATCH")
        head_sha, base_sha = pr["head"]["sha"], pr["base"]["sha"]
        if any(re.fullmatch(r"[0-9a-f]{40}", sha) is None for sha in (head_sha, base_sha)):
            raise ValueError("PR_SOURCE_SHA_INVALID")
        event_merge_sha = pr.get("merge_commit_sha")
        if event_merge_sha is not None:
            if re.fullmatch(r"[0-9a-f]{40}", event_merge_sha) is None:
                raise ValueError("PR_EVENT_MERGE_SHA_INVALID")
            if event_merge_sha != env.get("GITHUB_SHA"):
                raise ValueError("PR_CHECKOUT_MERGE_SHA_MISMATCH")
        if env.get("GITHUB_HEAD_REF") and env["GITHUB_HEAD_REF"] != pr["head"]["ref"]:
            raise ValueError("PR_HEAD_REF_MISMATCH")
        if env.get("GITHUB_BASE_REF") and env["GITHUB_BASE_REF"] != pr["base"]["ref"]:
            raise ValueError("PR_BASE_REF_MISMATCH")
        return {
            "number": number, "head_sha": head_sha, "base_sha": base_sha,
            "head_repository": pr["head"]["repo"]["full_name"],
            "base_repository": repository, "checkout_sha": env.get("GITHUB_SHA"),
            "checkout_kind": "GITHUB_PR_SYNTHETIC_MERGE",
            "event_merge_sha": event_merge_sha,
        }, True
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("PR_"):
            reason = str(exc)
        elif isinstance(exc, KeyError):
            reason = "MISSING_FIELD_" + str(exc.args[0])[:32]
        else:
            reason = type(exc).__name__
        return {"status": "INVALID_PR_CONTEXT", "reason_code": reason}, False



def build_receipt(job, ci_status, input_dir, *, env=None):
    env = os.environ if env is None else env
    records, data, errors = {}, {}, []
    if job == "verify":
        for key, filename in VERIFY_FILES.items():
            try:
                records[key], data[key] = _file_record(input_dir / filename)
                if not isinstance(data[key], dict):
                    raise ValueError("top-level JSON must be object")
            except (OSError, ValueError, TypeError) as exc:
                records[key] = {"missing_or_invalid": True}
                errors.append(key + ": " + type(exc).__name__)
        try:
            checks = _verify_checks(data) if not errors else {}
        except (KeyError, TypeError, ValueError):
            checks = {"receipt_fields_valid": False}
            errors.append("required_evaluation_fields_missing_or_invalid")
    elif job == "strict-torch":
        path = input_dir / "h00_strict_tests.log"
        try:
            raw = path.read_bytes()
            if len(raw) > 4_000_000:
                raise ValueError("strict test log exceeds 4 MB")
            records["strict_suite_log"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            checks, data["strict_suite"] = _strict_checks(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            records["strict_suite_log"] = {"missing_or_invalid": True}
            checks = {"strict_suite_log_present": False}
            errors.append("strict_suite_log: " + type(exc).__name__)
    else:
        raise ValueError("unknown job")
    full_sha = env.get("GITHUB_SHA", "")
    context_ok = (re.fullmatch(r"[0-9a-f]{40}", full_sha) is not None
                  and env.get("GITHUB_REPOSITORY") == "ivaniaworkshop-commits/rio-evidence-engine"
                  and (env.get("GITHUB_RUN_ID", "").isdigit()))
    checks["github_context_present"] = context_ok
    pr_context, pr_context_ok = _pull_request_context(env)
    if env.get("GITHUB_EVENT_NAME") == "pull_request":
        checks["github_pr_context_consistent"] = pr_context_ok
        if not pr_context_ok:
            errors.append("github_pull_request_context_invalid")
    complete = ci_status == "success" and not errors and bool(checks) and all(checks.values())
    try:
        torch_version = importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        torch_version = None
    try:
        node_version = subprocess.run(["node", "--version"], check=True,
                                      capture_output=True, text=True, timeout=4).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        node_version = None
    return {
        "schema": SCHEMA,
        "evidence_authority": "CI_RUNNER_SELF_REPORTED_NOT_EXTERNAL_ATTESTATION",
        "stage": job,
        "status": "COMPLETE_LOCAL_CI_RECEIPT" if complete else "INCOMPLETE_OR_FAILED",
        "ci_job_status_reported": ci_status,
        "run": {
            "repository": env.get("GITHUB_REPOSITORY"), "sha": full_sha or None,
            "event": env.get("GITHUB_EVENT_NAME"), "ref": env.get("GITHUB_REF"),
            "id": env.get("GITHUB_RUN_ID"), "attempt": env.get("GITHUB_RUN_ATTEMPT"),
            "pull_request": pr_context,
        },
        "runtime": {"python": platform.python_version(), "node": node_version, "torch": torch_version},
        "input_records": records,
        "checks": checks,
        "errors": errors,
        "strict_suite": data.get("strict_suite") if job == "strict-torch" else None,
        "external_holdout_authenticated": False,
        "source_class_verified_externally": False,
        "candidate_promoted": False,
        "production_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", choices=["verify", "strict-torch"], required=True)
    parser.add_argument("--ci-status", required=True)
    parser.add_argument("--input-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_receipt(args.job, args.ci_status, args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "job": args.job, "status": report["status"],
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    # Preserve diagnostics on upstream failure, but reject missing evidence after a green job.
    return 2 if args.ci_status == "success" and report["status"] != "COMPLETE_LOCAL_CI_RECEIPT" else 0


if __name__ == "__main__":
    sys.exit(main())
