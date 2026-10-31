"""Standalone stdlib validator. Process separation is not human/data independence.

Run on a third-party machine with operator-reviewed clean frozen Git checkouts.
No package imports from the evaluated repo are used by the parent grader.
"""
import argparse,datetime,hashlib,json,math,os,re,statistics,subprocess,sys,tempfile
from pathlib import Path
SCHEMA='RIO_EXTERNAL_VALIDATOR_INPUT_V1'
TARGETS={'h09':('rio_evidence.extended_graph','extract_extended_graph'),
         'structured_v1':('rio_evidence.candidate_v1','extract_candidate_v1'),
         'spanish':('rio_evidence.spanish_graph','extract_spanish_graph')}
WORKER='''import importlib,json,sys,time
sys.path.insert(0,sys.argv[1])
fn=getattr(importlib.import_module(sys.argv[2]),sys.argv[3])
rows=json.load(sys.stdin);out=[]
for row in rows:
 start=time.perf_counter_ns()
 try:
  r=fn(row['text']);state=r.get('status');graph=r.get('graph')
  if state=='ABSTAIN' and graph is None:kind='ABSTAIN'
  elif state in ('EXPLICIT_GRAPH_RECOVERED','CLOSED_PATTERN_GRAPH_RECOVERED') and graph is not None:kind='GRAPH'
  else:kind='INVALID_INTERFACE'
 except Exception:kind='RUNTIME_ERROR';graph=None
 out.append({'case_id':row['case_id'],'kind':kind,'graph':graph,'latency_ms':(time.perf_counter_ns()-start)/1e6})
print(json.dumps(out,allow_nan=False))
'''
def loads(text):
    def pairs(rows):
        out={}
        for k,v in rows:
            if k in out:raise ValueError('DUPLICATE_JSON_KEY')
            out[k]=v
        return out
    def constant(_):raise ValueError('NONFINITE_JSON_NUMBER')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
def graph(value):
    if not isinstance(value,dict) or set(value)!={'tasks','durations'}:raise ValueError('INVALID_GRAPH_ENVELOPE')
    tasks=value['tasks'];durations=value['durations']
    if not isinstance(tasks,list) or not 1<=len(tasks)<=8 or not isinstance(durations,dict):raise ValueError('INVALID_GRAPH_SIZE')
    nodes={}
    for row in tasks:
        if not isinstance(row,dict) or set(row)!={'id','depends_on'}:raise ValueError('INVALID_TASK')
        key=row['id'];deps=row['depends_on']
        if not isinstance(key,str) or not re.fullmatch('[A-H]',key) or key in nodes:raise ValueError('INVALID_TASK_ID')
        if not isinstance(deps,list) or any(not isinstance(d,str) for d in deps) or len(set(deps))!=len(deps):raise ValueError('INVALID_DEPENDENCIES')
        nodes[key]=set(deps)
    if set(durations)!=set(nodes):raise ValueError('INCOMPLETE_DURATIONS')
    if any(type(v) is not int or not 0<=v<=1000000 for v in durations.values()):raise ValueError('INVALID_DURATION')
    if any(deps-set(nodes) for deps in nodes.values()):raise ValueError('UNKNOWN_PREDECESSOR')
    done=set()
    while len(done)<len(nodes):
        ready={k for k,v in nodes.items() if v<=done}-done
        if not ready:raise ValueError('CYCLE')
        done|=ready
    return (tuple((k,tuple(sorted(v))) for k,v in sorted(nodes.items())),tuple(sorted(durations.items())))
def iso(value):
    if not isinstance(value,str):raise ValueError('TIMESTAMP_STRING_REQUIRED')
    t=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.utcoffset() is None:raise ValueError('TIMEZONE_REQUIRED')
    return t
