# Auditoría de exportación pública

## Alcance

Exportación curada de la aplicación Mercado Abierto/pey: servicio FastAPI, migraciones, frontend estático, tests sintéticos y entrada local desechable. Se crea un repositorio con historial Git nuevo; no se publica el historial de la monorepo privada.

## Exclusiones

- Evidencia histórica, logs, reportes de producción, respaldos, dumps y artefactos de auditoría.
- Guías de configuración privada, detalles de proyectos/despliegues de Vercel y matrices internas de trabajo.
- Entornos virtuales, cachés, bases locales y archivos de credenciales.
- La interfaz `frontdesk/practica.html`, que es una página de práctica antigua y no parte del frontdesk publicado actual.
- Herramientas operativas que pueden desplegar, enviar correos o iniciar cargos externos, y sus pruebas asociadas.
- Referencias de ayuda a repositorios, ramas y pull requests privados; se eliminaron de los metadatos JSON conservando el contenido dirigido al usuario.

## Verificación

El manifiesto `RELEASE_MANIFEST.json` registra la ruta, tamaño y SHA-256 de cada archivo del paquete, salvo el propio manifiesto para evitar una referencia circular. El ZIP y el manifiesto se verifican aparte; el SHA-256 del ZIP se entrega en un archivo lateral. La publicación se hace desde una copia limpia y un commit inicial nuevo. Las pruebas del código emplean usuarios, conexiones y datos sintéticos; no se incluyeron credenciales ni datos vivos.

El fixture `app/tests/fixtures/pey-openapi-2026-10-20.json` contiene la especificación pública CoDi API v3.1.1 de pey, recibida para integrar y verificar el contrato del cliente. Se usa solo como esquema estático en pruebas; las respuestas y credenciales del proveedor no se consultan.

## Límites

La exportación de código no certifica la configuración de producción, la compatibilidad de una base ajena ni la autorización de pey. No contiene una licencia para el código propio.
