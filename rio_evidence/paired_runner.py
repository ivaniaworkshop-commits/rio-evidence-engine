"""H11 local observed paired runner. Not an external evaluator or sandbox."""
import hashlib,json,re,statistics,time
from pathlib import Path
from .extended_graph import extract_extended_graph
from .graph_copy import extract_graph
from .independent_gate import _known_text,_one_sided_exact_p
from .semantic_gate import canonical,grade

ROOT=Path(__file__).resolve().parents[1]
REGISTRY={"h09":extract_extended_graph,"legacy":extract_graph}
FIELDS={"case_id","cluster","text","expected"}

def _run(fn,text):
    try:
        r=fn(text)
        if not isinstance(r,dict):return ("INVALID_INTERFACE",None)
        state,graph=r.get("status"),r.get("graph")
        if state=="ABSTAIN" and graph is None:return ("ABSTAIN",None)
        if state not in ("CLOSED_PATTERN_GRAPH_RECOVERED","EXPLICIT_GRAPH_RECOVERED") or graph is None:
            return ("INVALID_INTERFACE",None)
        canonical(graph)
        return ("GRAPH",graph)
    except Exception:
        return ("RUNTIME_ERROR",None)

def _correct(out,expected):
    if expected is None:return out[0]=="ABSTAIN"
    return out[0]=="GRAPH" and bool(grade(out[1],expected)["pass"])

def _check(cases,root):
    if not isinstance(cases,list) or not 1<=len(cases)<=500:raise ValueError("INVALID_CASE_COUNT")
    ids=set();known=_known_text(root)
    for row in cases:
        if not isinstance(row,dict) or set(row)!=FIELDS:raise ValueError("REJECT_SUBMITTED_OUTPUT_OR_LATENCY")
        key,cluster,text=row["case_id"],row["cluster"],row["text"]
        if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",key) or key in ids:
            raise ValueError("INVALID_OR_DUPLICATE_ID")
        ids.add(key)
        if not isinstance(cluster,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",cluster):
            raise ValueError("INVALID_CLUSTER")
        if not isinstance(text,str) or not text.strip() or len(text.encode())>4096:raise ValueError("INVALID_TEXT")
        if " ".join(text.casefold().split()) in known:raise ValueError("TRAIN_DEV_OVERLAP")
        if row["expected"] is not None:canonical(row["expected"])

def evaluate_paired(cases,candidate,*,baseline=extract_extended_graph,root=ROOT,repetitions=3,source_class="UNAUTHENTICATED"):
    if not callable(candidate) or not callable(baseline):raise ValueError("TRUSTED_CALLABLE_REQUIRED")
    if type(repetitions) is not int or repetitions not in (1,3,5,7):raise ValueError("REPETITIONS_INVALID")
    _check(cases,root)
    pos_a=pos_b=neg_a=neg_b=wins=losses=err_a=err_b=0;ta=[];tb=[];observations=[]
    for i,row in enumerate(cases):
        a=[];b=[];la=[];lb=[];funcs=[("a",baseline),("b",candidate)]
        for j in range(repetitions):
            for name,fn in (funcs if (i+j)%2==0 else funcs[::-1]):
                start=time.perf_counter_ns();out=_run(fn,row["text"]);elapsed=(time.perf_counter_ns()-start)/1e6
                if name=="a":a.append(out);la.append(elapsed)
                else:b.append(out);lb.append(elapsed)
        canonicalized=lambda x:json.dumps(x,sort_keys=True,allow_nan=False)
        if any(canonicalized(x)!=canonicalized(a[0]) for x in a) or any(canonicalized(x)!=canonicalized(b[0]) for x in b):
            raise ValueError("NONDETERMINISTIC_OUTPUT_REQUIRES_ALTERNATE_PROTOCOL")
        expected=row["expected"];correct_a=_correct(a[0],expected);correct_b=_correct(b[0],expected)
        if expected is None:neg_a+=int(correct_a);neg_b+=int(correct_b)
        else:pos_a+=int(correct_a);pos_b+=int(correct_b)
        err_a+=int(a[0][0] in ("RUNTIME_ERROR","INVALID_INTERFACE"))
        err_b+=int(b[0][0] in ("RUNTIME_ERROR","INVALID_INTERFACE"))
        wins+=int(correct_b and not correct_a);losses+=int(correct_a and not correct_b)
        ta.extend(la);tb.extend(lb)
        observations.append({"case_id_sha256":hashlib.sha256(row["case_id"].encode()).hexdigest(),
            "cluster":row["cluster"],"baseline_correct":correct_a,"candidate_correct":correct_b,
            "baseline_status":a[0][0],"candidate_status":b[0][0],
            "baseline_ms":statistics.median(la),"candidate_ms":statistics.median(lb)})
    p= _one_sided_exact_p(wins,losses)
    npos=sum(r["expected"] is not None for r in cases);nneg=len(cases)-npos
    meda=statistics.median(ta);medb=statistics.median(tb)
    engineering=(npos>=30 and nneg>=10 and len({r["cluster"] for r in cases})>=5
        and pos_b-pos_a>=5 and wins>losses and p<=0.05 and neg_b>=neg_a
        and err_b==0 and medb<=max(3*meda,meda+5))
    return {"status":"OBSERVED_IN_PROCESS_NOT_INDEPENDENT_ATTESTATION",
        "candidate_promoted":False,"source_class_declared":source_class,
        "source_class_verified":False,"independent_evaluator_authenticated":False,
        "baseline":"CURRENT_H09_WORKTREE_EXECUTED","candidate":"TRUSTED_CALLABLE_EXECUTED",
        "cases":len(cases),"supported":npos,"unsupported":nneg,
        "clusters_declared":len({r["cluster"] for r in cases}),
        "dataset_sha256":hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "baseline_supported_exact":pos_a,"candidate_supported_exact":pos_b,
        "baseline_correct_abstentions":neg_a,"candidate_correct_abstentions":neg_b,
        "candidate_wins":wins,"candidate_losses":losses,
        "conditional_one_sided_p_descriptive":p,"baseline_invalid_or_error":err_a,
        "candidate_invalid_or_error":err_b,"baseline_observed_median_ms":meda,
        "candidate_observed_median_ms":medb,"repetitions":repetitions,
        "preliminary_engineering_screen":engineering,"financial_cost":"UNKNOWN",
        "observations":observations,
        "limits":["Local trusted functions executed; revisions and human source authenticity not attested.",
          "Self-reported labels and clustered samples are not independently validated.",
          "Wall clock is not financial cost; conditional p is not a generalization guarantee.",
          "No output here can automatically promote a model."]}
