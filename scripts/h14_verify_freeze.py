"""H14: verify code bytes against the frozen pre-external-evaluation receipt."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rio_evidence.freeze_guard import verify_freeze
if __name__=="__main__":print(json.dumps(verify_freeze(),sort_keys=True))