def validate_bundle(bundle,known_texts):
    if not isinstance(bundle,dict) or set(bundle)!={'schema','provenance','cases'} or bundle['schema']!=SCHEMA:raise ValueError('INVALID_BUNDLE')
    p=bundle['provenance']
    if not isinstance(p,dict) or set(p)!={'source_ref','frozen_at_utc','collected_at_utc'}:raise ValueError('INVALID_PROVENANCE')
    if not isinstance(p['source_ref'],str) or not 1<=len(p['source_ref'].strip())<=512:raise ValueError('SOURCE_REFERENCE_REQUIRED')
    if iso(p['frozen_at_utc'])>=iso(p['collected_at_utc']):raise ValueError('COLLECTION_MUST_FOLLOW_FREEZE')
    rows=bundle['cases']
    if not isinstance(rows,list) or not 1<=len(rows)<=500:raise ValueError('INVALID_CASE_COUNT')
    known={' '.join(t.casefold().split()) for t in known_texts};ids=set();texts=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'case_id','cluster','text','expected'}:raise ValueError('SUBMITTED_RESULTS_OR_INVALID_FIELDS')
        key=row['case_id'];cluster=row['cluster'];text=row['text']
        if not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',key) or key in ids:raise ValueError('INVALID_OR_DUPLICATE_ID')
        if not isinstance(cluster,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',cluster):raise ValueError('INVALID_CLUSTER')
        if not isinstance(text,str) or not text.strip() or len(text.encode())>4096:raise ValueError('INVALID_TEXT')
        normalized=' '.join(text.casefold().split())
        if normalized in known or normalized in texts:raise ValueError('KNOWN_OR_DUPLICATE_INPUT')
        if row['expected'] is not None:graph(row['expected'])
        ids.add(key);texts.add(normalized)
    return rows
def frozen(root,commit):
    root=Path(root).resolve()
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('FULL_COMMIT_REQUIRED')
    def git(*args):
        r=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,timeout=15)
        if r.returncode:raise ValueError('GIT_VERIFICATION_FAILED')
        return r.stdout.strip()
    if git('rev-parse','--show-toplevel')!=str(root) or git('rev-parse','HEAD')!=commit:raise ValueError('FROZEN_COMMIT_MISMATCH')
    if git('status','--porcelain','--untracked-files=all','--ignored'):raise ValueError('DIRTY_CHECKOUT')
    return root

def execute(root,commit,target,cases,python=sys.executable,timeout=60):
    if target not in TARGETS:raise ValueError('UNREGISTERED_TARGET')
    root=frozen(root,commit);module,function=TARGETS[target]
    request=[{'case_id':r['case_id'],'text':r['text']} for r in cases] # Never transmit labels.
    with tempfile.TemporaryDirectory(prefix='rio-external-worker-') as cwd:
        r=subprocess.run([python,'-I','-B','-c',WORKER,str(root),module,function],input=json.dumps(request),capture_output=True,text=True,cwd=cwd,timeout=timeout)
    frozen(root,commit) # Reject tracked or untracked changes caused during execution.
    if r.returncode or len(r.stdout.encode())>4*1024*1024:raise ValueError('WORKER_FAILED_OR_OUTPUT_TOO_LARGE')
    results=loads(r.stdout)
    if not isinstance(results,list) or len(results)!=len(cases):raise ValueError('WORKER_CASE_COUNT_MISMATCH')
    for expected,actual in zip(cases,results):
        if not isinstance(actual,dict) or set(actual)!={'case_id','kind','graph','latency_ms'} or actual['case_id']!=expected['case_id']:raise ValueError('WORKER_CASE_ID_MISMATCH')
        ms=actual['latency_ms']
        if type(ms) not in (int,float) or not math.isfinite(ms) or ms<0:raise ValueError('INVALID_LATENCY')
    return results

def correct(output,expected):
    if expected is None:return output['kind']=='ABSTAIN' and output['graph'] is None
    if output['kind']!='GRAPH':return False
    try:return graph(output['graph'])==graph(expected)
    except (ValueError,TypeError,KeyError):return False

def valid_output(output):
    if output['kind']=='ABSTAIN':return output['graph'] is None
    if output['kind']!='GRAPH':return False
    try:graph(output['graph']);return True
    except (ValueError,TypeError,KeyError):return False

def pvalue(wins,losses):
    n=wins+losses
    return sum(math.comb(n,i) for i in range(wins,n+1))/2**n if n else 1.
