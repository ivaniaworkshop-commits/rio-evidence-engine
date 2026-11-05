# RÍO Primer Cobro — R013

**Demostración educativa local para negocios pequeños: carrito, efectivo, QR de práctica, ticket y ayuda contextual.** Proyecto en español, pensado primero para teléfonos. No es una aplicación financiera operativa.

## Abrir

Descarga `RIO_PRIMER_COBRO_R013_OFFLINE.html` y ábrelo en un navegador con JavaScript. El archivo no necesita conexión ni servidor. Desde `app/` también puedes levantar el servidor local opcional con `node server/dev_server.mjs`, iniciándolo desde la raíz del paquete; esto no configura ningún banco ni API.

## Recorrido de práctica

1. En **Caja**, usa «Rellenar ejemplo» y «Agregar al carrito», o agrega tus propios productos por pieza o gramos.
2. Edita cantidades o quita artículos. Los importes se calculan en centavos enteros y `BigInt` para peso.
3. Elige **Efectivo** o **QR de práctica**. Crea la venta, que bloquea el carrito para mantener el ticket consistente.
4. Para efectivo, escribe el importe recibido y registra el cambio. Esto **sólo documenta una declaración manual**.
5. Para QR, toca **Generar QR para esta venta**: aparece un código QR versión 5-L que incluye folio e importe exacto. Es **NO PAGABLE** y no es CoDi, DiMo, un webhook ni un enlace bancario. Pulsa los botones de simulación para aprender estados pendientes o confirmaciones *simuladas*.
6. Descarga el QR SVG; el ticket puede descargarse, imprimirse, copiarse, o prepararse para correo/WhatsApp. Tú eliges destinatario y confirmas el envío en la aplicación externa.
7. En **Reporte**, toca «Ejecutar pruebas y generar JSON»: se vuelven a ejecutar las pruebas internas del navegador. Nunca presenta las pruebas externas como ejecutadas mediante ese botón.

## Núcleo y privacidad

- QR local de ASCII impreso; no incluye credenciales, cuentas ni datos bancarios. Su texto tiene el marcador `RIO-QR-DEMO|NO-PAGABLE` y el folio/importe, únicamente para uso educativo.
- Código QR: implementación original local JS (v5, ECC L, máscara 0); sin librerías de terceros en el navegador ni CDN.
- Carrito en localStorage cuando esté disponible; la venta activa y su ticket sólo existen en la sesión actual. Exporta antes de cerrar.
- Chat local con reglas; **no hay IA generativa activa por defecto**. El servidor opcional requiere configuración por separado; nunca confirma pagos.
- Telemetría: categorías locales sólo con consentimiento; no se entrena automáticamente un modelo ni se transmiten categorías.
- Tickets: **no son CFDI ni comprobantes de una transferencia o depósito**. Un QR de práctica o simulación no autoriza entregar mercancías como pagadas.
- No se proporcionan claves o credenciales en este repositorio. La integración real pey/CoDi queda como trabajo futuro y requeriría configuración autorizada, autenticación y verificación independiente.

## Pruebas locales registradas

| Verificación | Resultado ejecutado en R013 |
|---|---|
| Núcleo lógico Node | 67/67 |
| Matriz QR contra `python-qrcode`, 60 entradas | 60/60 idénticas |
| Navegador Chromium en memoria, móvil + escritorio, efectivo y QR | 50/50 |
| Al pulsar `Generar reporte` en navegador (cada entorno) | 94/94 |
| Decodificador QR independiente (OpenCV) | Código leído en ambos tamaños |
| Servidor HTTP opcional | 5/5 |
| Android físico / TalkBack / envío efectivo por WhatsApp o email | **NO OBSERVADO** |
| Operación bancaria real / integración pey | **NO IMPLEMENTADA** |

Reproducción:

```bash
node tests/test_logic.mjs
python tests/test_qr_matrix.py   # requiere paquete Python qrcode
python tests/test_e2e_r013.py    # requiere playwright, Chromium, pillow, cv2, cairosvg
python tests/test_server.py
python tests/build_offline.py
```

En pruebas E2E se cargó el mismo HTML autónomo en memoria por restricciones administrativas del navegador de pruebas. Esto no es una prueba de reapertura del archivo en Android físico.

## Límites de evidencia

`TEST_PASS != USER_VALIDATION`, `QR_DEMO != PAYMENT_REQUEST`, `PAYMENT_STATE_SIMULATED != BANK_CONFIRMED`, `CART_LOCAL != MULTI_DEVICE_PERSISTENCE`, `HASH != TRUTH`.

## Próximos deltas

- **D013-01**: ensayo con 3–5 comerciantes y accesibilidad/TalkBack en Android real. `NOT_EXECUTED`.
- **D013-02**: analizar integración real pey con modo de pruebas confirmado, permisos y webhooks verificados. `BLOCKED_NO_INTEGRATION`.
- **D013-03**: respaldo/importación de venta o ticket al recargar; definir modelo de privacidad. `OPEN`.
- **D013-04**: refinar formato térmico de ticket e internacionalización de lectura QR. `OPEN`.
- **D013-05**: repositorio dedicado, CI y publicación web estática tras revisión. `OPEN`.

Rondas: R012→R013 fuente; R013 QR y skin móvil; R013 comparación de referencia; R013 pruebas UI; R013 publicación pública en rama de revisión (sin modificar main). 
