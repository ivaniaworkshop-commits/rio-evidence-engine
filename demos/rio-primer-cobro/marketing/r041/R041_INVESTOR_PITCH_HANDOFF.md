# RÍO R041 · Pitch de inversión — Entrega y control de afirmaciones

**Producto base:** RÍO Primer Cobro R015/R016. **Audiencia:** inversionistas/aliados estratégicos, no comerciantes finales. **Medio:** dos videos MP4 completos de 120.000 segundos, horizontal 16:9 y vertical 9:16.

## Historia comercial

Una operación de bajo costo de acceso (caja educativa gratuita) abre la hipótesis de relación con comercios. La estrategia por validar es ofrecer después POS/inventarios/CRM/cotizaciones y, potencialmente, red mayorista y logística. No se presenta la demo como un sistema de pagos ni como un negocio probado.

## Fuentes y estados

- **Implementado y respaldado por código:** caja educativa R015, vista pública R016, cálculo por pieza/peso, registro manual de efectivo, historial/ticket local, QR no pagable, guía por reglas y reportes de pruebas.
- **Propuesto / no integrado como oferta productiva en Primer Cobro:** expansión de POS, CRM, inventario, Marketplace RFQ, logística, suscripciones y comisiones. Existen demos relacionados de Río, pero estos no acreditan integración ni tracción.
- **No verificado:** usuarios activos, CAC, LTV, cohortes, retención, aceptación de pago, cuota comercial, margen o rentabilidad.
- **Escenario ilustrativo, no ingreso observado:** 10,000 comercios supuestos × 5% conversión supuesta × $99 MXN/mes supuestos = $49,500 mensuales brutos antes de costos. Sensibilidad adicional en `R041_SENSIBILIDAD_COMERCIAL.json`.
- **Límite operativo:** GitHub PR #41 en borrador. R038 policy HOLD sigue bloqueado. No merges, pagos reales, ofertas de valores, producción ni inversión comprometida.

## Auditoría ejecutada

- 9 escenas contiguas, 19 cues de subtítulos.
- La primera compilación se rechazó: el audio concatenado duró 118.316 segundos; se corrigió con padding exacto por escena y nuevo master de 120.000.
- Se verificaron audio AAC, vídeo H.264, resolución y ambos contenedores con `ffprobe`.
- Se auditaron láminas de las nueve escenas y se corrigió el solapamiento de subtítulos con la banda inferior opaca.
- No hay verificación humana independiente de la dicción o aceptación comercial; la locución es TTS sintética es-la de uso local, no un presentador profesional grabado.
- Las escenas son gráficos originales conceptuales, no capturas reales de comerciantes, bancos o aplicaciones conectadas.

## Punto de entrada para reuniones

Presentar la demo R016 seguida de este video R041 como **tesis por validar**. Pedir colaboración para pilotos y acordar métricas de avance: adquisición autorizada, comercio activo, uso repetido, conversión, ingresos netos/cuenta, CAC y feedback de uso. Evitar confundir desarrollo técnico con adopción.

## Reproducción

`python3 build_investor_pitch.py --stage all` con FFmpeg/ffprobe, eSpeak, Pillow, NumPy y fuentes Lato instalados. Resultados visuales equivalentes pero bytes del video pueden variar según versiones de codecs/fuentes. Los originales llevan SHA-256 en `reports/R041_AUDITORIA_FINAL.json`.
