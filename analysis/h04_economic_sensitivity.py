"""H04: bounded, deterministic scenario arithmetic; not a profitability forecast.

Inputs are decimal strings to avoid silently accepting binary floating-point
rounding. All assumptions are caller-provided; no external source is queried.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, localcontext
from pathlib import Path

NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SCALE = Decimal("0.000000000001")


def _object_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label}: missing or unexpected fields")


def _amount(label, value, *, positive=False):
    if not isinstance(value, str) or NUMBER.fullmatch(value) is None:
        raise ValueError(f"{label}: expected bounded nonnegative decimal string")
    result = Decimal(value)
    if positive and result == 0:
        raise ValueError(f"{label}: must exceed zero")
    return result


def _id(label, value):
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label}: invalid identifier")
    return value


def _rounded(value):
    # Presentation only. All acceptance gates use unrounded Decimal operands.
    return format(value.quantize(SCALE), "f")


def analyze(payload):
    _fields(payload, ("scenario_id", "baseline", "scenarios"), "payload")
    scenario_id = _id("scenario_id", payload["scenario_id"])
    base = payload["baseline"]
    _fields(base, ("ltv_mxn", "cac_mxn", "purchase_mxn", "gross_savings_mxn"), "baseline")
    ltv = _amount("ltv_mxn", base["ltv_mxn"], positive=True)
    cac = _amount("cac_mxn", base["cac_mxn"], positive=True)
    purchase = _amount("purchase_mxn", base["purchase_mxn"], positive=True)
    savings = _amount("gross_savings_mxn", base["gross_savings_mxn"])
    if savings > purchase:
        raise ValueError("gross_savings_mxn cannot exceed purchase_mxn")
    scenarios = payload["scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 30:
        raise ValueError("scenarios: expected 1 to 30 entries")

    with localcontext() as ctx:
        ctx.prec = 55
        ratio = ltv / cac
        required_ltv_factor = max(Decimal(1), cac / ltv)
        required_cac_drop = max(Decimal(0), (Decimal(1) - ratio) * 100)
        evaluated, names = [], set()
        for index, item in enumerate(scenarios):
            _fields(item, ("name", "ltv_multiplier", "cac_multiplier", "incremental_cost_mxn"), f"scenarios[{index}]")
            name = _id("scenario name", item["name"])
            if name in names:
                raise ValueError("duplicate scenario name")
            names.add(name)
            ltv_factor = _amount("ltv_multiplier", item["ltv_multiplier"])
            cac_factor = _amount("cac_multiplier", item["cac_multiplier"], positive=True)
            incremental = _amount("incremental_cost_mxn", item["incremental_cost_mxn"])
            new_ltv, new_cac = ltv * ltv_factor, cac * cac_factor
            net_savings = savings - incremental
            evaluated.append({
                "name": name,
                "ltv_cac_ratio_display": _rounded(new_ltv / new_cac),
                "meets_ltv_cac_one_gate": new_ltv >= new_cac,
                "gross_savings_mxn": format(savings, "f"),
                "incremental_cost_mxn": format(incremental, "f"),
                "savings_less_incremental_cost_mxn": format(net_savings, "f"),
                "savings_cover_incremental_cost": net_savings >= 0,
            })
        return {
            "schema": "RIO_H04_ECONOMIC_SENSITIVITY/1",
            "scenario_id": scenario_id,
            "status": "CALCULATED_FROM_USER_SUPPLIED_ASSUMPTIONS",
            "baseline": {
                "ltv_cac_ratio_display": _rounded(ratio),
                "meets_ltv_cac_one_gate": ltv >= cac,
                "minimum_ltv_multiplier_display": _rounded(required_ltv_factor),
                "minimum_cac_reduction_pct_display": _rounded(required_cac_drop),
                "gross_savings_rate_pct_display": _rounded(savings / purchase * 100),
            },
            "scenarios": evaluated,
            "evidence_boundary": "ASSUMPTION_SENSITIVITY_NOT_PROFITABILITY_OR_CAUSAL_EVIDENCE",
        }


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print('Usage: python analysis/h04_economic_sensitivity.py INPUT.json', file=sys.stderr)
        return 2
    try:
        path = Path(args[0])
        with path.open("rb") as source:
            data = source.read(65537)
        if len(data) > 65536:
            raise ValueError("input exceeds 65536 bytes")
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_object_pairs)
        result = analyze(payload)
    except (OSError, UnicodeError, ValueError, TypeError, ArithmeticError, RecursionError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
