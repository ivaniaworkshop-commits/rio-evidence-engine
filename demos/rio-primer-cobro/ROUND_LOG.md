# R014 — Registro de rondas

- R014.1 · OBSERVADO: R013 no conservaba ventas activas ni tickets tras recargar; `Nueva venta` descartaba venta activa.
- R014.2 · EJECUTADO: snapshot local validado con importe exacto, eventos reconciliados, historial de 50, respaldo JSON, recuperación y controles de error.
- R014.3 · PROBADO: persistencia Node 20/20; Chromium en memoria 61/61 (móvil/escritorio); núcleo 67/67; QR 60/60; HTTP 5/5; generación de reporte 106/106.
- R014.4 · PENDIENTE: publicación GitHub y readback. Main sin modificación.

No hay pago real ni prueba en Android físico; SIMULACIÓN != OBSERVACIÓN EXTERNA.
