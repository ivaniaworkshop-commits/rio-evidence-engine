# Paired mode comparison

42 authored cases; five alternating-order repetitions each: 210 timed calls per mode.
One warm-up per mode excluded. Three fresh-process startup measurements per mode.

| Measure | Deterministic | Neural ranking |
| --- | ---: | ---: |
| Correct numeric schedules | 42/42 | 42/42 |
| Warm median | 0.0292 ms | 8.4634 ms |
| Warm p95 | 0.0504 ms | 9.9951 ms |
| Cold median: imports + load + one answer | 13.65 ms | 1146.73 ms |
| Median peak process RSS | 13.75 MiB | 264.33 MiB |

All 42 schedules and explanations were identical across modes. Therefore this
experiment demonstrates no output benefit from the neural ranker on these cases.
It adds a median 8.4342 ms per warm call locally.
A very large ratio partly reflects the very small deterministic baseline.

**Decision: keep deterministic default; neural ranking experimental and opt-in.**
No weights were changed by this comparison. A low language-model loss had not
established useful task behavior; this ablation tests that assumption directly.
It does not establish that neural ranking is useless on every possible task.

RSS is whole-process peak memory (including Python/PyTorch), not isolated model
weights. Startup time excludes interpreter launch. No financial meter or human
preference study was available. Timings are hardware/load sensitive, not universal
performance claims. The earlier free-generator 0/26 probe remains unchanged.

Reproduce with `python scripts/compare_modes.py`; raw per-case timings and output
equality checks are in MODE_ABLATION.json. Next useful model gate: demonstrate a
new capability or preferred output on a separately defined evaluation before
adding parameters or training steps.
