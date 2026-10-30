# Río Evidence Engine

A small, offline Python prototype for reproducible task dependencies, paired evaluation and evidence journals. Extracted from AI-assisted preparation work in the Río project. This repository exposes a bounded engineering component; it does not expose the private Río knowledge corpus.

## Run

Python 3.10+ syntax; verified here on Python 3.12.14. No third-party dependencies or API credentials.

```sh
python demo.py
python -m unittest discover -s tests -v
```

## What it does

- Checks a dependency graph for missing nodes, duplicates and cycles.
- Reports critical-path duration separately from total single-worker work.
- Compares baseline and candidate results only when case identifiers match.
- Validates a closed event-metadata schema and maintains a single-writer hash-linked journal.
- Separates local work-unit limits from unknown account credit balances.

## Decisions and tradeoffs

The core uses the standard library to reduce setup requirements. Graph scheduling is deliberately limited: the critical path assumes unlimited workers and is not a resource-constrained scheduler. Evaluation requires paired case identities so changing the denominator cannot masquerade as an improvement. A local journal makes evidence inspectable without a database, but is suitable only for a single writer.

## Verification

Twelve functional tests cover graph scheduling, paired metrics, numeric boundaries, budget reserve, schema limits, journal consistency and incomplete-line handling. Actual execution results are recorded in VALIDATION.json. The demo uses authored synthetic values; it is not a benchmark or evidence of real-world performance improvement.

## Limits

A hash chain checks internal byte consistency. It does not prove the truth of an event, authority, authorship, completeness, protection against truncation or a coherently rewritten history. A syntactically allowed metadata value may still contain sensitive information: callers must supply appropriate identifiers. There is no active antivirus, autonomous agent runtime, independent AI protector, fine-tuning or production deployment.

## Contribution and provenance

The project owner directed the goals and evidence requirements. AI assistance was used for implementation, review and tests. The exported module and tests originated in the project’s FRONTIER preparation, not an official competition challenge. There is no claim of external users or independent certification. No third-party source implementation is intentionally included. Public licensing is not asserted by this preparation package.
