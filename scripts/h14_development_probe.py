"""H14: authored standard-serialization evaluation, NOT independent data."""
import json
from evaluation.language_shift_probe import rows
from rio_evidence.candidate_v1 import extract_candidate_v1
from rio_evidence.extended_graph import extract_extended_graph
from rio_evidence.semantic_gate import grade

def run():
    records=rows()
    counts={"supported":0,"unsupported":0,"baseline_supported_exact":0,"candidate_supported_exact":0,
            "baseline_correct_abstentions":0,"candidate_correct_abstentions":0}
    per={}
    for r in records:
        family=per.setdefault(r["family"],{"n":0,"baseline_correct":0,"candidate_correct":0})
        b=grade(extract_extended_graph(r["text"])["graph"],r["expected"])["pass"]
        c=grade(extract_candidate_v1(r["text"])["graph"],r["expected"])["pass"]
        family["n"]+=1;family["baseline_correct"]+=int(b);family["candidate_correct"]+=int(c)
        if r["expected"] is not None:
            counts["supported"]+=1
            counts["baseline_supported_exact"]+=int(b)
            counts["candidate_supported_exact"]+=int(c)
        else:
            counts["unsupported"]+=1
            counts["baseline_correct_abstentions"]+=int(b)
            counts["candidate_correct_abstentions"]+=int(c)
    out={"scope":"PROJECT_AUTHORED_PUBLIC_DEV_DIAGNOSTIC_NOT_EXTERNAL","source":"H10",
         "candidate":"STRICT_CSV_JSON_V1","neural_parameters_added":0,
         "candidate_promoted":False,"independent_evaluation":False,**counts,"per_family":per}
    if (counts["supported"],counts["unsupported"],counts["baseline_supported_exact"],
        counts["candidate_supported_exact"],counts["candidate_correct_abstentions"]) != (40,12,0,5,12):
        raise ValueError("H14_DEVELOPMENT_DIAGNOSTIC_REGRESSION")
    return out
if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,indent=2))
