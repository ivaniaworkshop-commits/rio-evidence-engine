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


## R018 — observación externa y promoción segura

**Verificación de acceso público sin autenticación:** `check_public_site.py` prueba / y /app.html mediante HTTP estándar desde GitHub Actions. No añade cookies ni Authorization. Se ejecutan primero 8 regresiones locales y luego la prueba HTTP externa. `HTTP_PUBLIC_ANONYMOUS=PASS` no implica `BROWSER_UI=PASS` ni `ANDROID_FISICO=PASS`.

**Cuando el despliegue autorizado esté activo**, la secuencia cambia a:
`SOURCE_VERIFY → STAGE_PROD_WITHOUT_ALIAS → ANONYMOUS_EXACT_BYTE_READBACK → PROMOTE → PUBLIC_EXACT_BYTE_READBACK`.
La URL pública **no se modifica si falla el readback del candidato**. Una falla posterior a promover sigue siendo incidente abierto, no PASS. Las credenciales se entregan únicamente a las acciones Vercel de staging y promoción; pruebas de acceso HTTP no las reciben.

La activación sigue pendiente de habilitar `RIO_PUBLIC_AUTO_DEPLOY`, definir `VERCEL_CLI_VERSION` exacta, proteger la rama y configurar `VERCEL_TOKEN` como secreto del entorno `rio-primer-cobro-production`. No hay dato que acredite Android físico ni pagos reales.


## R020 — autoridad de publicación y activación real

- La rama \`deploy/primer-cobro\` se considera una **ruta de publicación restringida**. El workflow comprueba en tiempo de ejecución reglas activas de GitHub: revisión obligatoria con al menos una aprobación, prohibición de eliminar ramas y de reescribir historial, y ausencia de actores con bypass en el ruleset aplicable. Si no puede acreditarlo, el despliegue **falla cerrado**.
- Las **9 pruebas unitarias** de \`release_authority_r020.py\` comprueban políticas válidas e inválidas. Estas pruebas no sustituyen una observación de protecciones realmente activas en GitHub.
- Para activar: visita https://github.com/ivaniaworkshop-commits/rio-evidence-engine/settings/rules y crea un Ruleset \`RÍO Primer Cobro — release\`, enforcement **Active**, solo rama \`deploy/primer-cobro\`. Configura \`Require a pull request before merging\` y al menos una aprobación, \`Block force pushes\` y \`Restrict deletions\`. No permitas bypass. Si tu plan/repositorio no admite todas estas opciones, **no declares ACTIVE**.
- En https://github.com/ivaniaworkshop-commits/rio-evidence-engine/settings/environments crea el entorno \`rio-primer-cobro-production\`, limita deployments a \`deploy/primer-cobro\`, exige revisión de despliegue si está disponible y añade **solo en ese entorno** el secreto \`VERCEL_TOKEN\`. Nunca lo pegues en chats, README o archivos públicos.
- En Actions Variables del repositorio define \`VERCEL_CLI_VERSION\` con una versión exacta revisada y \`RIO_PUBLIC_AUTO_DEPLOY=enabled\`. El token solo se expone a los dos pasos de staging/promoción de Vercel.
- En cada cambio revisado del branch, CI verifica manifest y regresiones, accesibilidad HTTP anónima, Chrome real y flujo completo de QR y efectivo. **Solo entonces** la rama podrá preparar un candidato, verificar bytes, promoverlo y contrastar la URL pública.
- Estado observado de configuración en esta ronda: \`GitHub GET /rulesets = []\`; no hay reglasets visibles. Los conectores no exponen edición de reglas ni secretos. Resultado: \`AUTO_DEPLOY=BLOCKED_PENDING_EXTERNAL_CONFIGURATION\`. Este documento no afirma haber realizado esas acciones. La aplicación pública R016 sigue disponible.

## Control de exactitud de Vercel

El despliegue de prueba R020 encontró una inyección automática de comentarios de Vercel de 163 bytes por HTML. Se corrigió desactivando el feedback de vista previa y desplegando un candidato nuevo, que devolvió los HTML **idénticos** a GitHub. La guarda de comparación binaria debe **permanecer estricta**, porque si se reactiva la inyección volverá a bloquear la promoción. La comprobación previa se hizo mediante conector Vercel, no con Android físico.
