# RÍO Primer Cobro — Video educativo R040 (120 segundos)

## Entregables

- `RIO_PRIMER_COBRO_VIDEO_120S_R040.mp4` — máster horizontal 16:9, 1280×720, 24 fps.
- `RIO_PRIMER_COBRO_VERTICAL_120S_R040.mp4` — composición móvil independiente 9:16, 720×1280, 24 fps.
- `RIO_PRIMER_COBRO_GUION_FINAL_AUDITADO_R040.md` — narración y auditoría de semántica.
- `RIO_PRIMER_COBRO_SUBTITULOS_R040.srt` — 26 segmentos, español.
- `RIO_PRIMER_COBRO_SUBTITULOS_R040.ass` — subtítulos integrados en el máster.
- `build_video.py`, `build_vertical.py` — código reproducible en un entorno Linux que disponga de `ffmpeg`, `espeak`, Pillow, numpy, qrcode y Lato.
- `reports/RIO_PRIMER_COBRO_VIDEO_R040_AUDIT.json`, `reports/R040_VERTICAL_QA.json` y `reports/voice_timing.json` — recibos, no certificaciones externas.
- `R040_VIDEO_QA_CONTACT_SHEET.png` — inspección visual de nueve fotogramas.

## Método en rondas

R040.A recuperó el código de R015/R016 para distinguir funciones implementadas de planes. R040.B reconcilió afirmaciones, cálculo comercial y protección de pagos. R040.C redujo el guion de 250 a 214 palabras, divididas en nueve escenas que suman exactamente 120 s. R040.D generó audio TTS sintético, música original, gráficos vectoriales, escenas animadas y subtítulos, y comprobó ffprobe. R040.E inspeccionó fotogramas de las nueve escenas y corregió la marca visual QR y el icono incompatible. R040.F produjo formato vertical sin recorte destructivo y corrigió un solapamiento de subtítulos, verificando de nuevo el MP4.

## Aclaraciones obligatorias

Las imágenes de teléfono son **recreaciones originales** basadas en etiquetas y funciones del código, no grabaciones de la aplicación real. Todas las operaciones de venta son ejemplos **ficticios**. El QR es escaneable, pero es demostrativo y **no pagable**, no significa cobro aprobado. El efectivo es un dato declarado manualmente. Los tickets no son CFDI. Datos y respaldos JSON son locales, no cifrados ni sincronizados por la demo.

La voz es **eSpeak offline, es-la**, no una voz humana ni una voz mexicana certificada. La música de fondo es un patrón matemático original sintetizado localmente y no copia de canciones existentes. Las conversiones entre render local y verdad física están explícitamente separadas: **REAL ≠ PIXEL**.

## Reproducibilidad

Desde este directorio:

```bash
python3 build_video.py --stage all
python3 build_vertical.py
```

El render utiliza herramientas de entorno que pueden variar, por lo que la identidad byte a byte del MP4 no se garantiza en otra versión de FFmpeg, sistema de fuentes o librerías. Lo que se conserva de manera reproducible es el guion, la línea temporal, la lógica de producción y las condiciones de verificación. Verificar duración, SHA-256 local, muestras de fotogramas y rótulos antes de compartir.

**Estado:** video producido localmente, sin consumir créditos de InVideo. NO publicado en un medio social, NO desplegado como nueva aplicación, NO habilitó pagos, NO cambió la protección de la rama GitHub.
