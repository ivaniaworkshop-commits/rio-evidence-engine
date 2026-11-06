# R028 · Revisable lineage without prior R027 exposure

The R028 branch was created from the last pre-incident R026 commit, using only sanitized R027 source and the original R027 manifest/workflow. The first R028 commit had exactly the same Git tree SHA as the latest sanitized old branch, but did not include the intervening affected commits in ancestry.

This is an **alternative reviewed branch**, not deletion of the original branch or GitHub's historical objects. The old PR and previous branch remain accessible and must not be merged until separately reconciled. GitHub cache removal and third-party clones/forks are NOT verified.

The `verify_privacy_lineage_r028.py` check examines each revision since the known safe anchor for selected Pey files, so a previous leak cannot be masked by the final version. It never prints values it inspects. A six-case synthetic test suite includes a leak inserted and then corrected in another commit.

Limitations: checks only selected file paths and a conservative numeric pattern; this is NOT a global repository/privacy audit. No production promotion, no bank credentials, no live QR or payment acceptance.

Administrative remediation is pending: identify reachable historical refs, arrange safe retirement of affected branch/PR after migration, request GitHub cached-view cleanup where supported, and validate readback without repeating sensitive data.
