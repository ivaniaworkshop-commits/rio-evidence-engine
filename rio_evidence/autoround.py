"""Finite derived-work controller. Never edits source, weights, permissions or publishes."""
import argparse,hashlib,importlib.util,json,math,statistics,time
from pathlib import Path
from .atomic_runtime import WarmRuntime,atomic_matrices,source_fingerprint,precompute_public
from .graph_copy import extract_graph
from .json_io import load


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


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rounds',type=int,default=1);p.add_argument('--max-actions',type=int,default=3);a=p.parse_args(argv)
    if not 1<=a.rounds<=4:p.error('rounds must be 1..4')
    root=Path(__file__).resolve().parents[1]
    try:
        controller=RoundController(root);reports=[controller.run(a.max_actions) for _ in range(a.rounds)]
        output=root/'output';output.mkdir(exist_ok=True)
        path=output/'AUTO_ROUND.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'rounds':reports},indent=2)+'\n');temporary.replace(path)
        print(json.dumps({'status':'EXECUTED_LOCAL','reports':str(path.relative_to(root)),'round_statuses':[r['status'] for r in reports]}));return 0
    except (ValueError,TypeError,KeyError,OSError) as error:
        print(json.dumps({'status':'HOLD','error':str(error),'action_execution':'STOPPED_OR_NOT_STARTED'}));return 2

if __name__=='__main__':raise SystemExit(main())
