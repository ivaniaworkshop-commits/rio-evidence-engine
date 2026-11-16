"""Offline, fail-closed guard for a complete all-added-text PR snapshot.

The caller must independently authenticate the snapshot and its base/head.
This is a manual check, not a GitHub status or a malware certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Callable

GUARD_SHA256 = "9c5348d840f42d0c043c927abb20a2647193e9e3fb51ed454c42df376fc8a058"
SHA = re.compile(r"[0-9a-f]{40}\Z")
PATH = re.compile(r"[A-Za-z0-9._/-]+\Z")
HUNK = re.compile(r"@@ -0,0 \+1(?:,(\d+))? @@(?:.*)\Z")
OTHER_LINE_SEPARATORS = set("\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")
MAX_SNAPSHOT_BYTES = 20_000_000


class IncompleteSnapshot(ValueError):
    """The snapshot does not support a complete scan in the stated scope."""


def validated_diff(files: object, expected_count: int) -> tuple[str, int]:
    if not isinstance(files, list) or not 0 < expected_count <= 3000 or len(files) != expected_count:
        raise IncompleteSnapshot("missing files or invalid expected count")
    sections: list[str] = []
    paths: set[str] = set()
    total = 0
    for item in files:
        if not isinstance(item, dict):
            raise IncompleteSnapshot("invalid file entry")
        name = item.get("filename")
        if (not isinstance(name, str) or not PATH.fullmatch(name) or name.startswith("/")
                or any(p in ("", ".", "..") for p in name.split("/")) or name in paths):
            raise IncompleteSnapshot("unsafe or repeated path")
        paths.add(name)
        count, deleted, blob, patch = (item.get(k) for k in ("additions", "deletions", "sha", "patch"))
        if (item.get("status") != "added" or type(count) is not int or count < 1
                or type(deleted) is not int or deleted != 0 or not isinstance(blob, str)
                or not SHA.fullmatch(blob) or not isinstance(patch, str)):
            raise IncompleteSnapshot("unsupported or incomplete file")
        lines = patch.split("\n")
        hunk = HUNK.fullmatch(lines[0]) if lines else None
        if not hunk or int(hunk.group(1) or 1) != count:
            raise IncompleteSnapshot("unsupported hunk")
        content: list[str] = []
        no_newline = False
        for position, line in enumerate(lines[1:], 1):
            if line.startswith("+"):
                if (no_newline or line.startswith("+++ ")
                        or OTHER_LINE_SEPARATORS.intersection(line)):
                    raise IncompleteSnapshot("ambiguous added line")
                content.append(line[1:])
            elif line == "\\ No newline at end of file":
                if no_newline or not content or position != len(lines) - 1:
                    raise IncompleteSnapshot("invalid newline marker")
                no_newline = True
            elif line == "" and position == len(lines) - 1:
                continue
            else:
                raise IncompleteSnapshot("unexpected or truncated patch")
        if len(content) != count:
            raise IncompleteSnapshot("addition count mismatch")
        data = ("\n".join(content) + ("" if no_newline else "\n")).encode("utf-8")
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != blob:
            raise IncompleteSnapshot("Git blob mismatch")
        sections.append(f"diff --git a/{name} b/{name}\n+++ b/{name}\n{patch}\n")
        total += count
    return "".join(sections), total


def scan_snapshot(files: object, expected_count: int, scanner: Callable) -> dict:
    diff, additions = validated_diff(files, expected_count)
    findings = [{"path": f.path, "line": f.diff_line, "rule": f.rule} for f in scanner(diff)]
    return {"status": "FINDINGS" if findings else "PASS", "files": expected_count,
            "verified_git_blobs": expected_count, "additions": additions, "findings": findings}


def load_pinned_guard(path: Path) -> Callable:
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != GUARD_SHA256:
        raise IncompleteSnapshot("guard does not match pinned source")
    module = types.ModuleType("rio_pinned_repository_guard")
    sys.modules[module.__name__] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module.scan_diff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--guard", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--expected-files", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if (not SHA.fullmatch(args.base) or not SHA.fullmatch(args.head)
                or args.base == "0" * 40 or args.head == "0" * 40 or args.base == args.head):
            raise IncompleteSnapshot("invalid base or head")
        raw = args.snapshot.read_bytes()
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise IncompleteSnapshot("snapshot too large")
        result = scan_snapshot(json.loads(raw), args.expected_files, load_pinned_guard(args.guard))
        result.update({"base_claimed": args.base, "head_claimed": args.head,
                       "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                       "guard_sha256": GUARD_SHA256, "scope": "ADDED_TEXT_FILES_ONLY",
                       "source_and_commits_authenticated_by_program": False,
                       "github_required_check": False})
        print(json.dumps(result, sort_keys=True))
        return 1 if result["findings"] else 0
    except (IncompleteSnapshot, OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc) if isinstance(exc, IncompleteSnapshot)
                          else type(exc).__name__, "github_required_check": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
