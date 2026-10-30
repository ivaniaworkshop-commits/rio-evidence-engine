# Río Evidence Engine

A small, offline Python prototype for reproducible task dependencies, paired evaluation and evidence journals. Extracted from AI-assisted preparation work in the Río project. This repository exposes a bounded engineering component; it does not expose the private Río knowledge corpus.

## Run

Python 3.10+ syntax; verified here on Python 3.12.14. The demo and CLI require no third-party dependencies or API credentials. The optional array branch of `triangular_ppf` requires NumPy, which is not bundled or covered by the standard-library test suite.

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

Twenty-three functional tests cover graph scheduling, paired metrics, numeric boundaries, budget reserve, schema limits, journal consistency and incomplete-line handling. Actual execution results are recorded in VALIDATION.json. Regression tests include malformed inputs, CLI subprocesses, and dependency invariants across 64 seeded synthetic graphs. The demo uses authored synthetic values; it is not a benchmark or evidence of real-world performance improvement.

## Limits

A hash chain checks internal byte consistency. It does not prove the truth of an event, authority, authorship, completeness, protection against truncation or a coherently rewritten history. A syntactically allowed metadata value may still contain sensitive information: callers must supply appropriate identifiers. There is no active antivirus, autonomous agent runtime, independent AI protector, fine-tuning or production deployment.

## Contribution and provenance

The project owner directed the goals and evidence requirements. AI assistance was used for implementation, review and tests. The exported module and tests originated in the project’s FRONTIER preparation, not an official competition challenge. There is no claim of external users or independent certification. No third-party source implementation is intentionally included. Public licensing is not asserted by this preparation package.

## Use with your own JSON

From the repository root:

```sh
python -m rio_evidence schedule examples/schedule.json
python -m rio_evidence compare examples/compare.json
python -m rio_evidence verify-journal path/to/events.jsonl
```

Success writes JSON to stdout and exits 0. Input or journal validation failures
write a JSON error to stderr and exit 2. Invalid command usage is handled by
argparse and also exits 2. Example schedules are in minutes; comparison latency
is in milliseconds. The example comparison is synthetic, not a user study.

`schedule` expects `tasks` and `durations`; `compare` expects `baseline` and
`candidate`. See the checked-in examples for complete payloads. Dependencies
must be lists of unique ids. Traversal is deterministic and uses a heap-based
Kahn algorithm; unrelated task ordering may differ from the first version.
`verify-journal` checks internal consistency and rejects duplicate JSON keys
and incomplete final lines. It does not authenticate the writer.

## Performance evidence

BENCHMARK.json records three local runs per implementation on the same authored
2,000-node chain. It is a narrow measurement, sensitive to hardware and load;
it does not establish performance for arbitrary graphs or production workloads.

## Development

Run `python -m unittest discover -s tests -v` and `python demo.py` before a
change. See CHANGELOG.md for fixes and compatibility notes. The journal remains
single-writer, reads the full history on append, and has no locking or durable
transaction guarantee. CLI commands read local files only; no model API or
service is started.
