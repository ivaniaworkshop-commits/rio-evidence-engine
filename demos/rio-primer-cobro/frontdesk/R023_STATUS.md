# RÍO Primer Cobro — R023 · Conciliación de incidentes antes y después de promoción

## Rebase observado (2026-11-06)
- PR #30 continúa `DRAFT`, rama `deploy/primer-cobro`; `main` no modificado.
- Rulesets de GitHub visibles: `[]`. Promoción automática `BLOCKED`, no `ACTIVE`.
- Alias de producción: `rio-primer-cobro-frontdesk.vercel.app` → `dpl_3j8jWcQ84xkEKXYk5Fym4odB9RFU` (R016).
- Canon `ivaniaworkshop-commits/rio`: `V115`, `OFF_FAIL_CLOSED`. No promover ni modificar ese estado.

## Defecto R022 identificado y corregido
Si fallaba un paso posterior al staging pero anterior a crear `r022-fence.json`, el anterior `incident` intentaba abrir un recibo inexistente, fallaba y sólo imprimía un estado genérico. R023 reemplaza esa ruta por una conciliación que admite recibos ausentes, corruptos, inconsistentes y de otro commit, distinguiendo cada estado sin convertirlo en PASS.

## Nueva política implementada (PROGRAMMED)
- `incident_reconcile_r023.py` observa alias Vercel y clasifica un incidente con el resultado del paso de promoción: `success|failure|skipped|unknown`.
- El workflow ejecuta el paso de incidentes ante **cualquier fallo del job de release**, no sólo con staging exitoso.
- `R023_INCIDENT_OPEN` conserva procedencia: SHA del commit, estado de baseline/fence, identidad de despliegues previo/candidato/observado, y estado de promoción.
- Invariantes explícitas: `automatic_rollback=false`, `production_write=false`, `incident_closed=false`. La ejecución de pruebas de incidentes no toca Vercel.
- Fallo de observación Vercel: `ALIAS_UNKNOWN_MANUAL_REVIEW`; evidencia contradictoria/corrupta: clasificación independiente. No se asume que una CLI exitosa sea un pago o una publicación válida.
- La clasificación de incidente se escribe en `r023-incident.json` en el runner y se publica en el resumen de Actions. Un error de diagnóstico no convierte el job fallido en SUCCESS.
- `incident_matrix_r023.py` produce un cuadro determinista de escenarios sintéticos y comprueba que ninguna clasificación habilite rollback ni escrituras.

## Restricciones
- **No** se ejecutan reversión, promoción, borrado ni force-push en esta ronda.
- No existe CAS atómico del alias Vercel probado; el fencing es lectura-detección, no cerrojo distribuido.
- El informe sintético no acredita recuperación operativa real; es validación de contratos y de código.
- Android físico, cámara y TalkBack: `NOT_OBSERVED`; QR bancario: `NO`.

## Validación requerida
- CI del workflow de publicación: verificación de manifest, Node, unit tests, HTTP anónimo, Chrome E2E; job de despliegue `SKIPPED` hasta autorización.
- H00 `verify` + `strict-torch`: `SUCCESS` para cerrar únicamente esta ronda.
- Escenarios sintéticos R023: 13/13 y pruebas R023: 24/24, **sujetos a readback real del CI**.

## Próximas fronteras
1. **P1 externa:** crear y verificar ruleset de la rama y environment secret protegido; ninguna escritura de producción hasta entonces.
2. **P1 técnica:** ejercitar la clasificación de incidentes en runner ante una falla inducida *sin token ni alias de producción*; conservar recibos verificables.
3. **P1 física:** prueba Android en dispositivo real con cámara/TalkBack, sin confundirla con Chrome headless.
