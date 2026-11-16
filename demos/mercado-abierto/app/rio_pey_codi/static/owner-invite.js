(function () {
  'use strict';
  const params = new URLSearchParams(location.hash.slice(1));
  let invitation = params.get('owner_invite');
  if (!invitation) return;
  history.replaceState(null, '', location.pathname + location.search);

  const panel = document.getElementById('owner-activation');
  const status = document.getElementById('owner-activation-status');
  const first = document.getElementById('owner-password');
  const second = document.getElementById('owner-password-confirm');
  const button = document.getElementById('owner-activate');
  panel.hidden = false;
  if (!/^[A-Za-z0-9_-]{43}$/.test(invitation)) {
    status.textContent = 'La invitación no tiene un formato válido.';
    button.disabled = true;
    invitation = '';
    return;
  }
  button.addEventListener('click', async () => {
    const password = first.value;
    if (password !== second.value || Array.from(password).length < 12 ||
        Array.from(password).length > 256) {
      status.textContent = 'Usa entre 12 y 256 caracteres e ingresa la misma contraseña dos veces.';
      return;
    }
    button.disabled = true;
    status.textContent = 'Activando acceso…';
    try {
      const response = await fetch('/v1/auth/activate-owner', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({token: invitation, password}),
      });
      if (!response.ok) throw Error('No fue posible activar. La invitación puede haber vencido o ya haberse usado.');
      const result = await response.json();
      if (result.status !== 'OWNER_ACCESS_ACTIVATED' || result.email_verified !== false)
        throw Error('No se pudo confirmar la activación.');
      invitation = '';
      first.value = '';
      second.value = '';
      status.textContent = 'Acceso activado por invitación. Tu correo sigue sin verificar. Ya puedes iniciar sesión.';
    } catch (_) {
      status.textContent = 'No se pudo activar. Si acabas de enviar la solicitud, intenta iniciar sesión; si no, abre de nuevo la invitación.';
    } finally {
      button.disabled = !invitation;
    }
  });
})();
