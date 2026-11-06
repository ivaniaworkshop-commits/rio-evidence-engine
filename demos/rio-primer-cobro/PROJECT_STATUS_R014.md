# RÍO Primer Cobro — R014 · continuidad de venta y ticket

**Tipo:** implementación local sobre R013; QR de práctica **NO PAGABLE**; efectivo con declaración manual.

## Rondas y evidencia
- R014.1: auditó falla de continuidad: carrito R013 persistía pero venta y ticket se perdían al recargar.
- R014.2: implementó `app/persistence.js` y UI de historial/importación/exportación con controles de integridad semántica.
- R014.3: pruebas locales realizadas: Node 67/67 núcleo; persistencia 20/20; Chromium 61/61 en memoria con localStorage simulado; QR 60/60 matrices frente a python-qrcode; HTTP 5/5; reporte interno generado por clic 106/106.
- R014.4: publicación y readback GitHub, por confirmar con datos remotos. No se modifica `main`.

## Gestión de datos
- Clave local `RIO_PRIMER_COBRO_R014_SESSION_V1`. Una escritura por snapshot; límite 50 ventas archivadas.
- Recuperación de sesión activa y del historial; normalización en centavos con cálculo determinista y replay de eventos de demostración.
- Exporta/Importa JSON local con acciones explícitas. No hay sincronización entre dispositivos ni envío automático.
- Bloqueo de sobrescritura si el snapshot almacenado está corrupto; opción de descargar los bytes originales y reiniciar con confirmación.
- **No existe prueba bancaria verificable, firma externa o cifrado del respaldo**; el contenido puede editarse localmente. El usuario debe gestionar su privacidad.

## Limitaciones
- Android físico, persistencia de navegador después de cerrar completamente la app, cámara, TalkBack, usuarios reales: `NOT_OBSERVED`.
- La simulación de continuidad en Chromium usa un almacenamiento sustituto dentro del mismo contexto en memoria. No se presenta como observación de un dispositivo físico.
- Integración real de pey/CoDi: `NO`, pago digital: `NO`, QR real: `NO`, IA generativa activa: `NO`.
- El reporte interno no relanza pruebas Node, Chromium externo ni pruebas físicas.
- Los criterios de impacto y adopción reales continúan `UNKNOWN`.

## Siguiente delta
**R015**: instrumentar medición de tareas en Android físico (guía reproducible y reporte de usuario), validar reanudación entre cierres reales y accesibilidad; después recuperar evidencia con usuarios de mercados y priorizar mejoras. Solo abrir integración financiera real al contar con entorno autorizado y validación independiente.
