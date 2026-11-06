# RÍO — source manifest authoring contract

- A producer MUST publish each source edit and its corresponding `MANIFEST.json` entry in **the same Git commit**. A passing CI run on an earlier SHA never validates a later SHA.
- For a local Git index: review and stage approved source files; run `python3 scripts/prepare_staged_manifest.py --prepare`, then `python3 scripts/prepare_staged_manifest.py` and `python3 scripts/verify_manifest.py`. Commit the staged snapshot atomically. Do **not** execute `git add -A` blindly.
- For GitHub REST/Git Data authors: build **one tree** containing all source blobs plus the matching manifest blob, then create a **single** commit and update only the authorized feature/ref. Do not push intermediate source-only commits.
- CI remains fail-closed; it MUST NOT regenerate or silently accept a manifest from untrusted source. Hashes prove byte identity, not approval or truth.
- Never write directly to protected `main`, bypass an approval, invent deployment authority, or deploy during source repair.
