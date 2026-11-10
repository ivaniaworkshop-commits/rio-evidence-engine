"""Finite derived-work controller. Never edits source, weights, permissions or publishes."""
import argparse,hashlib,importlib.util,json,math,statistics,time
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from .atomic_runtime import WarmRuntime,atomic_matrices,source_fingerprint,precompute_public
from .graph_copy import extract_graph
from .json_io import loads


_SHA256 = re.compile('[0-9a-f]{64}')
_RECEIPT_METADATA = {'run_id', 'recorded_at_utc', 'previous_sha256'}


def verify_source(root):
    spec=importlib.util.spec_from_file_location('local_manifest_guard',root/'scripts/verify_manifest.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    return guard.verify(root)


def priority(benefit,uncertainty,evidence,reuse,effort,risk):
    values=[benefit,uncertainty,evidence,reuse,effort,risk]
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('finite scores required')
    if effort<=0 or any(v<0 for v in values) or risk>1:raise ValueError('invalid score bounds')
    return (benefit+uncertainty+evidence+reuse)*(1-risk)/effort


def measure_cache(root,engine):
    cases=[json.loads(s) for s in (root/'training/extraction_dev.jsonl').read_text().splitlines()]
    cold=[];warm=[];matches=0
    for index,row in enumerate(cases):
        for rep in range(5):
            outputs={}
            for mode in (['direct','cache'] if (index+rep)%2==0 else ['cache','direct']):
                start=time.perf_counter();outputs[mode]=extract_graph(row['text']) if mode=='direct' else engine.graph(row['text'])
                (cold if mode=='direct' else warm).append((time.perf_counter()-start)*1000)
            if outputs['direct']!=outputs['cache']:raise ValueError('cached result differs')
            matches+=1
    baseline=statistics.median(cold);cached=statistics.median(warm)
    return {'cases':len(cases),'repetitions':5,'paired_equal_results':matches,
      'direct_median_ms':baseline,'cached_median_ms':cached,'median_saving_ms':baseline-cached,
      'scope':'LOCAL_REPEATED_PUBLIC_INPUTS_NOT_UNIQUE_REQUEST_OR_NEURAL_SPEEDUP'}


class RoundController:
    def __init__(self,root):
        bootstrap_start=time.perf_counter()
        self.root=Path(root);self.guard=verify_source(self.root);self.revision=source_fingerprint(self.root)
        self.engine=WarmRuntime(self.revision);self.package=None;self.benchmark=None;self.actions=[];self.rankings=[]
        self.prewarm_ms=None
        path=self.root/'runtime/PUBLIC_PRECOMPUTE.json'
        if path.exists():
            candidate=json.loads(path.read_text())
            expected=hashlib.sha256((self.root/'training/extraction_dev.jsonl').read_bytes()).hexdigest()
            if candidate.get('source_revision')==self.revision and candidate.get('source_data_sha256')==expected:self.package=candidate
        self.bootstrap_ms=(time.perf_counter()-bootstrap_start)*1000
    def candidates(self):
        proposals=[
          ('PRECOMPUTE_PUBLIC',self.package is None,[3,2,3,3,2,.05],['verified_source','public_authored_data']),
          ('PREWARM_MEMORY',self.package is not None and not self.engine.warm,[3,1,3,4,1,.02],['valid_precompute']),
          ('MEASURE_CACHE',self.engine.warm and self.benchmark is None,[2,4,4,2,2,.02],['warm_memory']),
        ]
        return sorted([{'action':name,'eligible':eligible,'score':priority(*features),'features':features,'dependencies':deps,
           'score_state':'LOCAL_ORDINAL_HEURISTIC_NOT_OBSERVED_ROI'} for name,eligible,features,deps in proposals],key=lambda x:(not x['eligible'],-x['score'],x['action']))
    def execute(self,name):
        # Fixed allowlist: no command, URL or code is accepted from data.
        if name=='PRECOMPUTE_PUBLIC':self.package=precompute_public(self.root);result={'cases':len(self.package['records'])}
        elif name=='PREWARM_MEMORY':
            start=time.perf_counter();result=self.engine.load_public_precompute(self.package);self.prewarm_ms=(time.perf_counter()-start)*1000
        elif name=='MEASURE_CACHE':
            self.benchmark=measure_cache(self.root,self.engine);saving=self.benchmark['median_saving_ms']
            self.benchmark['memory_prewarm_ms']=self.prewarm_ms
            setup=self.bootstrap_ms+self.prewarm_ms
            self.benchmark['bootstrap_guard_and_package_ms']=self.bootstrap_ms
            self.benchmark['reuse_break_even_estimate']=math.ceil(setup/saving) if saving>0 else None
            self.benchmark['break_even_scope']='Estimate covers controller bootstrap and memory prewarm, excludes interpreter/import startup; assumes repeated public workload and this measured median saving.'
            result=self.benchmark
        else:raise ValueError('action is not authorized')
        self.actions.append({'action':name,'status':'OBSERVED_COMPLETED','result':result})
    def run(self,max_actions=3):
        if type(max_actions) is not int or not 1<=max_actions<=3:raise ValueError('max_actions must be 1..3')
        if source_fingerprint(self.root)!=self.revision:raise ValueError('source revision changed; restart before reusing imported code or cache')
        initial=len(self.actions);initial_rank=len(self.rankings)
        for _ in range(max_actions):
            ranked=self.candidates();self.rankings.append(ranked);eligible=[p for p in ranked if p['eligible']]
            if not eligible:break
            self.execute(eligible[0]['action'])
        remaining=self.candidates();self.rankings.append(remaining)
        report={'scope':'BOUNDED_LOCAL_DERIVED_WORK_NOT_AUTONOMOUS_SOURCE_OR_MODEL_EVOLUTION',
          'status':'NO_MATERIAL_DELTA' if len(self.actions)==initial else ('READY_NO_ELIGIBLE_ACTION' if not any(p['eligible'] for p in remaining) else 'BUDGET_EXHAUSTED'),
          'source_guard':self.guard,'revision':self.revision,'new_actions':self.actions[initial:],
          'rankings_recomputed':self.rankings[initial_rank:],'atomic_matrices':atomic_matrices(),'cache':self.engine.stats(),
          'benchmark':self.benchmark,'permission_boundary':{'source_edits':False,'weight_changes':False,'network_calls':False,'publishing':False,
             'canonical_antivirus_activation':False},
          'unknowns':['Neural benefit not improved by this cache.','No proof of malware protection or general language coverage.',
                      'Cache lives per process. Shipped public precompute can be reused across processes; arbitrary user text is not persisted.']}
        return json.loads(json.dumps(report,allow_nan=False)) # Snapshot, not a shared mutable controller view.


def _write_round_file(path, data, *, preserve=False):
    descriptor, name = tempfile.mkstemp(prefix='.autoround-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        if not preserve:
            temporary.replace(path)
            return
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass  # Concurrent writers can observe the same previous report.
    finally:
        temporary.unlink(missing_ok=True)


def _archive_round_file(history, data):
    digest = hashlib.sha256(data).hexdigest()
    path = history / f'{digest}.json'
    if not path.exists():
        _write_round_file(path, data, preserve=True)
    if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
        raise ValueError('round receipt conflicts with its SHA-256')
    return path, digest


def _round_paths(root):
    output = root / 'output'
    history = output / 'autoround-history'
    latest = output / 'AUTO_ROUND.json'
    if output.is_symlink() or history.is_symlink():
        raise ValueError('round report directories must be local directories')
    return history, latest


def _read_latest(latest):
    if latest.is_symlink() or (latest.exists() and not latest.is_file()):
        raise ValueError('latest round report must be a regular file')
    try:
        return latest.read_bytes()
    except FileNotFoundError:
        return None


def _is_sha256(value):
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _history_entries(history):
    try:
        entries = sorted(history.iterdir())
    except FileNotFoundError:
        entries = []
    receipts, auxiliary = {}, []
    for path in entries:
        if path.suffix == '.json' and _is_sha256(path.stem):
            receipts[path.stem] = path
        else:
            auxiliary.append(path.name)
    return receipts, auxiliary


def _receipt_parent(data):
    try:
        report = json.loads(data)
    except (ValueError, RecursionError):
        return False, None
    if not isinstance(report, dict) or _RECEIPT_METADATA.isdisjoint(report):
        return False, None
    report = loads(data.decode('utf-8'))
    if not _RECEIPT_METADATA <= report.keys() or not isinstance(report.get('rounds'), list):
        raise ValueError('incomplete round receipt metadata')
    previous = report['previous_sha256']
    if previous is not None and not _is_sha256(previous):
        raise ValueError('invalid previous receipt SHA-256')
    return True, previous


def verify_history(root, *, expected_receipt=None):
    """Audit archived bytes, predecessor references and the latest local view."""
    if expected_receipt is not None and not _is_sha256(expected_receipt):
        raise ValueError('expected receipt must be a lowercase SHA-256')
    history, latest = _round_paths(Path(root))
    latest_bytes = _read_latest(latest)
    latest_sha256 = None if latest_bytes is None else hashlib.sha256(latest_bytes).hexdigest()
    receipts, auxiliary = _history_entries(history)
    issues = [{'code': 'UNRECOGNIZED_RECEIPT_NAME', 'name': name}
              for name in auxiliary if name.endswith('.json')]
    checked = set()
    legacy_count = 0
    children = {}
    for digest, path in receipts.items():
        if path.is_symlink() or not path.is_file():
            issues.append({'code': 'RECEIPT_NOT_REGULAR', 'sha256': digest})
            continue
        try:
            data = path.read_bytes()
        except OSError:
            issues.append({'code': 'RECEIPT_UNREADABLE', 'sha256': digest})
            continue
        if hashlib.sha256(data).hexdigest() != digest:
            issues.append({'code': 'HASH_MISMATCH', 'sha256': digest})
            continue
        checked.add(digest)
        try:
            managed, previous = _receipt_parent(data)
        except ValueError:
            issues.append({'code': 'INVALID_LINEAGE', 'sha256': digest})
            continue
        if not managed:
            legacy_count += 1
        if previous is not None:
            children.setdefault(previous, []).append(digest)

    for previous, successors in children.items():
        if previous not in checked:
            code = 'UNVERIFIED_PREDECESSOR' if previous in receipts else 'MISSING_PREDECESSOR'
            issues.append({'code': code, 'sha256': previous, 'referenced_by': successors})
    if latest_sha256 is None and receipts:
        issues.append({'code': 'LATEST_MISSING'})
    if latest_sha256 is not None and latest_sha256 not in checked:
        code = 'LATEST_UNVERIFIED' if latest_sha256 in receipts else 'LATEST_UNARCHIVED'
        issues.append({'code': code, 'sha256': latest_sha256})
    if expected_receipt is not None and expected_receipt not in checked:
        code = 'EXPECTED_RECEIPT_UNVERIFIED' if expected_receipt in receipts else 'EXPECTED_RECEIPT_MISSING'
        issues.append({'code': code, 'sha256': expected_receipt})
    if receipts.keys() != _history_entries(history)[0].keys() or latest_bytes != _read_latest(latest):
        issues.append({'code': 'CONCURRENT_CHANGE'})

    status = 'NO_HISTORY'
    if issues:
        status = 'HOLD'
    elif receipts:
        status = 'HISTORY_VERIFIED'
    return {
        'status': status,
        'scope': 'LOCAL_RECEIPT_BYTES_AND_OBSERVED_LINKS',
        'receipt_files': len(receipts),
        'hash_verified_receipts': len(checked),
        'legacy_bytes_only': legacy_count,
        'latest_sha256': latest_sha256,
        'expected_receipt_sha256': expected_receipt,
        'forks': {parent: successors for parent, successors in children.items() if len(successors) > 1},
        'auxiliary_entries': auxiliary,
        'issues': issues,
    }


def persist_rounds(root, reports):
    """Preserve exact reports before advancing the compatible latest view."""
    history, latest = _round_paths(root)
    previous = _read_latest(latest)
    history.mkdir(parents=True, exist_ok=True)
    previous_sha256 = None
    if previous is not None:
        _, previous_sha256 = _archive_round_file(history, previous)

    payload = {
        'rounds': reports,
        'run_id': uuid4().hex,
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'previous_sha256': previous_sha256,
    }
    data = (json.dumps(payload, indent=2, allow_nan=False) + '\n').encode('utf-8')
    receipt, digest = _archive_round_file(history, data)
    _write_round_file(latest, data)
    return {
        'reports': str(latest.relative_to(root)),
        'receipt': str(receipt.relative_to(root)),
        'receipt_sha256': digest,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rounds', type=int)
    p.add_argument('--max-actions', type=int)
    p.add_argument('--verify-history', action='store_true', help='audit local receipts without running a round')
    p.add_argument('--expect-receipt', metavar='SHA256', help='require this receipt during the audit')
    a = p.parse_args(argv)
    if a.verify_history and (a.rounds is not None or a.max_actions is not None):
        p.error('--verify-history cannot be combined with round options')
    if not a.verify_history and a.expect_receipt is not None:
        p.error('--expect-receipt requires --verify-history')
    rounds = 1 if a.rounds is None else a.rounds
    max_actions = 3 if a.max_actions is None else a.max_actions
    if not 1 <= rounds <= 4:
        p.error('rounds must be 1..4')
    root = Path(__file__).resolve().parents[1]
    reports = None
    try:
        if a.verify_history:
            audit = verify_history(root, expected_receipt=a.expect_receipt)
            print(json.dumps(audit))
            return 0 if audit['status'] == 'HISTORY_VERIFIED' else 2
        controller = RoundController(root)
        reports = [controller.run(max_actions) for _ in range(rounds)]
        saved = persist_rounds(root, reports)
        print(json.dumps({'status': 'EXECUTED_LOCAL', **saved, 'round_statuses': [report['status'] for report in reports]}))
        return 0
    except (ValueError,TypeError,KeyError,OSError) as error:
        execution = 'STOPPED_OR_NOT_STARTED' if reports is None else 'COMPLETED_LOCAL'
        print(json.dumps({'status': 'HOLD', 'error': str(error), 'action_execution': execution}))
        return 2

if __name__=='__main__':raise SystemExit(main())
