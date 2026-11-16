(function () {
  'use strict';
  const root = document.getElementById('pey-setup');
  if (!root) return;

  const email = document.getElementById('pey-profile-email');
  const profileStatus = document.getElementById('pey-profile-status');
  const progressStatus = document.getElementById('pey-progress');
  const steps = Array.from(root.querySelectorAll('input[data-pey-step]'));
  const profileKey = 'rio.local.profile.v1';
  const stepNames = new Set(['perfil', 'cuenta', 'activa', 'clave']);
  let activeEmail = '';
  let storageAvailable = true;

  function progressKey(value) {
    return 'rio.pey.alta.v1:' + encodeURIComponent(value);
  }
  function status() {
    const count = steps.filter(step => step.checked).length;
    const storageText = !activeEmail ? ' Guarda un perfil para conservar el avance.' :
      storageAvailable ? ' Guardado en este navegador.' : ' No se pudo guardar en este navegador.';
    progressStatus.textContent = count + ' de 4 pasos declarados por ti.' + storageText +
      ' Configura pey en tu cuenta de Mercado Abierto para cobrar.';
  }
  function loadSteps() {
    let saved = {};
    if (activeEmail) {
      try {
        const value = JSON.parse(localStorage.getItem(progressKey(activeEmail)) || '{}');
        if (value && typeof value === 'object' && !Array.isArray(value)) saved = value;
      } catch (_) { storageAvailable = false; }
    }
    steps.forEach(step => { step.checked = saved[step.dataset.peyStep] === true; });
    status();
  }
  function activateProfile(value) {
    email.value = value.trim();
    if (!email.value || email.value.length > 254 || !email.validity.valid) {
      profileStatus.textContent = 'Ingresa un correo válido.';
      return;
    }
    activeEmail = email.value;
    storageAvailable = true;
    try {
      localStorage.setItem(profileKey, JSON.stringify({email: activeEmail}));
      profileStatus.textContent = 'Perfil local guardado en este navegador; correo no verificado.';
    } catch (_) {
      storageAvailable = false;
      profileStatus.textContent = 'No se pudo guardar el perfil; permanecerá solo mientras esta página esté abierta.';
    }
    loadSteps();
  }
  document.getElementById('pey-profile-save').addEventListener('click', () => activateProfile(email.value));
  steps.forEach(step => step.addEventListener('change', () => {
    if (activeEmail) {
      const values = {};
      steps.forEach(item => {
        if (stepNames.has(item.dataset.peyStep)) values[item.dataset.peyStep] = item.checked;
      });
      try { localStorage.setItem(progressKey(activeEmail), JSON.stringify(values)); }
      catch (_) { storageAvailable = false; }
    }
    status();
  }));
  document.getElementById('pey-progress-clear').addEventListener('click', () => {
    steps.forEach(step => { step.checked = false; });
    if (activeEmail) {
      try { localStorage.removeItem(progressKey(activeEmail)); }
      catch (_) { storageAvailable = false; }
    }
    status();
  });

  const params = new URLSearchParams(location.hash.slice(1));
  const incomingEmail = params.get('correo');
  if (incomingEmail && !params.has('token') && !params.has('owner_invite')) {
    activateProfile(incomingEmail);
    history.replaceState(null, '', location.pathname + location.search);
  } else {
    try {
      const saved = JSON.parse(localStorage.getItem(profileKey) || 'null');
      if (saved && typeof saved.email === 'string') activateProfile(saved.email);
      else status();
    } catch (_) {
      storageAvailable = false;
      profileStatus.textContent = 'El almacenamiento de este navegador no está disponible.';
      status();
    }
  }
})();
