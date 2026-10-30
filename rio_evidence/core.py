"""Offline preparation helpers. No model calls, networking, or Río activation."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


def topological_order(tasks):
    if any(not isinstance(t.get('id'), str) or not t['id'].strip() for t in tasks):
        raise ValueError('nonempty text task id required')
    by_id = {t['id']: t for t in tasks}
    if len(by_id) != len(tasks):
        raise ValueError('duplicate task id')
    remaining = {k: set(t.get('depends_on', [])) for k, t in by_id.items()}
    for deps in remaining.values():
        if deps - by_id.keys():
            raise ValueError('missing dependency')
    result = []
    while remaining:
        ready = sorted(k for k, deps in remaining.items() if not deps)
        if not ready:
            raise ValueError('dependency cycle')
        for key in ready:
            result.append(key)
            del remaining[key]
        for deps in remaining.values():
            deps.difference_update(ready)
    return result


def critical_path(tasks, durations):
    """Unlimited-worker lower bound. A single worker also needs sum(durations)."""
    order = topological_order(tasks)
    by_id = {t['id']: t for t in tasks}
    if set(durations) != set(by_id):
        raise ValueError('duration ids differ')
    finish, parent = {}, {}
    for key in order:
        d = durations[key]
        if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or d < 0:
            raise ValueError('invalid duration')
        deps = by_id[key].get('depends_on', [])
        predecessor = max(deps, key=lambda x: (finish[x], x)) if deps else None
        parent[key] = predecessor
        finish[key] = d + (finish[predecessor] if predecessor is not None else 0)
    if not finish:
        return {'minutes': 0, 'path': [], 'single_worker_minutes': 0}
    end = max(finish, key=lambda x: (finish[x], x))
    path = []
    while end is not None:
        path.append(end)
        end = parent[end]
    return {'minutes': max(finish.values()), 'path': list(reversed(path)),
            'single_worker_minutes': sum(durations.values())}


def triangular_ppf(u, low, mode, high):
    """Inverse triangular CDF; supports NumPy arrays without importing NumPy."""
    if not all(math.isfinite(x) for x in (low, mode, high)) or not low <= mode <= high:
        raise ValueError('invalid triangular bounds')
    if isinstance(u, (float, int)):
        if not math.isfinite(u) or not 0 <= u <= 1:
            raise ValueError('u outside [0,1]')
        if low == high:
            return low
        c = (mode-low)/(high-low)
        if u <= c:
            return low+math.sqrt(u*(high-low)*(mode-low))
        return high-math.sqrt((1-u)*(high-low)*(high-mode))
    # Only analysis tools use vector operations; standard-library core stays portable.
    import numpy as np
    u = np.asarray(u)
    if not np.all(np.isfinite(u)) or np.any((u < 0) | (u > 1)):
        raise ValueError('u outside [0,1]')
    if low == high:
        return np.full_like(u, low, dtype=float)
    c = (mode-low)/(high-low)
    return np.where(u <= c, low+np.sqrt(u*(high-low)*(mode-low)),
                    high-np.sqrt((1-u)*(high-low)*(high-mode)))


def wilson_interval(successes, n, z=1.959963984540054):
    if not isinstance(n, int) or n <= 0 or not 0 <= successes <= n:
        raise ValueError('invalid counts')
    p = successes/n
    scale = 1+z*z/n
    center = (p+z*z/(2*n))/scale
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/scale
    return max(0, center-half), min(1, center+half)


def compare_results(baseline, candidate):
    """Require paired case ids: never report a gain from a changed denominator."""
    def keyed(rows):
        if any(set(r) != {'case_id', 'correct', 'latency_ms'} for r in rows):
            raise ValueError('unexpected fields')
        if any(not isinstance(r['correct'], bool) for r in rows):
            raise ValueError('correct must be bool')
        if any(not isinstance(r['case_id'], str) or not r['case_id'] for r in rows):
            raise ValueError('case id missing')
        if any(isinstance(r['latency_ms'], bool) or not isinstance(r['latency_ms'], (int, float))
               or not math.isfinite(r['latency_ms']) or r['latency_ms'] < 0 for r in rows):
            raise ValueError('invalid latency')
        d = {r['case_id']: r for r in rows}
        if not rows or len(d) != len(rows):
            raise ValueError('empty or duplicate cases')
        return d
    a, b = keyed(baseline), keyed(candidate)
    if a.keys() != b.keys():
        raise ValueError('unpaired cases')
    n = len(a)
    return {'n': n, 'baseline_correct': sum(r['correct'] for r in a.values()),
            'candidate_correct': sum(r['correct'] for r in b.values()),
            'correct_delta': sum(b[k]['correct']-a[k]['correct'] for k in a),
            'mean_latency_delta_ms': sum(b[k]['latency_ms']-a[k]['latency_ms'] for k in a)/n,
            'scope': 'PAIRED_LOCAL_CASES_ONLY_NOT_HIDDEN_TESTS'}


@dataclass
class WorkLimit:
    max_units: int = 8
    used_units: int = 0
    reserve_units: int = 2

    def __post_init__(self):
        values=(self.max_units,self.used_units,self.reserve_units)
        if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in values):
            raise ValueError('invalid work limit')
        if self.reserve_units>self.max_units or self.used_units>self.max_units:
            raise ValueError('inconsistent work limit')

    def reserve(self, units=1):
        if (isinstance(units, bool) or not isinstance(units, int) or units <= 0
                or self.used_units+units > self.max_units-self.reserve_units):
            return False
        self.used_units += units
        return True

    def state(self):
        return {'remaining_credits': None, 'credit_state': 'UNKNOWN_NO_ACCOUNT_METER',
                'work_units_remaining': max(0, self.max_units-self.used_units),
                'spendable_units_remaining': max(0,self.max_units-self.reserve_units-self.used_units),
                'delivery_reserve_units': self.reserve_units,
                'warning': 'WORK_UNITS_ARE_NOT_CREDITS_OR_TOKENS'}


EVENT_FIELDS = {'event_id', 'task_id', 'phase', 'status', 'elapsed_ms', 'attempt',
                'evidence_ref', 'version', 'calls', 'tokens_in', 'tokens_out', 'cost_usd'}


def validate_event(event):
    """Closed metadata schema. No prompt, request body, URL, key, or raw response."""
    if set(event)-EVENT_FIELDS:
        raise ValueError('unapproved telemetry fields')
    for key in ('event_id', 'task_id', 'phase', 'status', 'evidence_ref', 'version'):
        value = event.get(key)
        if not isinstance(value, str) or not value or len(value) > 160:
            raise ValueError('invalid metadata string')
        # Refs use local safe identifiers, never URLs or free-form content.
        if any(not (c.isalnum() or c in '._/-:') for c in value) or '://' in value:
            raise ValueError('metadata must be local identifiers')
        if value.startswith(('/', '\\')) or '..' in value.split('/'):
            raise ValueError('absolute or parent path not allowed')
    if event['status'] not in {'PLAN', 'READY', 'HOLD', 'RUNNING', 'PASS', 'FAIL', 'UNKNOWN'}:
        raise ValueError('invalid status')
    for key in ('elapsed_ms', 'attempt', 'calls', 'tokens_in', 'tokens_out', 'cost_usd'):
        value = event.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError('invalid numeric metadata')
    return event


def append_event(path, event):
    """Single-writer append journal; hash proves bytes, not event truth/authority."""
    validate_event(event)
    path = Path(path)
    if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b'\n'):
        raise ValueError('journal missing terminal newline; repair separately before append')
    old = read_events(path) if path.exists() else []
    if any(row['event']['event_id'] == event['event_id'] for row in old):
        raise ValueError('duplicate event id')
    previous = old[-1]['sha256'] if old else None
    body = {'previous_sha256': previous, 'event': event}
    raw = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    row = dict(body, sha256=hashlib.sha256(raw).hexdigest())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n')
        f.flush()
    return row


def read_events(path):
    rows, previous, ids = [], None, set()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if set(row) != {'previous_sha256', 'event', 'sha256'}:
            raise ValueError('invalid journal row')
        validate_event(row['event'])
        body = {'previous_sha256': row['previous_sha256'], 'event': row['event']}
        raw = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        if row['previous_sha256'] != previous or row['sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('journal content or chain mismatch')
        if row['event']['event_id'] in ids:
            raise ValueError('duplicate event id')
        ids.add(row['event']['event_id'])
        rows.append(row)
        previous = row['sha256']
    return rows
