import hashlib
from types import SimpleNamespace

import pytest

from rio_pey_codi.pr_snapshot_guard import (
    IncompleteSnapshot, load_pinned_guard, main, scan_snapshot, validated_diff,
)


def snapshot(data="alpha\nbeta\n", name="app/file.txt"):
    body = data.encode("utf-8")
    blob = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()
    pieces = data.splitlines()
    patch = "@@ -0,0 +1," + str(len(pieces)) + " @@\n" + "\n".join("+" + p for p in pieces)
    if not data.endswith("\n"):
        patch += "\n\\ No newline at end of file"
    return [{"filename": name, "status": "added", "additions": len(pieces),
             "deletions": 0, "sha": blob, "patch": patch}]


def test_complete_and_no_final_newline():
    for data in ("alpha\nbeta\n", "alpha\nbeta"):
        files = snapshot(data)
        observed = []
        result = scan_snapshot(files, 1, lambda diff: observed.append(diff) or [])
        assert result["status"] == "PASS"
        assert result["verified_git_blobs"] == 1
        assert "+++ b/app/file.txt" in observed[0]


def test_findings_are_metadata_only():
    secret = "not-a-real-" + "secret-value"
    files = snapshot(secret + "\n")
    result = scan_snapshot(files, 1, lambda _: [SimpleNamespace(path="app/file.txt", diff_line=1, rule="TEST")])
    assert result["status"] == "FINDINGS"
    assert secret not in str(result)


@pytest.mark.parametrize("mutation", [
    lambda x: x[0].update(status="modified"),
    lambda x: x[0].update(filename="../outside"),
    lambda x: x[0].update(filename="a/../outside"),
    lambda x: x[0].update(sha="0" * 40),
    lambda x: x[0].update(patch=None),
    lambda x: x[0].update(patch=x[0]["patch"] + "\n+extra"),
    lambda x: x[0].update(additions=True),
    lambda x: x[0].update(deletions=1),
    lambda x: x.append(x[0].copy()),
])
def test_incomplete_or_ambiguous_fails_closed(mutation):
    files = snapshot()
    mutation(files)
    with pytest.raises(IncompleteSnapshot):
        validated_diff(files, len(files))


def test_mismatched_file_count_fails_closed():
    with pytest.raises(IncompleteSnapshot):
        validated_diff(snapshot(), 2)


@pytest.mark.parametrize("patch", ["@@ -0,0 +1 @@\n+++ ambiguous", "@@ -0,0 +1 @@\n+line\rhidden"])
def test_scanner_line_parsing_ambiguities_fail_closed(patch):
    files = snapshot("alpha\n")
    files[0]["patch"] = patch
    with pytest.raises(IncompleteSnapshot):
        validated_diff(files, 1)


def test_unpinned_code_is_not_executed(tmp_path):
    source = tmp_path / "guard.py"
    marker = tmp_path / "executed"
    source.write_text("open(" + repr(str(marker)) + ", 'w').write('bad')\n")
    with pytest.raises(IncompleteSnapshot):
        load_pinned_guard(source)
    assert not marker.exists()


def test_invalid_commits_fail_closed_without_reading_files(capsys):
    sha = "a" * 40
    code = main(["--snapshot", "/missing", "--guard", "/missing", "--base", sha,
                 "--head", sha, "--expected-files", "1"])
    assert code == 2
    assert '"status": "HOLD"' in capsys.readouterr().err
