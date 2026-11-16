"""Read-only browser request failures must terminate without retrying writes."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_request_deadlines_and_session_landing():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is unavailable')
    script = Path(__file__).with_name('request_timeout_ui.cjs')
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20, check=True)
    assert 'REQUEST_TIMEOUT_UI_OK' in result.stdout
