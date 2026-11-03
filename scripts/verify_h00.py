"""Verify a GitHub Actions H00 run against the current pull request merge."""
import argparse
import json
import re
import subprocess


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True, timeout=60)


def api(path):
    return json.loads(gh("api", path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("pr", type=int)
    parser.add_argument("run", type=int)
    args = parser.parse_args()
    root = f"repos/{args.repository}"
    pr_path = f"{root}/pulls/{args.pr}"
    result = dict(ci="UNKNOWN", rules="UNKNOWN", authorization="UNKNOWN")
    errors = (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError)
    try:
        pr = api(pr_path)
        run = api(f"{root}/actions/runs/{args.run}")
        if (run["path"].split("@")[0] != ".github/workflows/h00-integrity.yml"
                or run["event"] != "pull_request" or run["status"] != "completed"):
            raise ValueError("Expected a completed H00 pull-request run")
        jobs = api(f"{root}/actions/runs/{args.run}/jobs?per_page=100")["jobs"]
        checkouts = {}
        for name in ("verify", "strict-torch"):
            matches = [job for job in jobs if job["name"] == name]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {name} job")
            job = matches[0]
            logs = gh("api", f"{root}/actions/jobs/{job['id']}/logs")
            ref = f"refs/remotes/pull/{args.pr}/merge"
            if ref not in logs:
                raise ValueError(f"Missing PR merge ref in {name}")
            hashes = re.findall(
                r"git log -1 --format=%H[^\n]*\n[^\n]*?\b([0-9a-f]{40})\s*$",
                logs, re.MULTILINE,
            )
            if len(hashes) != 1:
                raise ValueError(f"Missing or ambiguous checkout in {name}")
            checkouts[name] = hashes[0]
        latest = api(pr_path)
        def revision(p):
            return p["state"], p["head"]["sha"], p["base"]["sha"], p["merge_commit_sha"]
        result["checkouts"] = checkouts
        result["merge_sha"] = latest["merge_commit_sha"]
        if latest["state"] != "open" or not result["merge_sha"]:
            raise ValueError("Expected an open PR with a test merge")
        if revision(pr) != revision(latest) or set(checkouts.values()) != {result["merge_sha"]}:
            result["ci"] = "CI_DESACTUALIZADA"
        else:
            result["ci"] = "PASS" if all(
                job["conclusion"] == "success" for job in jobs if job["name"] in checkouts
            ) else "FAIL"
    except errors as error:
        result["ci_error"] = str(error)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ci"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
