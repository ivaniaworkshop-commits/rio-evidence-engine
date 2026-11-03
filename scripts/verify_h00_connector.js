// Run in Codex functions.exec with the GitHub connector available.
async function verifyH00(repo_full_name, pr_number, run_id, runHeadSha) {
  const result = {ci: "UNKNOWN", authorization: "UNKNOWN", rules: "UNKNOWN"};
  const read = async (tool, args) => {
    const response = await tool({repo_full_name, ...args});
    if (response.isError || !response.structuredContent) throw Error("GitHub read failed");
    return response.structuredContent;
  };
  const pr = async () => (await read(tools.mcp__codex_apps__github_fetch_pr, {pr_number})).pull_request;
  const revision = p => JSON.stringify([p.state, p.draft, p.head_sha, p.base_sha, p.merge_commit_sha]);
  try {
    const before = await pr();
    if (before.state !== "open" || !before.merge_commit_sha) return result;
    const {workflow_runs} = await read(tools.mcp__codex_apps__github_fetch_commit_workflow_runs, {commit_sha: runHeadSha ?? before.head_sha});
    if (!workflow_runs.some(run => run.id === run_id && run.name === "H00 integrity and reproducibility" && run.status === "completed")) return result;
    const {jobs} = await read(tools.mcp__codex_apps__github_fetch_workflow_run_jobs, {run_id});
    const checks = await Promise.all(["verify", "strict-torch"].map(async name => {
      const matches = jobs.filter(job => job.name === name && job.status === "completed");
      if (matches.length !== 1) throw Error("Missing or ambiguous job: " + name);
      const job = matches[0];
      const {content} = await read(tools.mcp__codex_apps__github_fetch_workflow_job_logs, {job_id: job.id});
      const ref = new RegExp("refs/remotes/pull/" + pr_number + "/merge\\b");
      const lines = content.split("\n");
      const hashes = lines.flatMap((line, index) => line.includes("git log -1 --format=%H")
        ? [lines[index + 1]?.match(/\b[0-9a-f]{40}\s*$/)?.[0]?.trim()] : []);
      if (!ref.test(content) || hashes.length !== 1 || !hashes[0]) throw Error("Checkout evidence missing: " + name);
      return {name, sha: hashes[0], conclusion: job.conclusion};
    }));
    const after = await pr();
    result.checks = checks;
    result.merge_sha = after.merge_commit_sha;
    result.ci = revision(before) !== revision(after) || checks.some(check => check.sha !== after.merge_commit_sha)
      ? "CI_DESACTUALIZADA" : checks.every(check => check.conclusion === "success") ? "PASS" : "FAIL";
  } catch (error) {
    result.error = String(error);
  }
  return result;
}

// Set the repository, PR and run for each invocation.
// For historical runs, pass the run's original head SHA as the fourth argument.
text(await verifyH00("ivaniaworkshop-commits/rio-evidence-engine", 23, 41583451797, "af4b8fbc0d63fad90be74b620d87a888ef34864f"));