def compare(cases,baseline,candidate):
    if len(cases)!=len(baseline) or len(cases)!=len(candidate):raise ValueError('PAIRED_COUNT_MISMATCH')
    counts={'supported':0,'unsupported':0,'baseline_exact':0,'candidate_exact':0,'baseline_abstentions':0,'candidate_abstentions':0,'wins':0,'losses':0,'candidate_errors':0,'baseline_errors':0};clusters={}
    for row,a,b in zip(cases,baseline,candidate):
        if a['case_id']!=row['case_id'] or b['case_id']!=row['case_id']:raise ValueError('PAIRED_ID_MISMATCH')
        ca=correct(a,row['expected']);cb=correct(b,row['expected']);positive=row['expected'] is not None
        counts['supported' if positive else 'unsupported']+=1
        counts['baseline_exact' if positive else 'baseline_abstentions']+=int(ca)
        counts['candidate_exact' if positive else 'candidate_abstentions']+=int(cb)
        counts['wins']+=int(cb and not ca);counts['losses']+=int(ca and not cb)
        counts['candidate_errors']+=int(not valid_output(b))
        counts['baseline_errors']+=int(not valid_output(a))
        clusters[row['cluster']]=clusters.get(row['cluster'],0)+int(cb)-int(ca)
    cw=sum(v>0 for v in clusters.values());cl=sum(v<0 for v in clusters.values())
    ma=statistics.median(r['latency_ms'] for r in baseline);mb=statistics.median(r['latency_ms'] for r in candidate)
    technical=(counts['supported']>=30 and counts['unsupported']>=10 and len(clusters)>=5 and counts['candidate_exact']-counts['baseline_exact']>=5 and pvalue(counts['wins'],counts['losses'])<=.05 and cw>=5 and pvalue(cw,cl)<=.05 and counts['candidate_abstentions']>=counts['baseline_abstentions'] and counts['candidate_errors']==0 and mb<=max(3*ma,ma+5))
    return {**counts,'cluster_count':len(clusters),'cluster_wins':cw,'cluster_losses':cl,'conditional_p_descriptive':pvalue(counts['wins'],counts['losses']),'cluster_p_descriptive':pvalue(cw,cl),'baseline_median_ms':ma,'candidate_median_ms':mb,'technical_screen_pass':technical}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle');p.add_argument('--known-texts');p.add_argument('--baseline-checkout');p.add_argument('--candidate-checkout');p.add_argument('--baseline-commit');p.add_argument('--candidate-commit');p.add_argument('--candidate',choices=['structured_v1','spanish'],default='structured_v1');p.add_argument('--output');args=p.parse_args(argv)
    if args.bundle is None:
        print(json.dumps({'status':'BLOCKED_NO_EXTERNAL_DATA','independence_verified':False,'candidate_promoted':False}));return 2
    try:
        if not all((args.known_texts,args.baseline_checkout,args.candidate_checkout,args.baseline_commit,args.candidate_commit,args.output)):raise ValueError('CHECKOUTS_COMMITS_KNOWN_TEXTS_AND_PRIVATE_OUTPUT_REQUIRED')
        raw=Path(args.bundle).read_bytes()
        if len(raw)>4*1024*1024:raise ValueError('BUNDLE_EXCEEDS_4_MIB')
        bundle=loads(raw.decode());known_raw=Path(args.known_texts).read_bytes()
        if len(known_raw)>16*1024*1024:raise ValueError('KNOWN_TEXTS_EXCEEDS_16_MIB')
        known=loads(known_raw.decode())
        if not isinstance(known,list) or not known or any(not isinstance(x,str) or len(x.encode())>4096 for x in known):raise ValueError('KNOWN_TEXT_ARRAY_REQUIRED')
        rows=validate_bundle(bundle,known)
        for root in (args.baseline_checkout,args.candidate_checkout):
            if Path(args.output).resolve().is_relative_to(Path(root).resolve()):raise ValueError('OUTPUT_MUST_BE_OUTSIDE_FROZEN_CHECKOUTS')
        a=execute(args.baseline_checkout,args.baseline_commit,'h09',rows);b=execute(args.candidate_checkout,args.candidate_commit,args.candidate,rows)
        report={'schema':'RIO_EXTERNAL_VALIDATOR_REPORT_V1','status':'OBSERVED_FROZEN_PROCESS_COMPARISON_NOT_INDEPENDENT_CERTIFICATE','metrics':compare(rows,a,b),'baseline_commit':args.baseline_commit,'candidate_commit':args.candidate_commit,'candidate':args.candidate,'dataset_sha256':hashlib.sha256(raw).hexdigest(),'known_texts_sha256':hashlib.sha256(known_raw).hexdigest(),'independence_verified':False,'source_authenticated':False,'labels_independently_adjudicated':False,'candidate_promoted':False,'limits':['Run by project authors is not external independent validation.','Separate processes are not a security sandbox; execute only operator-reviewed source.','Labels withheld from worker messages are not guaranteed inaccessible to trusted code.','Exact overlap screening cannot exclude paraphrases, graph leakage or incomplete disclosure.','Git commits and hashes identify bytes, not source identity or correct labels.','Timings are one pass excluding interpreter startup; p-values are conditional on sampling assumptions.']}
        output=Path(args.output)
        with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
        print(json.dumps({'status':report['status'],'technical_screen_pass':report['metrics']['technical_screen_pass'],'independence_verified':False,'candidate_promoted':False}));return 0
    except (ValueError,TypeError,KeyError,OSError,subprocess.SubprocessError) as e:
        print(json.dumps({'status':'REJECTED','reason':str(e),'candidate_promoted':False}));return 2
if __name__=='__main__':raise SystemExit(main())
