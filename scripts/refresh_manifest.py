"""Explicit build helper; run only after authorized changes and validation."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','__pycache__','.venv','output'}
if __name__=='__main__':
    files=[f for f in ROOT.rglob('*') if f.is_file() and f.name!='MANIFEST.json' and not (set(f.relative_to(ROOT).parts)&EXCLUDED)]
    manifest={'scope':'SOURCE_BYTES_NOT_TRUTH_OR_AUTHENTICITY','files':[{'path':str(f.relative_to(ROOT)),
      'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(files)]}
    path=ROOT/'MANIFEST.json';temp=ROOT/'MANIFEST.tmp'
    temp.write_text(json.dumps(manifest,indent=2)+'\n');temp.replace(path)
    print(json.dumps({'files':len(files),'guard':'BUILD_ONLY_NOT_AN_AUTOMATIC_REPAIR_OF_UNTRUSTED_SOURCE'}))
