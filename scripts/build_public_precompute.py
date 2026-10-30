"""Precompute only published authored examples, never arbitrary caller input."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.atomic_runtime import precompute_public
if __name__=='__main__':
    package=precompute_public(ROOT)
    (ROOT/'runtime/PUBLIC_PRECOMPUTE.json').write_text(json.dumps(package,indent=2)+'\n')
    print(json.dumps({'public_cases':len(package['records']),'source_revision':package['source_revision']}))
