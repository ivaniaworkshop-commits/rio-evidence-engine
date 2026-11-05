# RÍO Primer Cobro — registro por rondas

| Ronda | Delta | Ejecución | Evidencia | Estado |
|---|---|---|---|---|
| R013-01 | Recuperar R012 y auditar el QR no existente | Revisado `app.js` | Texto antiguo sólo declaraba QR, sin codificarlo | OBSERVADO |
| R013-02 | Renombrar venta de práctica `QR` y generar QR no pagable por venta | Código y UI R013 | Payload con folio y centavos, SVG local | IMPLEMENTADO |
| R013-03 | Skin de teléfono para caja, carrito, ayuda, reportes y ticket | CSS y HTML R013 | Vistas Chromium móvil/escritorio | PROBADO_LOCAL |
| R013-04 | Auditoría de QR ante referencia independiente | Se corrigió el relleno de codewords alternados | 60/60 matrices idénticas; OpenCV decodificó | PROBADO_LOCAL |
| R013-05 | Test completo del recorrido y botón de reporte | Node, Chromium, servidor | 67/67 núcleo; 50/50 UI; 94/94 interno; 5/5 HTTP | PROBADO_LOCAL |
| R013-06 | Publicación GitHub pública | Publicar en rama sin tocar main | Pendiente de readback en GitHub | PENDIENTE_AL_CORTE |

No hay credenciales bancarias ni pagos reales. La aplicación es un **producto educativo de práctica**, no una caja bancaria.
