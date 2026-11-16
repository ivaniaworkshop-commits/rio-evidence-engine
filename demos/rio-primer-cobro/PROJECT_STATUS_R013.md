# RÍO Primer Cobro R013 — estado de entrega

## Rondas ejecutadas

- R013-01 RECUPERADO: fuente R012 revisada; el supuesto QR era sólo texto, no un símbolo codificado.
- R013-02 IMPLEMENTADO: método visible y canónico `qr`, generador QR local versión 5-L, folio e importe exacto; el escaneo entrega texto `NO-PAGABLE`.
- R013-03 IMPLEMENTADO: interfaz «skin de celular» aplicada a todas las secciones (caja, carrito, ayuda, reporte, ticket) sin servicios externos.
- R013-04 PROBADO: se detectó y reparó un error de padding de QR que afectaba longitudes impares; la matriz final coincide con `python-qrcode` en 60/60 entradas y OpenCV decodifica la venta de práctica.
- R013-05 PROBADO: 67 pruebas de lógica en Node, 48 regresiones de carrito, 3 pruebas de almacenamiento simulado, 50 controles browser e2e, 94 pruebas internas al pulsar Generar reporte, 5 pruebas de HTTP local.
- R013-06 PERSISTIDO EN GITHUB: 24 archivos de código, aplicación offline, documentación, pruebas y recibos colocados en la rama pública `feat/primer-cobro-r013-qr-mobile-20261105` dentro de `ivaniaworkshop-commits/rio-evidence-engine`; PR #25 en borrador para revisión. `main` no fue modificado por esta operación.

## Repositorio

- PR pública: https://github.com/ivaniaworkshop-commits/rio-evidence-engine/pull/25
- Carpeta fuente: https://github.com/ivaniaworkshop-commits/rio-evidence-engine/tree/feat/primer-cobro-r013-qr-mobile-20261105/demos/rio-primer-cobro
- HTML único: https://github.com/ivaniaworkshop-commits/rio-evidence-engine/blob/feat/primer-cobro-r013-qr-mobile-20261105/demos/rio-primer-cobro/RIO_PRIMER_COBRO_R013_OFFLINE.html

## Fronteras

- `REAL_PAYMENT=NO`.
- `QR_PRACTICE=YES`, no pagable, sin credenciales, sin datos de clientes en código QR.
- `EMAIL_WHATSAPP=PREPARE_ONLY`, envío real no observado.
- `ANDROID_PHYSICAL=NOT_OBSERVED`.
- `LLM_BACKEND=OPTIONAL_NOT_CONFIGURED`; chat local por reglas.
- `INDEPENDENT_USER_IMPACT=NOT_MEASURED`.
- No creó un nuevo repositorio: el conector disponible no provee esa operación, por lo que R013 quedó publicada en una rama de un repositorio público existente.

## Nuevos deltas por valor esperado

1. **D013-01**: validar la experiencia en Android y con comerciantes reales; registrar navegación, comprensión de estados, escaneabilidad, TalkBack y ticket. Estado OPEN.
2. **D013-02**: migrar a repositorio dedicado cuando haya herramienta autorizada para crearlo y configurar CI, una vista previa web segura y una ruta de versionado. Estado OPEN.
3. **D013-03**: persistencia recuperable/importación de ventas, con privacidad y consentimiento; el carrito persiste localmente pero los tickets no. Estado OPEN.
4. **D013-04**: integrar IA generativa limitada a tutoría, con servidor seguro, permisos y evaluación de comprensión; IA no confirma pagos. Estado OPEN.
5. **D013-05**: investigar el sandbox contractual de pey/CoDi y después diseñar el adaptador de cobros reales con autenticación de webhooks y reconciliación; sin pagos reales en este prototipo. Estado BLOCKED_EXTERNAL.
6. **D013-06**: verificación de entrega externa real de tickets por apps de correo y WhatsApp, formatos de impresión térmica y accesibilidad. Estado OPEN.

Esta nota es un registro de la ronda. No acredita validación externa de impacto.
