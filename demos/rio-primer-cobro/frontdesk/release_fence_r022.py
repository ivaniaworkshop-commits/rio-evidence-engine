#!/usr/bin/env python3
"""R022 Vercel production-alias fencing, incident receipts, and no automatic rollback.

AUTHORIZATION: read-only Vercel API calls plus local JSON receipts.
The CLI workflow performs promotion separately. No fencing check is atomic with
the external promotion; always confirm ownership afterward and never auto-rollback.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from check_public_site import valid_base, DEFAULT_URL

PROJECT = "prj_J7YrJusN08qUXrZNPDBmspVRKW6d"
TEAM = "team_cAq0fHixSn0Hck4ogKCifUzi"
ALIAS = "rio-primer-cobro-frontdesk.vercel.app"
API = "https://api.vercel.com"
BASELINE_SCHEMA = "RIO_RELEASE_BASELINE_R022"
FENCE_SCHEMA = "RIO_RELEASE_FENCE_R022"
DEPLOY_ID = re.compile(r"^dpl_[A-Za-z0-9]+$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class FenceError(ValueError):
    pass


def unwrap(data: object) -> dict:
    if not isinstance(data, dict):
        raise FenceError("INVALID_API_RESPONSE")
    result = data.get("result", data)
    if not isinstance(result, dict):
        raise FenceError("INVALID_API_RESPONSE")
    return result


def alias_deployment(data: object) -> str:
    item = unwrap(data)
    if item.get("alias") != ALIAS or item.get("deletedAt") is not None:
        raise FenceError("ALIAS_NOT_VERIFIED")
    deployment = item.get("deploymentId") or (item.get("deployment") or {}).get("id")
    if not isinstance(deployment, str) or not DEPLOY_ID.fullmatch(deployment):
        raise FenceError("ALIAS_DEPLOYMENT_UNRESOLVED")
    if item.get("projectId") != PROJECT:
        raise FenceError("ALIAS_PROJECT_MISMATCH")
    return deployment


def candidate_deployment(data: object, candidate_url: str) -> str:
    item = unwrap(data)
    d = item.get("deployment", item)
    if not isinstance(d, dict):
        raise FenceError("CANDIDATE_INVALID")
    deployment_id = d.get("id")
    project = d.get("project") or {}
    project_id = project.get("id") if isinstance(project, dict) else None
    project_id = project_id or d.get("projectId")
    state = d.get("readyState") or d.get("state")
    if (not isinstance(deployment_id, str) or not DEPLOY_ID.fullmatch(deployment_id)
            or project_id != PROJECT or state != "READY" or d.get("target") != "production"):
        raise FenceError("CANDIDATE_NOT_READY_PRODUCTION_PROJECT")
    host = urlparse(candidate_url).hostname
    if d.get("url", "").lower() != host:
        raise FenceError("CANDIDATE_URL_IDENTITY_MISMATCH")
    return deployment_id


def validate_candidate_url(url: str) -> str:
    try:
        base = valid_base(url)
    except (ValueError, TypeError) as exc:
        raise FenceError("CANDIDATE_URL_NOT_ALLOWED") from exc
    if base == DEFAULT_URL or url != base:
        raise FenceError("CANDIDATE_URL_NOT_IMMUTABLE_HOST")
    return base


def baseline_record(alias_id: str, commit: str) -> dict:
    if not DEPLOY_ID.fullmatch(alias_id) or not COMMIT.fullmatch(commit):
        raise FenceError("BASELINE_INVALID_IDENTITY")
    return {"schema": BASELINE_SCHEMA, "result": "OBSERVED_BASELINE",
            "project": PROJECT, "alias": ALIAS, "commit": commit,
            "previous_deployment_id": alias_id, "authority": "VERCEL_API_READBACK"}


def fence_record(baseline: dict, current_alias: str, candidate_id: str, url: str, commit: str) -> dict:
    validate_candidate_url(url)
    if (baseline.get("schema") != BASELINE_SCHEMA or
            baseline.get("project") != PROJECT or baseline.get("alias") != ALIAS or
            baseline.get("commit") != commit or not COMMIT.fullmatch(commit)):
        raise FenceError("STALE_OR_INVALID_BASELINE")
    previous = baseline.get("previous_deployment_id")
    if not isinstance(previous, str) or not DEPLOY_ID.fullmatch(previous):
        raise FenceError("BAD_PREVIOUS_ID")
    if previous != current_alias:
        raise FenceError("CONCURRENT_ALIAS_CHANGE_BEFORE_PROMOTION")
    if candidate_id == previous or not DEPLOY_ID.fullmatch(candidate_id):
        raise FenceError("CANDIDATE_NOT_DISTINCT")
    return {"schema": FENCE_SCHEMA, "result": "PRE_PROMOTION_GUARD_PASS_NOT_ATOMIC",
            "project": PROJECT, "alias": ALIAS, "commit": commit,
            "previous_deployment_id": previous, "candidate_deployment_id": candidate_id,
            "candidate_url": url, "automatic_rollback": False}


def confirm_fence(fence: dict, actual_alias: str, commit: str) -> dict:
    if (fence.get("schema") != FENCE_SCHEMA or fence.get("project") != PROJECT
            or fence.get("alias") != ALIAS or fence.get("commit") != commit
            or not COMMIT.fullmatch(commit)):
        raise FenceError("STALE_OR_INVALID_FENCE")
    expected = fence.get("candidate_deployment_id")
    if expected != actual_alias:
        raise FenceError("CONCURRENT_OR_FAILED_PROMOTION")
    return {"schema": "RIO_RELEASE_ALIAS_CONFIRM_R022",
            "result": "ALIAS_POINTS_TO_TESTED_CANDIDATE",
            "alias": ALIAS, "commit": commit, "candidate_deployment_id": expected,
            "public_html_readback": "SEPARATE_CHECK_REQUIRED",
            "automatic_rollback": False}


def incident_record(fence: dict | None, current_alias: str | None, error: str) -> dict:
    expected = fence.get("candidate_deployment_id") if isinstance(fence, dict) else None
    previous = fence.get("previous_deployment_id") if isinstance(fence, dict) else None
    if current_alias is None:
        classification = "ALIAS_UNKNOWN_MANUAL_REVIEW"
    elif expected and current_alias != expected:
        classification = "ALIAS_CHANGED_OR_PROMOTION_NOT_APPLIED_NO_ROLLBACK"
    elif current_alias == expected:
        classification = "CANDIDATE_OWNS_ALIAS_BUT_POSTCHECK_FAILED"
    else:
        classification = "FENCE_UNKNOWN_MANUAL_REVIEW"
    return {"schema": "RIO_RELEASE_INCIDENT_R022", "result": "INCIDENT_OPEN",
            "classification": classification, "reason": str(error)[:180],
            "previous_deployment_id": previous,
            "candidate_deployment_id": expected, "observed_deployment_id": current_alias,
            "automatic_rollback": False, "next_action": "HUMAN_REVIEW_AND_REBASE"}


def read_json(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FenceError("INVALID_RECEIPT")
    return value


def write_json(path: str | None, item: dict) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    print(json.dumps(item, ensure_ascii=False))


class DenyAPIRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise FenceError("VERCEL_API_REDIRECT_BLOCKED")


def api_get(path: str) -> dict:
    token = os.environ.get("VERCEL_TOKEN", "")
    if len(token) < 12 or "\n" in token:
        raise FenceError("VERCEL_TOKEN_NOT_CONFIGURED")
    url = API + path + "?teamId=" + quote(TEAM)
    request = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "RIO-RELEASE-FENCE-R022",
    })
    try:
        with build_opener(DenyAPIRedirect()).open(request, timeout=18) as response:
            if response.status != 200:
                raise FenceError("VERCEL_API_NON_200")
            data = response.read(262145)
    except OSError as exc:
        raise FenceError("VERCEL_API_UNAVAILABLE") from exc
    if len(data) > 262144:
        raise FenceError("VERCEL_API_RESPONSE_OVERSIZED")
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FenceError("VERCEL_API_RESPONSE_INVALID") from exc


def read_alias() -> str:
    return alias_deployment(api_get("/v4/aliases/" + ALIAS))


def read_candidate(url: str) -> str:
    validate_candidate_url(url)
    return candidate_deployment(api_get("/v13/deployments/" + quote(urlparse(url).hostname, safe="")), url)


def main() -> int:
    arg = argparse.ArgumentParser()
    arg.add_argument("phase", choices=("snapshot", "guard", "confirm", "incident"))
    arg.add_argument("--baseline")
    arg.add_argument("--fence")
    arg.add_argument("--candidate-url")
    arg.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    arg.add_argument("--output")
    args = arg.parse_args()
    try:
        if args.phase == "snapshot":
            result = baseline_record(read_alias(), args.commit)
        elif args.phase == "guard":
            baseline = read_json(args.baseline)
            candidate = read_candidate(args.candidate_url)
            result = fence_record(baseline, read_alias(), candidate, args.candidate_url, args.commit)
        elif args.phase == "confirm":
            result = confirm_fence(read_json(args.fence), read_alias(), args.commit)
        else:
            fence = read_json(args.fence) if args.fence else None
            try:
                actual = read_alias()
            except (FenceError, ValueError, OSError):
                actual = None
            result = incident_record(fence, actual, "POST_PROMOTION_CHECK_FAILED")
        write_json(args.output, result)
        return 0
    except (FenceError, ValueError, TypeError, OSError, AttributeError) as exc:
        # Never expose token or raw HTTP response. Incident phase must remain observable.
        print(json.dumps({"result": "FAIL_CLOSED", "reason": str(exc)[:160],
                          "automatic_rollback": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
