# RÍO R032 — Administrar protección de rama candidata (sin despliegue)

**Estado de origen (2026-11-06):** no existe un ruleset activo exactamente aplicable
a `refs/heads/candidate/primer-cobro-r031-clean-20261106`. El único ruleset
activo observado protege `main`. La candidata es una rama con genealogía
revisada y actualmente SIN protección administrativa acreditada.

## Qué quedó preparado en este repositorio
- `ruleset_admin_r032.py --plan` produce una configuración local **sin red ni escrituras**.
- El plan exige revisión por otra persona, descarte de aprobaciones obsoletas,
  rechazo de push no fast-forward, protección frente a borrado y tres checks
  obligatorios con productor GitHub Actions (ID **15368**, observado vía API).
- Checks: `verify`, `strict-torch`, `candidate-readiness`.
- El workflow de `candidate-readiness` se ejecuta en **todos los PR** cuya base
  es la candidata, sin filtros de rutas. H00 ejecuta `verify` y `strict-torch`
  en pull requests, con permisos de sólo lectura.
- `--apply` existe únicamente como operación **administrativa explícita**, no
  se invoca desde los workflows automáticos de RÍO. Requiere token con permiso
  específico de administración de reglas, doble confirmación y SHA vigente.

## Opción GUI de GitHub (administrador)
1. Abrir el repositorio `ivaniaworkshop-commits/rio-evidence-engine` → **Settings**
   → **Rules** → **Rulesets** → **New branch ruleset**.
2. Nombre: `RIO_PRIMER_COBRO_CANDIDATE_R032`. Enforcement: **Active**.
   Target: **Branch**. Aplicar sólo a
   `candidate/primer-cobro-r031-clean-20261106`; sin exclusiones ni bypass.
3. Requerir PR antes de cambiar la rama: al menos **una aprobación**,
   descartar aprobaciones tras nuevos pushes y aprobación del último push
   por un revisor distinto. Proteger borrado y bloquear force-push.
4. Exigir los tres checks anteriores, seleccionando **GitHub Actions** como
   productor. Marcar **Require branches to be up to date before merging**.
   Si los checks no aparecen, generar primero un PR de prueba dirigido a esta
   rama; NO usar nombres arbitrarios.
5. Guardar. Leer nuevamente las reglas por la API; confirmar coincidencia
   de rama, tipo de reglas, contexto e integración. Evaluar separadamente
   protección de environment y secretos Vercel.

## Opción CLI para administrador autenticado (manual)
El administrador, fuera de este chat, puede generar y revisar primero un plan:
`python3 demos/rio-primer-cobro/integrations/ruleset_admin_r032.py --plan --output /tmp/r032-plan.json`.

El script admite `--apply` **sólo con token GH_TOKEN fuera del repositorio**,
variable de reconocimiento `RIO_R032_ADMIN_APPROVAL=approved`, confirmación
literal de rama y SHA conocido mediante `--expected-head`. NO almacenar tokens,
señales bancarias ni datos personales en el repositorio o logs de Actions.

## Semántica de evidencias
`RULESET_PREPARED != RULESET_ACTIVE`; y `RULESET_ACTIVE != DEPLOY_AUTHORIZED`.
Un readback de reglas tampoco acredita environment protegido, revisión humana,
identidad restringida ni disponibilidad de credenciales de Vercel.

## Pendientes abiertos
GitHub ruleset aún no aplicado por este conector; environment de Vercel no
acreditado; PR #36 sin fusionar; referencias históricas contaminadas aún accesibles;
Pey real y pagos bancarios siguen desactivados. Ninguna escritura de producción.
