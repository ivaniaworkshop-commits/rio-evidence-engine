# RÍO Primer Cobro — R020 · Estado de despliegue automático

**Objetivo:** publicación automática por pushes revisados a `deploy/primer-cobro`, sin cambiar `main`, con verificación de contenido en Vercel.

## Estado epistemológico

| Parte | Estado | Evidencia |
|---|---|---|
| Sitio público actual | READY / versión R016 | Vercel project `prj_J7YrJusN08qUXrZNPDBmspVRKW6d`; rutas HTTP 200 previas |
| Archivo de workflow | PROGRAMMED | `.github/workflows/rio-primer-cobro-deploy.yml` |
| Pruebas navegador/caja | OBSERVED PASS en R019 | GitHub Actions run `42187976488`: 33/33 |
| Inventario y H00 | OBSERVED PASS en R019 | GitHub Actions run `42187984428` |
| Rama de release | EXISTE | `deploy/primer-cobro` |
| Rulesets GitHub | NINGUNO visible | GET `/repos/ivaniaworkshop-commits/rio-evidence-engine/rulesets` devolvió `[]` en R020 |
| Protección clásica de rama | UNKNOWN | La consulta de GitHub conectada no acredita sus reglas efectivas |
| Variables CI / secreto entorno | UNKNOWN | El conector no ofrece lectura/escritura de secretos del repositorio |
| Git vinculado a Vercel | NO OBSERVADO | `get_git_deployment_context` no mostró proyectos Git vinculados |
| Activación automática de producción | BLOCKED_PENDING_CONFIGURATION | El job de despliegue anterior fue `SKIPPED` |
| Dispositivo Android físico | NOT_OBSERVED | Sin recibo físico |
| QR bancario real | NO IMPLEMENTADO | Modo educativo no pagable |

## Guarda nueva R020

Se añadió `release_authority_r020.py` y sus regresiones. La publicación queda condicionada a un ruleset **Active** para la rama de publicación, revisión PR con una aprobación, prohibición de borrado y force-push, y sin bypass. No es suficiente declarar que una rama está protegida; el workflow comprueba reglas de GitHub al ejecutar.

Cadena programada:
`SOURCE + MANIFEST → NODE → HTTP ANÓNIMO → CHROME E2E → RULESET ACTIVE → STAGING SIN ALIAS → READBACK EXACTO → PROMOTION → READBACK PÚBLICO`.

**Sin secreto y reglas verificadas, ninguna nueva publicación se reclama ni se envía.** La versión R016 continúa sirviendo desde su URL actual.

## Configuración externa pendiente

1. Crear ruleset activo de GitHub para `deploy/primer-cobro` con políticas indicadas.
2. Crear/proteger entorno de GitHub `rio-primer-cobro-production`; configurar `VERCEL_TOKEN` allí.
3. Fijar variables `VERCEL_CLI_VERSION` exacta y `RIO_PUBLIC_AUTO_DEPLOY=enabled`.
4. Ejecutar desde un push autorizado; exigir evidencia real de `verify`, `browser-public`, `deploy` y readback byte a byte.

Toda acción sobre `main` y el canon de RÍO permanece fuera de alcance.

## Readiness automática en cada push

El workflow R020 incorpora el job `release-authority` y clasifica la política real del repositorio desde GitHub. Sus salidas son `authorized=true/false`, y su resumen distingue `BLOCKED_NO_ACTIVE_RULESETS`, `BLOCKED_POLICY_CHECK`, `UNKNOWN_API_UNAVAILABLE` o `VERIFIED_RULESET_GUARDS`.

`deploy` solo se habilita cuando `verify`, `browser-public` y `release-authority` terminaron, se obtuvo `authorized=true` y `RIO_PUBLIC_AUTO_DEPLOY=enabled`. Un run global `SUCCESS` con `deploy=SKIPPED` **no acredita publicación**. El token continúa siendo necesario únicamente en el entorno protegido del paso autorizado.
