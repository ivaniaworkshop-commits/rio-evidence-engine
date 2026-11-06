# R024 - Controlled isolated GitHub Actions incident drill

The R023 incident reconciler now has an explicit offline alias mode. The mode never invokes Vercel APIs; a unit test checks this by replacing the lookup with a function that raises if called.

This drill deliberately fails two GitHub Actions steps, with exit codes 47 and 49. Step outcome must be failure. Those two steps have continue-on-error so the remaining validation and artifact steps execute; this is not a claim that the overall workflow failed.

Missing baseline and fence: incident remains open with alias unknown.
Corrupt baseline and fence: incident remains open with evidence corrupt.
Both cases require no rollback, no production write and no incident closure.

The workflow is triggered only by a change to R024_TRIGGER.txt on the release branch.
The workflow has contents:read only, no environment, and VERCEL_TOKEN empty.
Two JSON receipts are uploaded as one Actions artifact.

Before runner readback: status PROGRAMMED, not OBSERVED.
Rulesets remain unavailable for production deployment; no changes to main, no Android physical testing.
