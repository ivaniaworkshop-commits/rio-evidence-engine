import json
import tempfile
from pathlib import Path
from rio_evidence.core import critical_path, compare_results, append_event, read_events

def main():
    tasks=[{"id":"read"},{"id":"validate","depends_on":["read"]},{"id":"report","depends_on":["validate"]}]
    schedule=critical_path(tasks,{"read":1,"validate":2,"report":1})
    baseline=[{"case_id":"example","correct":False,"latency_ms":10}]
    candidate=[{"case_id":"example","correct":True,"latency_ms":10}]
    delta=compare_results(baseline,candidate)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"journal.jsonl"
        append_event(path,{"event_id":"DEMO1","task_id":"report","phase":"DEMO","status":"PASS","evidence_ref":"synthetic/example","version":"demo1","elapsed_ms":None,"attempt":1,"calls":0,"tokens_in":None,"tokens_out":None,"cost_usd":None})
        journal_count=len(read_events(path))
    print(json.dumps({"scope":"SYNTHETIC_DEMO_NOT_MEASURED_PRODUCT_IMPROVEMENT","schedule":schedule,"synthetic_delta":delta,"journal_events":journal_count},indent=2))

if __name__ == "__main__": main()
