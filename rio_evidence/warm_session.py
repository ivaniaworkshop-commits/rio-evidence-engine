"""Bounded persistent JSONL session; caller inputs remain process-local."""
import argparse,json,sys
from pathlib import Path
from .atomic_runtime import WarmRuntime,source_fingerprint
from .autoround import verify_source
from .json_io import loads


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prewarm-public',action='store_true');p.add_argument('--max-requests',type=int,default=1000);a=p.parse_args(argv)
    if not 1<=a.max_requests<=10000:p.error('max-requests must be 1..10000')
    root=Path(__file__).resolve().parents[1]
    try:
        verify_source(root);engine=WarmRuntime(source_fingerprint(root))
        if a.prewarm_public:
            package=json.loads((root/'runtime/PUBLIC_PRECOMPUTE.json').read_text())
            import hashlib
            expected=hashlib.sha256((root/'training/extraction_dev.jsonl').read_bytes()).hexdigest()
            if package['source_data_sha256']!=expected:raise ValueError('public data revision mismatch')
            engine.load_public_precompute(package)
        for index in range(a.max_requests):
            # Bounded readline avoids buffering arbitrarily long caller input.
            raw=sys.stdin.buffer.readline(1024*1024+2)
            if not raw:break
            if len(raw)>1024*1024:raise ValueError('JSONL request exceeds 1 MiB')
            try:
                row=loads(raw.decode('utf-8'))
                if not isinstance(row,dict) or set(row)!={'text'}:raise ValueError('expected text field only')
                result=engine.graph(row['text'])
                print(json.dumps({'request':index+1,'status':'EXECUTED_LOCAL','result':result,'cache':engine.stats()}),flush=True)
            except (ValueError,TypeError,KeyError):
                print(json.dumps({'request':index+1,'status':'HOLD','reason':'INVALID_INPUT','cache':engine.stats()}),flush=True)
        return 0
    except (ValueError,TypeError,KeyError,OSError) as error:
        print(json.dumps({'status':'HOLD','error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
