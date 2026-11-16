"""Regresiones de la interfaz HTML multipágina unificada del hackatón."""
import hashlib
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "rio_pey_codi" / "static"
HUB = STATIC / "unificada" / "index.html"
CAJA = STATIC / "unificada" / "caja" / "index.html"
MERCADO = STATIC / "unificada" / "mercado" / "index.html"
ROOT = STATIC / "index.html"
MANIFEST = STATIC / "unificada" / "offline-manifiesto.js"
ROUTES = ("/#mis-negocios", "/#cobro-codi", "/static/unificada/mercado/index.html", "/mercado-abierto")


def read(path):
    return path.read_text(encoding="utf-8")


def test_tres_modulos_enlazados_desde_inicio():
    text = read(HUB)
    for route in ROUTES:
        assert f'href="{route}"' in text
    assert 'data-workspace-view="menu"' in read(ROOT)
    assert 'data-workspace-view="negocios"' in read(ROOT)
    assert 'href="/mercado-abierto"' in read(ROOT)
    assert "<iframe" not in text.lower()
    assert "<script>" not in text.lower()


def test_navegacion_de_retorno_en_tres_modulos():
    for page in (CAJA, MERCADO):
        text = read(page)
        assert 'href="/static/unificada/index.html"' in text
        routes = (("#rio-merchant-details", "/caja#cobro-codi", "/static/unificada/mercado/index.html", "/hackaton")
                  if page == ROOT else ("/", "/static/unificada/caja/index.html", "/static/unificada/mercado/index.html"))
        for route in routes:
            assert f'href="{route}"' in text


def test_shell_css_y_script_disponibles():
    text = read(HUB)
    assert 'src="/static/unificada/shell.js"' in text
    assert 'href="/static/unificada/shell.css"' in text
    assert (HUB.parent / "shell.css").is_file()
    assert (HUB.parent / "shell.js").is_file()


def test_manifest_offline_refleja_bytes_reales():
    raw = read(MANIFEST)
    match = re.fullmatch(r"globalThis\.RioOfflineManifest=Object\.freeze\((.*)\);\s*", raw, re.S)
    assert match
    doc = json.loads(match.group(1))
    assets = doc["assets"]
    assert len(assets) == 19
    assert all(not asset.endswith(".html") for asset in assets)
    for asset, expected in assets.items():
        assert asset.startswith("/static/unificada/")
        target = STATIC / asset.removeprefix("/static/")
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected, asset
    canonical = json.dumps(assets, sort_keys=True, separators=(",", ":")).encode()
    expected_cache = "rio-unificada-" + hashlib.sha256(canonical).hexdigest()[:20]
    assert doc["cache"] == expected_cache
    for asset in ("shell.css", "shell.js", "caja/caja-1.js", "mercado/app.js"):
        assert "/static/unificada/" + asset in assets
