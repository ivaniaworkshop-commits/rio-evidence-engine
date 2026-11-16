"""R010 fail-closed static checks for the currently integrated shell."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/"rio_pey_codi"/"static"
HUB=STATIC/"unificada"/"index.html"
MANIFEST=STATIC/"unificada"/"offline-manifiesto.js"
HACK=STATIC/"unificada"/"hackaton"
def test_hackaton_link_on_latest_shell():
    text=HUB.read_text(encoding="utf8")
    assert 'href="/mercado-abierto" data-module="operaciones"' in text
    assert '<iframe' not in text.lower()
def test_hash_manifest_matches_shell_bytes():
    js=MANIFEST.read_text(encoding="utf8")
    prefix="globalThis.RioOfflineManifest=Object.freeze("
    assert js.startswith(prefix)
    manifest=json.loads(js[len(prefix):].rstrip().removesuffix(");"))
    assert all(not asset.endswith(".html") for asset in manifest["assets"])
    assert manifest["assets"]["/static/unificada/shell.js"]==hashlib.sha256((HUB.parent/"shell.js").read_bytes()).hexdigest()
    canon=json.dumps(manifest["assets"],sort_keys=True,separators=(",",":")).encode()
    assert manifest["cache"]=="rio-unificada-"+hashlib.sha256(canon).hexdigest()[:20]
def test_csp_compatible_hackaton_sources():
    html=(HACK/"index.html").read_text(encoding="utf8")
    assert "<script>" not in html
    assert "<style>" not in html
    assert 'src="/static/unificada/hackaton/app.js"' in html
    assert 'href="/static/unificada/hackaton/app.css"' in html
def test_runtime_files_exist():
    for file in ("index.html","app.js","app.css","manifest.json"):
        assert (HACK/file).is_file()
def test_original_3_modules_preserved():
    for f in (STATIC/"index.html",STATIC/"unificada"/"caja"/"index.html",STATIC/"unificada"/"mercado"/"index.html"):
        text=f.read_text(encoding="utf8")
        assert 'data-session-required="true"' in text
        assert 'src="/static/session-guard.js"' in text
def test_identity_hook_registered():
    code=(ROOT/"rio_pey_codi"/"platform.py").read_text(encoding="utf8")
    assert "register_hackaton_routes(app, accounts)" in code
    assert code.index("app.include_router(router_for(accounts))")<code.index("register_hackaton_routes(app, accounts)")<code.index("app.mount('/static'")
