"""R011: UI route/action inventory and session-boundary regression contracts."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]/"rio_pey_codi"/"static"/"unificada"/"hackaton"
JS=ROOT/"app.js"
HTML=ROOT/"index.html"
VIEWS={"panel","mercado","solicitudes","ofertas","pedidos","fletes","caja","inventario","negocios","tickets","historial"}

def source():return JS.read_text(encoding="utf8")

def test_eleven_real_views_and_router():
 s=source()
 assert all(re.search(r"\b"+view+r"\b",s) for view in VIEWS)
 assert "const PAGES={panel,centro,mercado,solicitudes,ofertas,pedidos,fletes,caja,inventario,negocios,tickets,historial,admin,cuenta}" in s
 assert "window.RIO_DEMO=" in s

def test_all_direct_button_handlers_exist():
 s=source()
 actions=set(re.findall(r"btn\([^,]+,\s*'([^']+)'",s))
 cases=set(re.findall(r"case '([^']+)':",s))
 assert not {a for a in actions if a not in cases and not a.startswith("go-")}

def test_forms_all_have_handlers():
 s=source()
 declared=set(re.findall(r'data-form="([^"]+)"',s))
 cases=set(re.findall(r"case '([^']+)':",s))
 assert declared<=cases
 assert {"business","product","rfq","offer","freight","checkout"}<=declared

def test_session_memory_cleared_on_all_failure_paths():
 s=source()
 for marker in ("storageKey=null","state=seed()","marketCart={}","posCart={}","appReady=false","adminState.csrf=''","modalRoot"):
  assert marker in s
 assert "invalidateSession(e.status===401?'Sesión terminada':'No se pudo revalidar la sesión; interfaz bloqueada')" in s
 assert "data.user.id!==adminState.user?.id" in s
 assert "invalidateSession('Sesión cerrada')" in s
 assert "invalidateSession('Sesión terminada')" in s

def test_modal_keyboard_navigation():
 s=source()
 for marker in ("modalReturnFocus=document.activeElement","modalReturnFocus?.isConnected","e.key!=='Tab'","e.shiftKey","last.focus()","first.focus()","e.key==='Escape'"):
  assert marker in s
 assert 'id="modalRoot"' in HTML.read_text(encoding="utf8")

def test_demo_money_and_privilege_boundaries():
 s=source()
 assert "r010_gateway_user_" in s
 assert "admin.dashboard.read" in s
 assert "No se pudo revalidar la sesión; interfaz bloqueada" in s
 manifest=(ROOT/"manifest.json").read_text(encoding="utf8")
 assert '"real_payments": false' in manifest
 assert '"admin_r003_grants": false' in manifest
