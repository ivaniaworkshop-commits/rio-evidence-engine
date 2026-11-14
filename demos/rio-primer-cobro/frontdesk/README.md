# Pey / RÍO · entrada web actual

[Abrir la aplicación](https://rio-primer-cobro-frontdesk.vercel.app/app.html) · [Iniciar sesión](https://rio-pey-codi-gateway.vercel.app/login) · [Estado y verificaciones](ESTADO_20261113.md) · [Accesibilidad R003: implementación y estado](A11Y_R003_20261114.md)

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

## Accesibilidad R003 (14 de noviembre)

El trabajo de accesibilidad está registrado en [RÍO privado #306](https://github.com/ivaniaworkshop-commits/rio/pull/306) y documentado en el [checkpoint R003](A11Y_R003_20261114.md). Esta rama pública **no incluye el código interno** y el sitio productivo todavía no incorpora esas modificaciones. Las comprobaciones estáticas no sustituyen las pruebas de navegador, lector de pantalla ni de despliegue.

## Endurecimiento de cabeceras (14 de noviembre de 2026)

`vercel.json` añade para `/(.*)`: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` sin cámara/micrófono/geolocalización/pagos, HSTS (`max-age=63072000; includeSubDomains; preload`) y CSP restringida a mismo origen con `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'` y `form-action 'self'`.

Estas cabeceras corresponden **a la entrada pública de frontdesk**. La aplicación autenticada responde desde otro origen (gateway privado), cuya rama del [PR privado #306](https://github.com/ivaniaworkshop-commits/rio/pull/306) incluye sus propias cabeceras y controles de sesión. Las cabeceras no sustituyen autenticación ni autorización. GitHub confirma la modificación del archivo; **falta observar la respuesta HTTP del despliegue**. La palabra `preload` en HSTS no acredita inscripción en listas de precarga y debe evaluarse junto con los subdominios reales del dominio que se publique.
