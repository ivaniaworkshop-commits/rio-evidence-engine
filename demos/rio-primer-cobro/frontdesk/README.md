# Pey / RÍO · entrada web actual

[Abrir la aplicación](https://rio-primer-cobro-frontdesk.vercel.app/app.html) · [Iniciar sesión](https://rio-pey-codi-gateway.vercel.app/login) · [Estado y verificaciones](ESTADO_20261113.md)

Esta carpeta contiene la entrada pública de la aplicación. `index.html` y `app.html` llevan al login del gateway. `vercel.json` dirige las rutas al mismo acceso. El backend se mantiene en un repositorio privado y no está incluido en esta carpeta.

## Funciones disponibles en el gateway

- Acceso obligatorio antes de servir la aplicación y sus módulos; navegación única entre Caja, Historial, Conectar pey, Mi negocio y Otros módulos.
- Registro con verificación de correo y recuperación por SMTP.
- Conexión de pey persistente y cifrada por comercio, con estado actualizado entre pestañas. La ficha muestra identificadores y fechas, permite habilitar CoDi y retirar la conexión sin borrar el historial. Las claves no se muestran.
- Cobro mediante PEY/CoDi con credenciales del comercio. El aviso `codi.qr.payment_received` se valida y contrasta con la API de PEY antes de confirmar el pago en la aplicación. La integración es multibanco mediante PEY.
- Comprobante «Pago confirmado por pey» con QR verificable. Puede enviarse al pagador y al titular con correo verificado. La casilla de desactivación cancela ambos correos para ese cobro y conserva el comprobante dentro de la aplicación.

La cuenta y las credenciales del comercio deben estar guardadas y habilitadas para emitir cobros. Que las banderas generales estén en LIVE no demuestra un pago real ni la acreditación bancaria. Los comprobantes no son CFDI.

## Archivo histórico y publicación

`practica.html` conserva exactamente la antigua aplicación educativa R015, antes publicada como `app.html`. Es un archivo histórico con QR no pagables y almacenamiento local. Está en Git, pero **no se incluye en los archivos publicados en Vercel**. El despliegue de la entrada usa exclusivamente `index.html`, `app.html` y `vercel.json`. Las rutas del sitio llevan al login. No se migraron ni borraron registros de navegadores anteriores.

La publicación en Vercel es explícita; actualizar esta rama no crea por sí solo otro despliegue. El PR permanece en borrador hasta su revisión e integración.
