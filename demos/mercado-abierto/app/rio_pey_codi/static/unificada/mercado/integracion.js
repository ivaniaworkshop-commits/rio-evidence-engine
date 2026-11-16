(function () {
  'use strict';
  const button = document.getElementById('rio-basket-to-cash');
  const status = document.getElementById('rio-market-transfer-status');
  button.addEventListener('click', () => {
    try {
      const source = globalThis.RIO_BOOTSTRAP.scenario.basket;
      const lines = source.map(item => ({
        name: String(item.sku).replace(/_/g, ' '),
        quantity: item.qty,
        priceCents: Math.round(item.retail_unit * 100)
      }));
      const raw = RioBridge.encode('basket', {lines});
      if (sessionStorage.getItem(RioBridge.BASKET_KEY) !== null) throw Error('Ya hay una cesta pendiente; ábrela o descártala en la caja.');
      sessionStorage.setItem(RioBridge.BASKET_KEY, raw);
      if (sessionStorage.getItem(RioBridge.BASKET_KEY) !== raw) throw Error('No se pudo guardar el traslado.');
      window.location.assign('/static/unificada/caja/index.html');
    } catch (error) {
      status.textContent = 'No se pudo preparar la cesta ficticia: ' + String(error.message || error);
    }
  });
})();
