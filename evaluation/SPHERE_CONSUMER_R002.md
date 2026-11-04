# R002 — Sphere Mother consumer (read-only candidate)

This repository is public; the upstream RÍO repository is private. This adapter
does **not** read private source, fetch an upstream wheel, import a private
module, accept credentials, or authorize GitHub writes.

- Candidate source revision is an exact 40-character SHA in
  rio_evidence/sphere_consumer.py. It identifies an unmerged candidate,
  **not** an authenticated upstream release.
- Input is a JSON-compatible mapping with four fields:
  source_commit, engine, evidence, authority.
- The engine must use RIO_SPHERE_ENGINE_RECEIPT/1.0 and provide an
  engine_id, payload, and SHA-256 of canonical JSON.
- The evidence declaration must bind the same digest, declare a distinct
  verifier_id, a nonempty source reference, and result=PASS.
- The authority declaration must bind the same digest, declare a distinct
  issuer_id, an approval reference, a concrete operation and target, and
  decision=APPROVE. An explicit DENY is respected.
- Even when every declaration matches, the result is
  HOST_VERIFICATION_REQUIRED, never ALLOW. All authenticity flags stay false.
- The module only performs **structural screening**. Distinct actor strings,
  a matching digest, a pinned SHA, and a claimed PASS are not evidence of
  external attestation, GitHub permission separation, origin, or authorization.

## Local testing

    python3 -m unittest tests.test_sphere_consumer -v
    python3 scripts/verify_manifest.py

No private keys, private repository content, independent holdout data, or
evaluation claims belong in the public test fixtures.

## Exit criteria (not satisfied)

1. A trusted host authenticates RÍO's source revision and engine execution.
2. A separate authorized verifier independently retrieves the evidence source.
3. A separately authenticated authority binds a scoped action to an
   authenticated identity, policy, freshness and revocation state.
4. Restricted GitHub credentials demonstrate an actual denied write.
5. Both repositories' exact commits, CI, readbacks and privacy controls
   are reviewed before enabling any write-capable integration.

Until then: PROPOSED, PRODUCTION=NO, PROMOTION=BLOCKED.
