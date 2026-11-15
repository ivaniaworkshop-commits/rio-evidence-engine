> **Aplicación web actual (2026-11-13):** [Abrir Pey / RÍO](https://rio-primer-cobro-frontdesk.vercel.app/app.html) · [Código de la entrada pública](./frontdesk/README.md) · [Estado y verificaciones](./frontdesk/ESTADO_20261113.md).
>
> La entrada actual lleva al login del gateway con PEY/CoDi. Las instrucciones siguientes corresponden al archivo educativo R015 histórico, no al funcionamiento del gateway actual. La publicación de Vercel es independiente de la fusión de este PR.

# 🌊 RÍO Primer Cobro — R015

Aplicación educativa **offline**, de interfaz móvil. Permite carrito por pieza/peso, cobro de efectivo **declarado manualmente**, QR **NO PAGABLE**, tickets, compartir mediante correo/WhatsApp a elección del usuario, historial local y respaldo JSON. No conecta a bancos ni a pey/CoDi.

## Nuevo: pestaña «Prueba móvil»

Esta versión incorpora un protocolo de campo para comprobar continuidad de una venta en Android y registrar problemas de QR, accesibilidad y recuperación **sin inventar resultados físicos**.

1. Descarga `RIO_PRIMER_COBRO_R015_OFFLINE.html`, ábrelo **en Chrome o Edge**, no en la vista previa del chat. Recuerda dónde lo guardaste; al cambiar ruta o aplicación puedes cambiar el origen y perder acceso a `localStorage`.
2. En **Caja**, agrega un producto, crea una venta (efectivo o QR) y, si elegiste QR, pulsa **Generar QR de práctica**.
3. En **Prueba móvil**, pulsa **Iniciar punto de control**. Confirma que aparece un folio e importe.
4. Cierra el documento/pestaña, vuelve a abrir **el mismo archivo en la misma aplicación** y entra a **Prueba móvil**. Pulsa **Verificar recuperación**. `PASS_NEW_DOCUMENT` significa que coinciden folio, importe, método y estado tras una nueva carga; **no demuestra por sí mismo que Android haya cerrado el proceso**.
5. Para verificar QR, usa otra cámara o lector, copia el texto leído al campo «Contenido que devolvió el lector QR» y pulsa **Comparar con la venta**. El texto esperado comienza `RIO-QR-DEMO|NO-PAGABLE|...`. No es CoDi.
6. Con TalkBack habilitado, intenta navegar por los botones, agregar un producto y recuperar un ticket. Selecciona **Completada / Falló / No disponible / Sin probar** según lo ocurrido; no marques como completado lo que no hiciste.
7. Prueba exportar el respaldo JSON de ventas e importarlo en otro dispositivo si está disponible. Registra el resultado.
8. Pulsa **Ejecutar pruebas y generar reporte R015**. La descarga contiene pruebas internas ejecutadas *en ese momento* y resultados de campo `USER_REPORTED_ONLY` (no enviados automáticamente).

**El reporte de campo no contiene el texto escaneado**, ni texto del chat, ni una firma bancaria, ni una certificación independiente del equipo. Sí incluye folio e importe de práctica; trata el reporte como información privada hasta revisarlo.

## Pruebas reproducibles en ordenador

```bash
node --test tests/test_field_r015.mjs tests/test_logic.mjs tests/test_persistence_r014.mjs
python tests/test_e2e_r015.py
python tests/test_qr_matrix.py
python tests/test_server.py
python tests/build_offline.py
```

El E2E de Chromium usa un **almacenamiento simulado dentro de la misma página** para reproducir nuevas cargas del HTML. No acredita reinicio de un teléfono. Las cifras y alcances exactos se registran en `reports/R015_TEST_STATUS.json`.

## Seguridad, privacidad y límites

- `REAL_PAYMENT=NO`, `QR_PAYABLE=NO`, `PEY_CODI_CONNECTED=NO`, `LLM_ACTIVE_BY_DEFAULT=NO`.
- El pago en efectivo se registra por declaración manual, no por observación física.
- Ticket y historial no son CFDI, ni acuse de banco, ni autorización de entrega.
- `localStorage` puede borrarse o estar bloqueado; exporta respaldos para conservar información. No hay sincronización remota ni cifrado del respaldo.
- Una pantalla etiquetada y teclas compatibles no prueban conformidad completa WCAG; falta prueba TalkBack real.
- Android físico, cámara externa y evaluación con comerciantes siguen `NOT_INDEPENDENTLY_VERIFIED` hasta recuperar evidencia fuera del simulador.
- No se modificó el repositorio canónico de RÍO ni se activaron operadores o mecanismos adversariales globales.
