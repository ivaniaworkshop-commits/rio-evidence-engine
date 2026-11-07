# RÍO Primer Cobro — R040: guion audiovisual auditado y programado

**Objetivo:** demostración educativa útil, creíble y verificable en 120 segundos. **Audiencia:** pequeños comercios de México. **Estética:** vector original RÍO, no capturas falsas. **Narración:** voz sintética local en español latinoamericano, no una voz mexicana certificada.

## Auditoría y rondas

- **R040.A · Semántica:** contrastado con `app/logic.js`, `app/chat.js`, `app/persistence.js`, `app/index.html`, `README.md` y `frontdesk/README.md` de R015/R016. El material audiovisual es una RECREACIÓN VISUAL basada en funciones del código, NO captura de la UI ni prueba de usuarios reales.
- **R040.B · Cálculo:** 2 panes × $15.00 = $30.00; 500 g × $40.00/kg = $20.00; total = $50.00; efectivo declarado $100.00 − total $50.00 = cambio $50.00. El efectivo es un registro humano, nunca comprobación bancaria.
- **R040.C · Tiempo:** nueve escenas consecutivas, suma exactamente 120 s; la duración sintetizada de cada locución se mide después de generar audio, se ajusta sin alterar el contenido verbal y se guarda en `reports/voice_timing.json`. Subtítulos `.srt` y `.ass` con intervalos definidos.
- **R040.D · Render:** FFmpeg H.264 + AAC, 1280×720, 24 fps, subtítulos integrados, música sintetizada original de volumen bajo. Comprobación con `ffprobe`, imágenes de muestra y recibo de integridad. No usa servicios externos ni créditos de InVideo.
- **R040.E · Gobierno:** no cambia `main`, no afirma pago real, no inicia cobros ni hace públicos secretos. El guion/video no levanta el `r038-policy-hold` ni implica despliegue de producción.

## Escenas y narración final

### 01 · 000–011 s · Una venta más clara

**Locución:** ¿Vendes en una tienda, un puesto o un mercado? Entre cantidades y cambio, cada venta merece claridad. Conoce RÍO Primer Cobro.

**Pantalla:** Para puestos, tiendas y mercados. **Rótulo:** Tu negocio. Tus decisiones..

### 02 · 011–023 s · Aprende sin registro

**Locución:** Una caja educativa y gratuita, en español. Abre la demo desde tu celular, entra a Caja y practica sin crear una cuenta.

**Pantalla:** Caja educativa en español, gratuita. **Rótulo:** Comienza desde tu celular.

### 03 · 023–037 s · Piezas y peso

**Locución:** Agrega dos panes de quince pesos: treinta. Después, quinientos gramos de jitomate a cuarenta pesos por kilo: veinte. Tu carrito suma cincuenta pesos.

**Pantalla:** Carrito con cálculos por producto. **Rótulo:** $30 + $20 = $50 MXN.

### 04 · 037–051 s · Efectivo y cambio

**Locución:** Elige efectivo. Registra manualmente cien pesos recibidos. Para una venta de cincuenta, RÍO muestra cincuenta de cambio. La verificación del dinero depende de ti.

**Pantalla:** Registra la recepción manualmente. **Rótulo:** $100 recibido → $50 de cambio.

### 05 · 051–065 s · QR de práctica

**Locución:** ¿Quieres practicar un recorrido digital? Genera un QR escaneable de demostración. Atención: no es pagable, no envía dinero y nunca confirma un cobro real.

**Pantalla:** Aprende el recorrido digital sin pagar. **Rótulo:** NO PAGABLE · DEMO.

### 06 · 065–079 s · Ticket e historial

**Locución:** Prepara un ticket de práctica; cópialo, imprímelo o descárgalo. Consulta el historial guardado en el navegador. Ese ticket no es factura ni comprobante bancario.

**Pantalla:** Revisa tus ventas de práctica. **Rótulo:** Ticket de demostración · No CFDI.

### 07 · 079–094 s · Tus datos, locales

**Locución:** El archivo descargado funciona sin internet, en un navegador compatible. Tus datos permanecen locales cuando el navegador permite guardarlos. Exporta un respaldo JSON antes de cambiarlos o borrarlos.

**Pantalla:** Archivo sin conexión y respaldo JSON. **Rótulo:** Sin sincronización automática.

### 08 · 094–109 s · Ayuda y reporte

**Locución:** ¿Tienes dudas sobre el peso, el efectivo o internet? La ayuda responde mediante reglas locales. En Reporte puedes ejecutar pruebas internas y descargar un resumen de tu práctica.

**Pantalla:** Reglas locales que acompañan tu práctica. **Rótulo:** Dudas → guía → pruebas internas.

### 09 · 109–120 s · RÍO Primer Cobro

**Locución:** RÍO Primer Cobro. Aprende paso a paso, sin mover dinero. Pruébalo gratis y utiliza medios autorizados cuando cobres de verdad.

**Pantalla:** Aprende antes de cobrar de verdad. **Rótulo:** Pruébalo gratis.

## Afirmaciones controladas

- **C01:** La app descrita es educativa, gratuita, sin login; soporte portada R016 y app R015; acceso público R016 no implica despliegue nuevo.
- **C02:** El cálculo usa unidad de centavos exactos; 2×15=30; 500 gramos×40/1000=20; total 50; valores de práctica.
- **C03:** En efectivo la app registra la declaración de la persona; 100-50=50 de cambio, no prueba dinero real.
- **C04:** QR de prueba escaneable y explícitamente no pagable; sin confirmación bancaria ni conexión a CoDi/Pey.
- **C05:** Ticket con folio de demostración y historial local, ticket no CFDI ni comprobante bancario.
- **C06:** La versión HTML local funciona offline en navegador compatible; persistencia sujeta a localStorage y respaldo JSON no cifrado.
- **C07:** Ayuda usa reglas locales predefinidas (RioChat), no LLM generativo activo. El reporte ejecuta pruebas internas al generarse.
- **C08:** No se promete mejora de ingresos, ahorro medido, comercio real, protección bancaria, certificación de accesibilidad ni seguridad de producción.

## Limitaciones de esta versión

- Las pantallas y el entorno comercial son gráficos ilustrativos construidos a partir de lo que documenta el repositorio, y van etiquetados como `RECREACIÓN VISUAL`; no sustituyen capturas reales de navegador.
- La voz offline `es-la` es comprensible pero sintética; para una versión publicitaria profesional puede sustituirse por una grabación humana o TTS profesional con licencia.
- No se presentan ingresos obtenidos, usuarios reales, resultados de conversión ni mejoras medidas.
- Los tickets no son CFDI, los QR no aceptan pagos, el JSON de respaldo no es cifrado y no hay sincronización en la nube.
- Este entregable es una producción local, independiente de la cuenta InVideo (0 créditos observados).
