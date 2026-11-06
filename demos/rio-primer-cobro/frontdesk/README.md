# 🌐 RÍO Primer Cobro — Front Desk R016

**[Abrir portada pública](https://rio-primer-cobro-frontdesk.vercel.app/)** · **[Abrir caja de práctica](https://rio-primer-cobro-frontdesk.vercel.app/app.html)** · [Código del proyecto](https://github.com/ivaniaworkshop-commits/rio-evidence-engine)

La carpeta contiene exclusivamente los dos HTML que componen la versión web: `index.html` (portada pública) y `app.html` (demo R015 autónoma).

## Alcance

- Interfaz pública gratuita y adaptable a móvil; no requiere cuenta de GitHub.
- Carrito, registro manual de efectivo, QR **NO PAGABLE**, tickets e historial local.
- Ventas de práctica almacenadas **solo en el navegador del visitante** mediante almacenamiento local.
- No hay base de datos remota de usuarios, pagos reales, tokens privados ni credenciales en los HTML.
- El código publicado en esta rama puede diferir del contenido de `main` hasta que se revise e integre.
- La URL de Vercel se actualiza mediante publicación explícita desde los archivos de esta carpeta; la conexión Git automática no está configurada.

## Verificación R016

Los endpoints `/` y `/app.html` respondieron HTTP 200 en la comprobación del alojamiento. El proyecto de Vercel tiene SSO y contraseña desactivados. La validación real de navegador físico, cámara y TalkBack sigue pendiente.

**NO ES COdi, QR PAGABLE NI COMPROBANTE DE PAGO.** Los tickets no son CFDI.

## R017 — despliegue verificable

El procedimiento está en [DEPLOYMENT_R017.md](./DEPLOYMENT_R017.md). El código de publicación se conserva en la rama `deploy/primer-cobro`; la comprobación automatizada puede ejecutarse sin credenciales, pero el despliegue a Vercel necesita la configuración única descrita. No se actualiza `main` ni se activan pagos reales.
