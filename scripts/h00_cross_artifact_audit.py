"""RÍO R021: read-only cross-job GitHub Actions evidence consistency auditor.

A matching pair of self-reported CI artifacts is NOT independent authentication,
review approval, branch protection, or a production release. No network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile

SCHEMA = "RIO_H00_CROSS_ARTIFACT_AUDIT/1.0"
SUCCESS = "CONSISTENT_SELF_REPORTED_NOT_INDEPENDENT"
MAX_ZIP_FILES = 64
MAX_FILE_BYTES = 4_000_000
MAX_UNCOMPRESSED_BYTES = 8_000_000
MAX_COMPRESSION_RATIO = 300


class AuditError(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(value):
    raise AuditError("NONFINITE_JSON_NUMBER")


def parse_json(raw: bytes) -> dict:
    try:
        result = json.loads(raw, object_pairs_hook=_unique_pairs,
                            parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AuditError("INVALID_JSON:" + type(exc).__name__) from exc
    if type(result) is not dict:
        raise AuditError("JSON_TOP_LEVEL_NOT_OBJECT")
    return result


def _archive(path: Path, expected_digest: str | None) -> tuple[dict, str]:
    if path.stat().st_size > 16_000_000:
        raise AuditError("ZIP_CONTAINER_SIZE_LIMIT")
    raw_sha = digest(path.read_bytes())
    if expected_digest is not None and raw_sha != expected_digest:
        raise AuditError("ARCHIVE_DIGEST_MISMATCH")
    entries = {}
    try:
        with zipfile.ZipFile(path) as z:
            members = z.infolist()
            if len(members) > MAX_ZIP_FILES:
                raise AuditError("ZIP_ENTRY_LIMIT")
            if sum(i.file_size for i in members) > MAX_UNCOMPRESSED_BYTES:
                raise AuditError("ZIP_TOTAL_SIZE_LIMIT")
            for i in members:
                name = i.filename
                parts = PurePosixPath(name).parts
                if (not name or "\\" in name or name.startswith("/") or
                        any(p in ("", ".", "..") for p in name.split("/")) or
                        not parts or name in entries):
                    raise AuditError("UNSAFE_OR_DUPLICATE_ZIP_PATH")
                if stat.S_ISLNK(i.external_attr >> 16):
                    raise AuditError("ZIP_SYMLINK_FORBIDDEN")
                if i.is_dir():
                    continue
                if i.file_size > MAX_FILE_BYTES:
                    raise AuditError("ZIP_MEMBER_SIZE_LIMIT")
                if i.file_size and i.file_size / max(i.compress_size, 1) > MAX_COMPRESSION_RATIO:
                    raise AuditError("ZIP_COMPRESSION_RATIO_LIMIT")
                content = z.read(i)
                if len(content) != i.file_size:
                    raise AuditError("ZIP_MEMBER_LENGTH_MISMATCH")
                entries[name] = content
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
        raise AuditError("ZIP_READ_FAILURE:" + type(exc).__name__) from exc
    return entries, raw_sha



def repack_directory(source: Path, destination: Path) -> None:
    """Repack same-run extracted Actions artifacts as bounded ZIP input.

    The digest of this newly generated ZIP is local, not the original GitHub
    artifact digest. Never follow symlinks or execute extracted content.
    """
    source = Path(source)
    if not source.is_dir() or source.is_symlink():
        raise AuditError("ARTIFACT_DIRECTORY_NOT_REGULAR")
    entries = sorted(source.rglob("*"))
    if len(entries) > MAX_ZIP_FILES:
        raise AuditError("ARTIFACT_DIRECTORY_ENTRY_LIMIT")
    total = 0
    for p in entries:
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise AuditError("ARTIFACT_DIRECTORY_UNSAFE_ENTRY")
        if p.is_file():
            size = p.stat().st_size
            if size > MAX_FILE_BYTES:
                raise AuditError("ARTIFACT_DIRECTORY_MEMBER_SIZE_LIMIT")
            total += size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise AuditError("ARTIFACT_DIRECTORY_TOTAL_SIZE_LIMIT")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in entries:
            if p.is_file():
                rel = p.relative_to(source).as_posix()
                if ".." in PurePosixPath(rel).parts:
                    raise AuditError("UNSAFE_DIRECTORY_MEMBER_NAME")
                z.write(p, arcname=rel)


def _item(entries: dict, name: str) -> bytes:
    expected_suffix = "/output/h00/" + name
    matches = [v for p, v in entries.items() if p.endswith(expected_suffix) or p == "output/h00/" + name]
    if len(matches) != 1:
        raise AuditError("REQUIRED_ZIP_MEMBER_MISSING_OR_AMBIGUOUS:" + name)
    return matches[0]


def _must(condition: bool, reason: str) -> None:
    if not condition:
        raise AuditError(reason)


def _flags_false(d: dict) -> bool:
    return all(d.get(k) is False for k in
               ("candidate_promoted", "production_ready", "external_holdout_authenticated"))


def inspect(verify_zip: Path, strict_zip: Path, *, expected_run_id: str | None = None,
            expected_head_sha: str | None = None,
            expected_checkout_sha: str | None = None,
            expected_verify_zip_sha256: str | None = None,
            expected_strict_zip_sha256: str | None = None) -> dict:
    """Cross-compare two post-run archives, optionally pinned to observed GitHub identifiers."""
    v, vsha = _archive(Path(verify_zip), expected_verify_zip_sha256)
    s, ssha = _archive(Path(strict_zip), expected_strict_zip_sha256)
    _must(vsha != ssha, "SAME_ARCHIVE_USED_FOR_BOTH_JOBS")
    verify = parse_json(_item(v, "verify-receipt.json"))
    strict = parse_json(_item(s, "strict-receipt.json"))
    vp = _item(v, "pr-checkout.json")
    sp = _item(s, "pr-checkout.json")
    _must(vp == sp, "PARENT_PROOF_BYTES_DIFFER_ACROSS_JOBS")
    proof = parse_json(vp)
    _must(proof.get("schema") == "RIO_H00_PR_PARENT_BINDING/1.0", "PARENT_PROOF_SCHEMA_INVALID")
    _must(proof.get("status") == "RUNNER_GIT_PARENT_BINDING_PASS", "PARENT_PROOF_NOT_PASS")
    _must(proof.get("authority") == "RUNNER_GIT_OBJECT_AND_EVENT_NOT_INDEPENDENT", "PARENT_PROOF_AUTHORITY_INVALID")
    _must(proof.get("reason_code") is None and _flags_false(proof), "PARENT_PROOF_PROMOTION_OR_ERROR")
    for stage, receipt in (("verify", verify), ("strict-torch", strict)):
        _must(receipt.get("schema") == "RIO_H00_CI_RECEIPT/1.0", "RECEIPT_SCHEMA_INVALID:" + stage)
        _must(receipt.get("stage") == stage, "RECEIPT_STAGE_INVALID:" + stage)
        _must(receipt.get("status") == "COMPLETE_LOCAL_CI_RECEIPT", "RECEIPT_INCOMPLETE:" + stage)
        _must(receipt.get("evidence_authority") == "CI_RUNNER_SELF_REPORTED_NOT_EXTERNAL_ATTESTATION", "RECEIPT_AUTHORITY_INVALID")
        _must(receipt.get("ci_job_status_reported") == "success", "UPSTREAM_NOT_SUCCESS")
        _must(_flags_false(receipt) and receipt.get("source_class_verified_externally") is False,
              "RECEIPT_UNEARNED_PROMOTION:" + stage)
        checks = receipt.get("checks", {})
        _must(isinstance(checks, dict) and checks and all(value is True for value in checks.values()),
              "RECEIPT_CHECKS_NOT_ALL_TRUE:" + stage)
        record = receipt.get("input_records", {}).get("pr_checkout", {})
        _must(record.get("bytes") == len(vp) and record.get("sha256") == digest(vp),
              "PARENT_PROOF_DIGEST_MISMATCH:" + stage)
        run = receipt.get("run", {})
        pr = run.get("pull_request", {})
        _must(run.get("event") == "pull_request", "RECEIPT_NOT_PR:" + stage)
        _must(pr.get("checkout_parent_binding") == "RUNNER_REPORT_CONSISTENT_NOT_INDEPENDENT",
              "PARENT_BINDING_STATUS_MISSING:" + stage)
        _must(pr.get("parent_binding_report_sha256") == digest(vp), "PR_PROOF_DIGEST_LINK_MISSING:" + stage)
        _must(proof.get("run_id") == run.get("id") and proof.get("attempt") == run.get("attempt"),
              "PR_RUN_IDENTITY_MISMATCH:" + stage)
        _must(proof.get("pr_number") == pr.get("number") and type(pr.get("number")) is int,
              "PR_NUMBER_MISMATCH:" + stage)
        _must(proof.get("checkout_sha") == run.get("sha") == pr.get("checkout_sha"),
              "PR_CHECKOUT_IDENTITY_MISMATCH:" + stage)
        _must(proof.get("head_sha") == pr.get("head_sha") and
              proof.get("base_sha") == pr.get("base_sha"), "PR_SOURCE_IDENTITY_MISMATCH:" + stage)
        _must(proof.get("parent_shas") == [pr.get("base_sha"), pr.get("head_sha")],
              "PR_PARENTS_MISMATCH:" + stage)
    _must(verify["run"] == strict["run"], "CROSS_JOB_RUN_CONTEXT_MISMATCH")
    summary = strict.get("strict_suite") or {}
    _must(summary.get("status") == "PASS_NO_SKIPS" and
          type(summary.get("tests_run")) is int and summary["tests_run"] > 0 and
          all(type(summary.get(x)) is int and summary[x] == 0 for x in ("failed", "errors", "skipped")),
          "STRICT_SUITE_SUMMARY_NOT_PASS")
    run = verify["run"]
    if expected_run_id is not None:
        _must(str(run.get("id")) == expected_run_id, "EXPECTED_RUN_ID_MISMATCH")
    if expected_head_sha is not None:
        _must(run["pull_request"]["head_sha"] == expected_head_sha, "EXPECTED_HEAD_SHA_MISMATCH")
    if expected_checkout_sha is not None:
        _must(run["sha"] == expected_checkout_sha, "EXPECTED_CHECKOUT_SHA_MISMATCH")
    return {
        "schema": SCHEMA, "status": SUCCESS,
        "authority": "OFFLINE_CROSS_ARTIFACT_CONSISTENCY_NOT_INDEPENDENT_REVIEW",
        "run_id": run["id"], "attempt": run["attempt"],
        "pr_number": run["pull_request"]["number"],
        "head_sha": run["pull_request"]["head_sha"],
        "base_sha": run["pull_request"]["base_sha"],
        "checkout_sha": run["sha"], "parents": proof["parent_shas"],
        "parent_report_sha256": digest(vp),
        "verify_archive_sha256": vsha, "strict_archive_sha256": ssha,
        "strict_tests": summary["tests_run"],
        "externally_authenticated": False, "independent_pr_review": False,
        "candidate_promoted": False, "production_ready": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    source_verify = p.add_mutually_exclusive_group(required=True)
    source_verify.add_argument("--verify-zip", type=Path)
    source_verify.add_argument("--verify-dir", type=Path)
    source_strict = p.add_mutually_exclusive_group(required=True)
    source_strict.add_argument("--strict-zip", type=Path)
    source_strict.add_argument("--strict-dir", type=Path)
    p.add_argument("--expected-run-id")
    p.add_argument("--expected-head-sha")
    p.add_argument("--expected-checkout-sha")
    p.add_argument("--expected-verify-zip-sha256")
    p.add_argument("--expected-strict-zip-sha256")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    try:
        if args.verify_dir or args.strict_dir:
            if not (args.verify_dir and args.strict_dir):
                raise AuditError("MIXED_ARTIFACT_SOURCE_MODES_NOT_ALLOWED")
            if args.expected_verify_zip_sha256 or args.expected_strict_zip_sha256:
                raise AuditError("ORIGINAL_ZIP_DIGEST_CANNOT_PIN_REPACKAGED_DIRECTORY")
            with tempfile.TemporaryDirectory(prefix="rio-r022-artifact-") as td:
                verify_zip = Path(td) / "verify-repacked.zip"
                strict_zip = Path(td) / "strict-repacked.zip"
                repack_directory(args.verify_dir, verify_zip)
                repack_directory(args.strict_dir, strict_zip)
                report = inspect(verify_zip, strict_zip,
                                 expected_run_id=args.expected_run_id,
                                 expected_head_sha=args.expected_head_sha,
                                 expected_checkout_sha=args.expected_checkout_sha)
                report["input_kind"] = "REPACKAGED_SAME_RUN_ARTIFACT_DIRECTORIES"
                report["archive_digests_authority"] = "LOCAL_REPACKAGED_NOT_ORIGINAL_GITHUB_ZIPS"
        else:
            report = inspect(args.verify_zip, args.strict_zip,
                             expected_run_id=args.expected_run_id,
                             expected_head_sha=args.expected_head_sha,
                             expected_checkout_sha=args.expected_checkout_sha,
                             expected_verify_zip_sha256=args.expected_verify_zip_sha256,
                             expected_strict_zip_sha256=args.expected_strict_zip_sha256)
            report["input_kind"] = "ORIGINAL_ZIP_FILES"
    except (AuditError, OSError, ValueError) as exc:
        report = {"schema": SCHEMA, "status": "REJECTED",
                  "reason_code": str(exc)[:180], "externally_authenticated": False,
                  "independent_pr_review": False, "candidate_promoted": False,
                  "production_ready": False}
    result = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    print(result, end="")
    return 0 if report["status"] == SUCCESS else 2


if __name__ == "__main__":
    sys.exit(main())
