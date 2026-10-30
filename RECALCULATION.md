# Bounded recalculation policy

Status: five daily automations created and enabled, starting 2026-10-31.
Execution has not yet been observed. The owner requested pausing the five
previous active tasks; they were paused, not deleted.

Cadence (flexible windows, America/Mexico_City): improvement 08:00; correctness
10:00; security 12:00; performance 14:00; dashboard 16:00. Only improvement may
write/publish; the other tasks are read-only. Scheduled tasks do not establish
independent model errors or continuous runtime.

Each round must retrieve main and reconcile concurrent changes first. Rank
candidate deltas by reproducible defect, observed benefit, uncertainty reduced,
effort, risk and reversibility. Ordinal judgment is not measured ROI. Execute at
most one bounded improvement, preserve regression coverage, and publish only
passing changes with readback. If no material delta exists, make no commit.

Keep DELTAS.json and docs/data.json identical. Snapshot metrics must come from
actual validation output; authored cases never count as real users. Retain
benchmark workload and hardware/load caveats. Regenerate MANIFEST.json after
source changes, excluding itself and bytecode. Do not claim remote CI passed
from local test output.

Public Site: appgprj_6ae4e24099e081918ee05c506cee990a
Frontend source: docs/ (copied to the Site dist/ directory).
Dashboard updates require the Sites workflow, current source rebase, unchanged
public audience and a verified deployment. A GitHub commit alone does not update
the hosted Site. Do not publish the private Río corpus or credentials.
