(() => {
  'use strict';
  const root = document.documentElement;
  const login = () => '/login?next=' + encodeURIComponent(location.pathname);
  function lock() {
    delete root.dataset.sessionReady;
    window.RioWorkspace?.lock();
  }
  async function check() {
    lock();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/v1/auth/me', {credentials:'same-origin', cache:'no-store',
        signal:controller.signal, headers:{Accept:'application/json'}});
      if (response.status === 401 || response.status === 403) { location.replace(login()); return; }
      if (!response.ok) throw Error();
      const me = await response.json();
      if (typeof me.id !== 'string' || !me.id) throw Error();
      root.dataset.sessionReady = 'true';
    } catch (_) {
      const main = document.createElement('main');
      main.className = 'shell';
      const title = document.createElement('h1');
      title.textContent = 'No pudimos comprobar tu sesión';
      const text = document.createElement('p');
      text.textContent = 'Conéctate a Internet y vuelve a intentar.';
      const link = document.createElement('a');
      link.href = login(); link.textContent = 'Volver al acceso';
      main.append(title, text, link);
      document.body.replaceChildren(main);
      root.dataset.sessionReady = 'true';
    } finally { clearTimeout(timer); }
  }
  window.addEventListener('pagehide', lock);
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
  try {
    const channel = new BroadcastChannel('rio-session');
    channel.addEventListener('message', event => {
      if (event.data === 'logout') { lock(); location.replace(login()); }
    });
    window.RioSession = Object.freeze({lock, logout() { channel.postMessage('logout'); lock(); }});
  } catch (_) { window.RioSession = Object.freeze({lock, logout:lock}); }
  void check();
})();
