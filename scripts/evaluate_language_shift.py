"""Paired format-shift diagnostic. Print observations; never pretend independent."""
import json,hashlib,statistics,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.language_shift_probe import rows
from rio_evidence.independent_gate import _known_text
from rio_evidence.graph_copy import extract_graph
from rio_evidence.extended_graph import extract_extended_graph
from rio_evidence.semantic_gate import grade,canonical

def run():
    cases=rows();known=_known_text(ROOT)
    if len(cases)!=52 or len(set(c["case_id"] for c in cases))!=52:raise ValueError("BAD_CASE_IDS")
    fam={};old_s=new_s=old_n=new_n=0;ta=[];tb=[]
    for c in cases:
        if " ".join(c["text"].casefold().split()) in known:raise ValueError("TRAIN_DEV_TEXT_OVERLAP")
        if (c["kind"]=="supported")!=(c["expected"] is not None):raise ValueError("BAD_REFERENCE_KIND")
        if c["expected"] is not None:canonical(c["expected"])
        start=time.perf_counter_ns();a=extract_graph(c["text"]);ta.append((time.perf_counter_ns()-start)/1e6)
        start=time.perf_counter_ns();b=extract_extended_graph(c["text"]);tb.append((time.perf_counter_ns()-start)/1e6)
        p=grade(a["graph"],c["expected"])["pass"];q=grade(b["graph"],c["expected"])["pass"]
        d=fam.setdefault(c["family"],{"cases":0,"old_pass":0,"h09_pass":0})
        d["cases"]+=1;d["old_pass"]+=int(p);d["h09_pass"]+=int(q)
        if c["kind"]=="supported":old_s+=int(p);new_s+=int(q)
        else:old_n+=int(p);new_n+=int(q)
    return {"status":"OBSERVED_PROJECT_AUTHORED_DIAGNOSTIC_NOT_INDEPENDENT",
        "case_count":len(cases),"supported":40,"negative":12,
        "baseline_supported_exact":old_s,"h09_supported_exact":new_s,
        "baseline_correct_abstentions":old_n,"h09_correct_abstentions":new_n,
        "families":fam,"baseline_median_ms":statistics.median(ta),
        "h09_median_ms":statistics.median(tb),
        "dataset_sha256":hashlib.sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest(),
        "external_independence":False,"candidate_promoted":False,
        "limits":"Eight author-generated wording patterns with repeated numbers are correlated; never call these external human inputs."}
if __name__=="__main__":print(json.dumps(run(),sort_keys=True,indent=2))
