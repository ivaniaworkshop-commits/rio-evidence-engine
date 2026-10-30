"""Additive exact-grammar task parser. Code-only and no broad English claim."""
import json
import re

from .core import critical_path
from .graph_copy import extract_graph
from .semantic_gate import canonical
from .json_io import load

IDS = "ABCDEFGH"
RULES = (
 ("step_sentence", r"Step (?P<id>[A-H]) takes (?P<n>0|[1-9][0-9]{0,6}) minutes after (?P<deps>none|[A-H](?: and [A-H])*)\."),
 ("pipe_record", r"(?P<id>[A-H]): (?P<n>0|[1-9][0-9]{0,6}) min \| after: (?P<deps>none|[A-H](?:,[A-H])*)"),
 ("key_value", r"task=(?P<id>[A-H]); duration_minutes=(?P<n>0|[1-9][0-9]{0,6}); predecessors=(?P<deps>none|[A-H](?:,[A-H])*)"),
 ("requires_sentence", r"(?P<id>[A-H]) requires (?P<deps>none|[A-H](?: and [A-H])*); duration (?P<n>0|[1-9][0-9]{0,6}) minutes"),
)

def extract_extended_graph(text):
    if not isinstance(text, str):
        raise ValueError("TEXT_MUST_BE_STRING")
    if len(text.encode("utf-8")) > 4096:
        raise ValueError("TEXT_EXCEEDS_4096_BYTES")
    legacy = extract_graph(text)
    if legacy["status"] != "ABSTAIN":
        return dict(legacy, extractor="LEGACY_PRESERVED", neural_calls=0)
    rows = text.splitlines(keepends=True)
    if not rows or re.fullmatch(r"Tasks: [1-8]", rows[0].rstrip("\r\n")) is None:
        return {"status": "ABSTAIN", "issues": ["UNSUPPORTED_DECLARATIVE_HEADER"],
                "graph": None, "schedule": None, "evidence": [], "neural_calls": 0}
    count = int(rows[0].rstrip("\r\n").split(": ")[1])
    expected = set(IDS[:count])
    issues, definitions, durations, evidence = [], {}, {}, []
    if len(rows) != count + 1:
        issues.append("DECLARED_TASK_COUNT_MISMATCH")
    offset = len(rows[0])
    for raw in rows[1:]:
        line = raw.rstrip("\r\n")
        matches = [(name, re.fullmatch(pattern, line)) for name, pattern in RULES]
        matches = [(name, match) for name, match in matches if match is not None]
        if len(matches) != 1:
            issues.append("UNRECOGNIZED_OR_AMBIGUOUS_LINE")
            offset += len(raw)
            continue
        family, match = matches[0]
        key, value = match.group("id"), int(match.group("n"))
        raw_deps = match.group("deps")
        deps = [] if raw_deps == "none" else raw_deps.split(" and " if " and " in raw_deps else ",")
        if key not in expected or any(d not in expected for d in deps):
            issues.append("UNDECLARED_TASK_REFERENCE")
        if key in definitions:
            issues.append("DUPLICATE_TASK")
        if len(deps) != len(set(deps)):
            issues.append("DUPLICATE_DEPENDENCY")
        if value > 1_000_000:
            issues.append("DURATION_OUT_OF_RANGE")
        definitions[key], durations[key] = deps, value
        evidence.append({"id": key, "family": family, "line": line,
            "source_start": offset, "source_end": offset + len(line),
            "duration_start": offset + match.start("n"), "duration_end": offset + match.end("n"),
            "depends_start": offset + match.start("deps"), "depends_end": offset + match.end("deps"),
            "offset_units": "PYTHON_UNICODE_CHARACTER_INDEX"})
        offset += len(raw)
    if set(definitions) != expected:
        issues.append("MISSING_OR_EXTRA_TASKS")
    graph = schedule = None
    if not issues:
        try:
            graph = canonical({"tasks": [{"id": k, "depends_on": definitions[k]} for k in IDS[:count]],
                               "durations": durations})
            schedule = critical_path(graph["tasks"], graph["durations"])
        except (TypeError, ValueError, KeyError, OverflowError):
            issues.append("INVALID_DEPENDENCY_GRAPH")
    return {"status": "ABSTAIN" if issues else "EXPLICIT_GRAPH_RECOVERED",
            "issues": sorted(set(issues)), "graph": graph, "schedule": schedule,
            "evidence": evidence, "neural_calls": 0,
            "authority": "DETERMINISTIC_FULL_LINE_PARSER_AND_EXACT_SOURCE_SPANS",
            "scope": "TASKS_1_TO_8_IDS_A_TO_H_FOUR_GRAMMARS_INTEGERS_0_TO_1M"}

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON object with exactly text")
    args = parser.parse_args(argv)
    try:
        obj = load(args.input)
        if not isinstance(obj, dict) or set(obj) != {"text"}:
            raise ValueError("EXPECTED_TEXT_FIELD_ONLY")
        print(json.dumps(extract_extended_graph(obj["text"]), allow_nan=False))
        return 0
    except (TypeError, ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
