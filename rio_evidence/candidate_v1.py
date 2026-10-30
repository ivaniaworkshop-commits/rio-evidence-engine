"""H14: bounded strict CSV / JSON task graph reader layered on unchanged H09.

Not an LLM or natural-language model. Every accepted field must be explicit.
Malformed or ambiguous content abstains; neither bytes nor instructions trigger
external actions. A source format contract is not independent test evidence.
"""
import csv
import io
import json

from .core import critical_path
from .extended_graph import extract_extended_graph
from .semantic_gate import canonical

IDS = "ABCDEFGH"
CSV_HEADER = ["task", "duration", "predecessors"]


def _duplicate_object_keys(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("DUPLICATE_JSON_KEY")
        obj[k] = v
    return obj


def _reject_constant(value):
    raise ValueError("NONFINITE_JSON_NUMBER")


def _normal_graph(tasks, durations):
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 8:
        raise ValueError("TASK_COUNT_OUT_OF_BOUNDS")
    count = len(tasks)
    allowed = set(IDS[:count])
    if not isinstance(durations, dict) or set(durations) != allowed:
        raise ValueError("INCOMPLETE_DURATION_MAP")
    for k, value in durations.items():
        if type(value) is not int or not 0 <= value <= 1_000_000:
            raise ValueError("INVALID_INTEGER_MINUTES")
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "depends_on"}:
            raise ValueError("INVALID_TASK_FIELDS")
        key, deps = task["id"], task["depends_on"]
        if type(key) is not str or key not in allowed or key in seen:
            raise ValueError("DUPLICATE_OR_UNKNOWN_ID")
        seen.add(key)
        if not isinstance(deps, list) or any(type(dep) is not str or dep not in allowed for dep in deps):
            raise ValueError("UNKNOWN_PREDECESSOR")
        if len(set(deps)) != len(deps):
            raise ValueError("DUPLICATE_PREDECESSOR")
    if seen != allowed:
        raise ValueError("INCOMPLETE_TASK_SET")
    normalized = canonical({"tasks": tasks, "durations": durations})
    plan = critical_path(normalized["tasks"], normalized["durations"])
    return normalized, plan


def _csv_payload(text):
    # Caller has matched the exact CSV schema header; no guessing from prose.
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    rows = list(reader)
    if not rows or rows[0] != CSV_HEADER:
        raise ValueError("CSV_HEADER_MISMATCH")
    data = rows[1:]
    if not 1 <= len(data) <= 8:
        raise ValueError("CSV_TASK_COUNT_OUT_OF_BOUNDS")
    tasks, durations = [], {}
    for row in data:
        if len(row) != 3:
            raise ValueError("CSV_WRONG_COLUMN_COUNT")
        name, raw_duration, raw_deps = row
        if len(name) != 1 or name not in IDS or name in durations:
            raise ValueError("CSV_DUPLICATE_OR_UNKNOWN_TASK")
        if not raw_duration.isascii() or not raw_duration.isdecimal() or len(raw_duration) > 7 or (
            len(raw_duration) > 1 and raw_duration.startswith("0")
        ):
            raise ValueError("CSV_INVALID_INTEGER")
        duration = int(raw_duration)
        if duration > 1_000_000:
            raise ValueError("CSV_DURATION_OUT_OF_RANGE")
        if raw_deps == "none":
            deps = []
        else:
            deps = raw_deps.split("|")
            if not deps or any(len(x) != 1 or x not in IDS for x in deps):
                raise ValueError("CSV_INVALID_PREDECESSORS")
        durations[name] = duration
        tasks.append({"id": name, "depends_on": deps})
    return _normal_graph(tasks, durations)


def extract_candidate_v1(text):
    if not isinstance(text, str):
        raise ValueError("TEXT_MUST_BE_STRING")
    if len(text.encode("utf-8")) > 4096:
        raise ValueError("MAX_4096_BYTES")
    incumbent = extract_extended_graph(text)
    if incumbent["status"] != "ABSTAIN":
        return dict(incumbent, candidate="STRUCTURED_V1_LEGACY_PRESERVED", neural_calls=0)
    stripped = text.lstrip("\ufeff") if text.startswith("\ufeff") else text
    try:
        if stripped.startswith("task,duration,predecessors\n") or stripped.startswith("task,duration,predecessors\r\n"):
            graph, schedule = _csv_payload(stripped)
            source_format = "STRICT_CSV_V1"
        elif stripped.startswith("{"):
            payload = json.loads(
                stripped, object_pairs_hook=_duplicate_object_keys,
                parse_constant=_reject_constant,
            )
            if not isinstance(payload, dict) or set(payload) != {"tasks", "durations"}:
                raise ValueError("INVALID_JSON_GRAPH_ENVELOPE")
            graph, schedule = _normal_graph(payload["tasks"], payload["durations"])
            source_format = "STRICT_JSON_GRAPH_V1"
        else:
            return {"status": "ABSTAIN", "graph": None, "schedule": None,
                    "issues": ["UNSUPPORTED_INPUT_FORMAT"], "neural_calls": 0,
                    "candidate": "STRUCTURED_V1"}
    except (ValueError, TypeError, KeyError, csv.Error, RecursionError):
        return {"status": "ABSTAIN", "graph": None, "schedule": None,
                "issues": ["INVALID_OR_INCOMPLETE_EXPLICIT_GRAPH"], "neural_calls": 0,
                "candidate": "STRUCTURED_V1"}
    return {"status": "EXPLICIT_GRAPH_RECOVERED", "graph": graph, "schedule": schedule,
            "issues": [], "source_format": source_format,
            "source_anchoring": "COMPLETE_PAYLOAD_VALIDATED_NOT_CHARACTER_SPANS",
            "neural_calls": 0, "candidate": "STRUCTURED_V1"}
