# RÍO Primer Cobro — R014

**Producto:** prototipo local de caja para efectivo manual y **QR de práctica no pagable**.

R014 añade continuidad: venta activa, ticket, historial limitado a 50 ventas, importación y exportación JSON con validación, y controles ante almacenamiento corrupto o bloqueado. El archivo `RIO_PRIMER_COBRO_R014_OFFLINE.html` funciona sin conexión.

## Uso
1. Abre el HTML en un navegador y agrega un producto.
2. Selecciona **Efectivo** o **QR de práctica** y crea la venta.
3. Para QR: pulsa **Generar QR**, que es únicamente texto educativo sin posibilidad de pago. Para efectivo: registra manualmente el monto recibido.
4. Genera el ticket; puedes preparar un correo o mensaje de WhatsApp que **tú** decides enviar.
5. Pulsa **Nueva venta**: la anterior pasa al historial. Si cierras la aplicación, vuelve a abrirla en el mismo origen del navegador; si necesitas cambiar de dispositivo, exporta y después importa el respaldo JSON.

## Seguridad y alcance
- **No admite pagos reales**, no incluye credenciales, ni da comprobantes bancarios/CFDI.
- El historial se almacena sólo en el navegador si su política lo permite. El navegador o usuario pueden borrarlo.
- El respaldo puede contener nombres y detalles de ventas; guárdalo con cuidado. No está cifrado ni tiene firma verificable independiente.
- La importación valida montos, eventos y estados y rechaza una declaración de pago real. Aun así, el fichero local no prueba que un pago haya ocurrido.
- Si falla la lectura, no se sobrescribe automáticamente la clave dañada. Se puede descargar una copia cruda antes de reiniciar.
- La generación de reporte ejecuta nuevamente las pruebas internas, no las pruebas externas de dispositivos.
- Android físico, TalkBack y pruebas con comerciantes: **NOT_OBSERVED**.

## Pruebas
`node --test tests/test_persistence_r014.mjs` y `python tests/test_e2e_r014.py` (requiere Chromium/Playwright).

## Publicación
El desarrollo se realiza sobre una rama de revisión de un repositorio público; `main` queda protegido de escrituras automáticas.
