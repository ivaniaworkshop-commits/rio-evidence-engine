/* Datos sintéticos entre pantallas del mismo origen. No autoriza pagos. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.RioBridge = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const BASKET_KEY = 'rio.unificada.basket.v1';
  const SALE_KEY = 'rio.unificada.sale.v1';
  const MAX_AGE_MS = 15 * 60 * 1000;
  const MAX_AMOUNT = 100000000;
  const exact = (obj, keys) => obj && typeof obj === 'object' && !Array.isArray(obj) &&
    Object.keys(obj).sort().join('|') === keys.slice().sort().join('|');
  const fail = text => { throw new Error(text); };
  const integer = (v, low, high) => Number.isSafeInteger(v) && v >= low && v <= high;

  function validatePayload(kind, payload) {
    if (kind === 'basket') {
      if (!exact(payload, ['lines']) || !Array.isArray(payload.lines) ||
          !payload.lines.length || payload.lines.length > 30) fail('Cesta de prueba inválida.');
      let total = 0;
      for (const item of payload.lines) {
        if (!exact(item, ['name', 'quantity', 'priceCents']) ||
            typeof item.name !== 'string' || !/^[\p{L}\p{N} ._-]{1,70}$/u.test(item.name) ||
            !integer(item.quantity, 1, 1000000) || !integer(item.priceCents, 0, MAX_AMOUNT)) {
          fail('Producto de prueba inválido.');
        }
        const amount = item.quantity * item.priceCents;
        if (!Number.isSafeInteger(amount) || amount > MAX_AMOUNT || total + amount > MAX_AMOUNT) {
          fail('La cesta supera el importe permitido.');
        }
        total += amount;
      }
      return { lines: payload.lines.map(x => ({name:x.name, quantity:x.quantity, priceCents:x.priceCents})), totalCents:total };
    }
    if (kind === 'sale') {
      if (!exact(payload, ['saleId', 'amountCents']) ||
          typeof payload.saleId !== 'string' || !/^DEMO-[A-Z0-9-]{4,40}$/.test(payload.saleId) ||
          !integer(payload.amountCents, 1, MAX_AMOUNT)) fail('Venta de prueba inválida.');
      return {saleId:payload.saleId, amountCents:payload.amountCents};
    }
    return fail('Tipo de transferencia desconocido.');
  }
  function encode(kind, payload, now = Date.now()) {
    if (!integer(now, 0, Number.MAX_SAFE_INTEGER)) fail('Fecha inválida.');
    const normalized = validatePayload(kind, payload);
    const clean = kind === 'basket' ? {lines:normalized.lines} : normalized;
    return JSON.stringify({schema:'RIO_TRANSFER_V1', kind, classification:'SYNTHETIC_ONLY', created:now, payload:clean});
  }
  function decode(raw, expected, now = Date.now()) {
    if (typeof raw !== 'string' || raw.length > 16000) fail('Transferencia no disponible o demasiado grande.');
    let obj; try { obj = JSON.parse(raw); } catch (_) { return fail('Transferencia dañada.'); }
    if (!exact(obj, ['schema','kind','classification','created','payload']) ||
        obj.schema !== 'RIO_TRANSFER_V1' || obj.kind !== expected || obj.classification !== 'SYNTHETIC_ONLY' ||
        !integer(obj.created, 0, Number.MAX_SAFE_INTEGER) || !integer(now, 0, Number.MAX_SAFE_INTEGER) ||
        obj.created > now + 30000 || now - obj.created > MAX_AGE_MS) fail('Transferencia inválida o vencida.');
    return validatePayload(expected, obj.payload);
  }
  return Object.freeze({BASKET_KEY,SALE_KEY,MAX_AGE_MS,MAX_AMOUNT,encode,decode});
});
