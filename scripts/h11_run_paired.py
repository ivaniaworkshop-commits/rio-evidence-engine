"""H11: run H09 or legacy against actual private inputs or PUBLIC H10 diagnostic."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.paired_runner import REGISTRY,evaluate_paired

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle");p.add_argument("--diagnostic",action="store_true")
    p.add_argument("--candidate",choices=sorted(REGISTRY),default="h09")
    args=p.parse_args(argv)
    if not args.bundle and not args.diagnostic:
        print(json.dumps({"status":"BLOCKED_NO_EVALUATION_INPUT","candidate_promoted":False}))
        return 0
    if bool(args.bundle)==args.diagnostic:raise SystemExit("EXACTLY_ONE_INPUT_REQUIRED")
    if args.diagnostic:
        from evaluation.language_shift_probe import rows
        cases=[{"case_id":r["case_id"],"cluster":r["family"],"text":r["text"],"expected":r["expected"]} for r in rows()]
        source="PROJECT_AUTHORED_PUBLIC_H10"
    else:
        data=json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        if not isinstance(data,dict) or set(data)!={"cases"}:raise SystemExit("REJECT_EXTRA_OR_SELF_REPORTED_FIELDS")
        cases=data["cases"];source="SUBMITTED_PRIVATE_NOT_ATTESTED"
    print(json.dumps(evaluate_paired(cases,REGISTRY[args.candidate],source_class=source),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":raise SystemExit(main())
