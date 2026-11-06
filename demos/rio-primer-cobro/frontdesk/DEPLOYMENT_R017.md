# R017 - Public Front Desk: despliegue verificable

## Fuente y destino

- Publicacion: https://rio-primer-cobro-frontdesk.vercel.app/
- Aplicacion: https://rio-primer-cobro-frontdesk.vercel.app/app.html
- Repositorio: https://github.com/ivaniaworkshop-commits/rio-evidence-engine
- Rama de publicacion: `deploy/primer-cobro` (independiente de `main`)
- Codigo de la web: `demos/rio-primer-cobro/frontdesk/index.html` y `app.html`
- Vercel proyecto identificado: `prj_J7YrJusN08qUXrZNPDBmspVRKW6d`; equipo `team_cAq0fHixSn0Hck4ogKCifUzi`.

## Como funciona

Cada push autorizado a `deploy/primer-cobro`, si cambia la portada, aplicacion o sus pruebas, dispara un workflow:
1. Verifica `MANIFEST.json` para todos los archivos fuente.
2. Ejecuta regresiones del motor y del asistente local.
3. Genera una entrega estatica y un recibo SHA-256 usando `verify_release.py`.
4. Solamente cuando `RIO_PUBLIC_AUTO_DEPLOY=enabled`, despliega al proyecto Vercel anterior.
5. Recupera las dos URLs publicas **sin cabeceras de autenticacion** y compara bytes exactos. Si difieren, FAIL, no falso PASS.

**La existencia del workflow no significa que Vercel ya reciba pushes.** El puente necesita una configuracion inicial.

## Configuracion unica pendiente (no pegar secretos al chat)

1. Crea un token Vercel restringido de despliegue para el proyecto/equipo autorizado.
2. En GitHub: Settings > Environments > `rio-primer-cobro-production`. Configura primero la restriccion de rama `deploy/primer-cobro` y los revisores requeridos; despues crea ahi el **environment secret** `VERCEL_TOKEN`. No uses un secreto general del repositorio.
3. En GitHub: Settings > Secrets and variables > Actions > Variables, agrega `VERCEL_CLI_VERSION` con una version exacta comprobada del CLI y `RIO_PUBLIC_AUTO_DEPLOY` con valor `enabled`.
4. Protege `deploy/primer-cobro` contra pushes directos no revisados (Settings > Branches o Rulesets) y exige revision antes de actualizarla. Sin esta proteccion, NO habilites `RIO_PUBLIC_AUTO_DEPLOY`. El token se entrega solo al paso `vercel deploy`, no a npm ni a los tests.
5. Lanza una ejecucion de `RIO Primer Cobro - verified public deployment` desde la rama de publicacion, o realiza un nuevo push revisado. Exige `verify=success`, `deploy=success` y `PUBLIC_READBACK_PASS`.

Hasta instalar ese secreto y habilitar la variable, `deploy` queda **SKIPPED_BY_POLICY** mientras `verify` puede ejecutarse.

## Limites y evidencias

- REAL_PAYMENT = NO. Los QR son educativos y no pagables. Los tickets no son CFDI.
- Los datos se guardan en el navegador de cada visitante; sin backend de clientes.
- La lectura HTTP en CI cuando este activo **no es** una prueba de interfaz completa en Android.
- Android fisico, camara y TalkBack permanecen `NOT_OBSERVED` hasta prueba real.
- No es GitHub Pages. El repositorio es publico y GitHub Actions alimenta Vercel tras la configuracion.

## Protocolo de campo R017

Abre la URL publica en modo incognito o dispositivo no autenticado y anota `HTTP_VISIBLE`, `LOGIN_REQUESTED`, `UNKNOWN`. En Android, registra modelo/navegador sin identificadores personales, acceso, agregar producto, QR, ticket, cierre/reapertura, copia/exportacion. Marca cada paso `PASS_USER_REPORTED`, `FAIL_USER_REPORTED` o `NOT_TESTED`. No publiques datos de ventas reales ni conversaciones personales en el repositorio.
