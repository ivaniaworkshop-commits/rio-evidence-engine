# H00 R002 — autenticación de procedencia de recibos CI (GitHub OIDC + Sigstore)

Estado: **implementación candidata en PR, no promoción**. Esto autentica la **procedencia y los bytes** de los dos recibos cuando una atestación GitHub es verificada contra su política. NO autentica que las métricas sean verdad, que exista holdout independiente, ni que el ejecutor no haya sido comprometido.

## Esquema de confianza

1. `verify` y `strict-torch` generan sus JSON de autodeclaración H00 y datos de prueba, y los publican como artefactos del MISMO run.
2. El job `attest-receipts` solo existe después de ambos jobs exitosos. No hace checkout ni ejecuta programas proporcionados en los artefactos. Descarga artefactos por nombre de esta ejecución, valida pares archivo/hash y recibos contra `GITHUB_REPOSITORY`, `GITHUB_SHA`, `GITHUB_RUN_ID` y `GITHUB_RUN_ATTEMPT`.
3. Solo ese job tiene `id-token: write` y `attestations: write`. `actions/attest-build-provenance` usa identidad OIDC GitHub y la cadena de confianza Sigstore para emitir una atestación de los bytes exactos de `verify-receipt.json` y `strict-receipt.json`.
4. `verify-attestation`, sin permisos OIDC ni de escritura, comprueba criptográficamente ambos sujetos con `gh attestation verify`; obliga a identificar repositorio, workflow firmante y digest de código fuente.
5. Los bundles y resultados de verificación se publican como artefactos. La retención es de 30 días; conservar externamente los paquetes si se necesita prueba histórica.
6. **R012:** únicamente se emiten atestaciones al ejecutar `push` en `refs/heads/main` con `github.ref_protected == true`. Los PR internos y de forks producen recibos para diagnóstico, **no** una firma. Que GitHub marque una referencia como protegida no acredita por sí mismo una revisión independiente ni la política completa.

## Comprobación independiente, fuera del runner

Obtener el artefacto `h00-attested-<attempt>` (contiene `bundle.json` y los dos recibos). Comprobar cada sujeto:

```bash
gh attestation verify verify-receipt.json \
  --bundle bundle.json \
  --repo ivaniaworkshop-commits/rio-evidence-engine \
  --signer-workflow ivaniaworkshop-commits/rio-evidence-engine/.github/workflows/h00-integrity.yml \
  --source-digest <SHA-40-del-checkout-que-figura-en-el-reporte>

gh attestation verify strict-receipt.json \
  --bundle bundle.json \
  --repo ivaniaworkshop-commits/rio-evidence-engine \
  --signer-workflow ivaniaworkshop-commits/rio-evidence-engine/.github/workflows/h00-integrity.yml \
  --source-digest <SHA-40-del-checkout-que-figura-en-el-reporte>
```

Después comprobar `run.id`, `run.attempt`, `run.sha`, estado y SHA-256 de cada dato adjunto usando los recibos firmados. **No aceptar un hash aislado, un estado PASS escrito por el runner o una atestación sin la política de identidad.** El resultado del job de verificación es una prueba operacional adicional, pero el operador independiente debe ejecutar su propio `gh attestation verify` desde una máquina que controle.

## Condiciones de seguridad y límites

- La credencial OIDC pertenece a GitHub Actions, no a la cuenta propietaria. No se exporta un secreto ni una clave privada.
- GitHub / Sigstore son raíces de confianza de procedencia. No se obtiene un custodio verdaderamente independiente ni una firma privada del propietario.
- Un workflow/commit de PR puede ser malicioso; para confiar en el resultado es indispensable revisar el código y la política de rama. La firma por sí sola no satisface control de cambios.
- Para PRs de forks, el job privilegiado queda omitido: **AUTENTICACIÓN AUSENTE**, no PASS.
- `H08=BLOCKED_NO_EXTERNAL_HOLDOUT`; `H14.candidate_promoted=false`; `PRODUCTION=NO` siguen obligatorios. La autenticación de artefactos no cambia estos estados.
- Sin una atestación real descargable y una verificación válida, el estado es `AUTHENTICATION_PENDING`, no `AUTHENTICATED`.

El valor de la atestación alcanza: *"estos bytes fueron atestados por un workflow identificable con identidad respaldada por GitHub"*. No alcanza: *"todo el experimento fue probado por un evaluador independiente"*.

## R012 — separación de checks y firma (política candidata, PR #26)

- **Antes del merge (PR):** los jobs `verify` y `strict-torch` ejecutan los gates y publican recibos; `attest-receipts` y `verify-attestation` se omiten deliberadamente. La omisión no es un `PASS` de firma.
- **Después del merge (push a main):** sólo se permite firmar cuando `github.ref_protected == true`; después el job de verificación read-only valida ambos recibos del mismo run.
- **Advertencia de autoridad:** `github.ref_protected` no prueba que el ruleset incluya los cuatro checks, revisión independiente o ausencia de bypass. Se requiere readback administrativo y control de cambios antes de llamar confiable al workflow.
- **Regla de checks propuesta para PR:** exigir `verify` y `strict-torch` como prerrequisitos de integración, más revisión por persona distinta del autor y reglas de rama. No exigir los dos jobs posteriores al merge como checks de PR. Un check omitido puede aparecer como resultado aceptable en GitHub y **no prueba emisión de firma**.
- **Procedencia histórica:** la atestación del run 42180299757 sigue siendo válida para `refs/pull/26/merge`; no debe reclasificarse retrospectivamente como atestación de `main` protegida.
- **Protección remota:** no está activada; `H08=BLOCKED_NO_EXTERNAL_HOLDOUT`, `candidate_promoted=false` y `production_ready=false` no cambian.

## R013 — unprotected main push fails closed (candidate PR #26)

- The `verify` and `strict-torch` jobs now fail with exit code 2 if a `push` event targeting `refs/heads/main` reports `github.ref_protected != true`. This guard is the **first step before checkout** in both jobs.
- A PR continues to run the two validation jobs; the guard step is omitted on PR events. OIDC/Sigstore signing remains restricted to protected `main` pushes and remains skipped on PRs.
- A green main workflow should not be possible solely because attestation jobs were skipped on an unprotected main push. This is an observability/fail-closed improvement, **not branch write enforcement**.
- The guard depends on GitHub's `ref_protected` metadata, which does not itself prove approval requirements, effective ruleset content, or bypass policy. No live unprotected main push was executed to test this path. `MAIN_PROTECTED=false` and `RULESET_ACTIVE=false` remain observed blockers.

## R014 — behavioral tests of actual YAML guard (candidate PR #26)

- The tests extract the `run: |` shell script for `H00 reject green CI for unprotected main push` directly from the checked-in workflow, for both `verify` and `strict-torch`.
- They execute that exact script in a temporary directory with a restricted environment and no GitHub credentials. Values `false`, empty, absent, `0`, `TRUE`, and `true ` must return exit code 2 with `UNPROTECTED_MAIN_PUSH`; only exact `true` may return 0.
- This adds behavioral evidence beyond R013's static YAML checks. It does **not** exercise a real GitHub push, prove `github.ref_protected` mapping, or activate repository branch rules. No direct writes to `main` are permitted by this test.

## R015 — identidad PR vs checkout de integración

- En eventos pull_request, GITHUB_SHA/run.sha identifica el checkout de refs/pull/N/merge, que difiere del head SHA de la rama del PR.
- Añadimos run.pull_request con número, head_sha, base_sha, repositorios y checkout_sha, verificando consistencia con el JSON del evento; se conserva el contrato extensible RIO_H00_CI_RECEIPT/1.0.
- Se rechazan eventos ausentes o malformados, claves duplicadas, referencias/números inconsistentes, SHAs inválidos y repositorios base diferentes. El merge SHA del evento puede estar desfasado: su diferencia respecto del checkout se conserva como telemetría consultiva, no como una denegación.
- La consistencia es autodeclarada por GitHub Actions, NO una certificación independiente ni una política de rama.
- Evidencia histórica (run 42197920923): PR head 2ed2090199e685400d05ad6615b53f5dc472215a; merge checkout 5c65a2a28b2563f9ac3d33a0fc5ec07f47a3f48a; main base e85b1e808081510a8267457c9b4aafeca064cb36.

### Corrección R015 tras prueba real

Las ejecuciones 42199523148 y 42199986207 rechazaron la igualdad obligatoria entre merge_commit_sha del payload y GITHUB_SHA del checkout. El segundo run identificó PR_CHECKOUT_MERGE_SHA_MISMATCH. El recibo conserva event_merge_matches_checkout y declara checkout_parent_binding=NOT_VERIFIED_BY_RECEIPT. La correspondencia real de padres fue comprobada separadamente con la API GitHub, no acreditada por este recibo.

## R016 — prueba de padres del checkout sintético

Los dos jobs de validación previa al merge (`verify` y `strict-torch`) ejecutan `python3 -m scripts.h00_pr_checkout --output output/h00/pr-checkout.json` inmediatamente después del checkout. El verificador lee `git rev-parse HEAD` y las cabeceras reales del objeto `git cat-file -p HEAD`; funciona también con `fetch-depth: 1`, a diferencia de un `rev-list --parents` sobre un clon superficial.

Una ejecución pasa únicamente si `GITHUB_SHA` coincide con `HEAD`, el commit tiene **exactamente dos padres**, el primero coincide con el SHA de base y el segundo con el SHA de head del evento PR. Cualquier discrepancia da exit 2 y deja diagnóstico con `reason_code`. La diferencia histórica `event_merge_matches_checkout=false` permanece consultiva, nunca una identidad acreditada.

Los artefactos H00 de ambos jobs incorporan `pr-checkout.json`. La procedencia es `RUNNER_GIT_OBJECT_AND_EVENT_NOT_INDEPENDENT`: corrobora genealogía de checkout en el runner pero no autentica revisión, ruleset ni producción. Son once regresiones nuevas, con checkout superficial y rechazos adversariales. `main` no cambia y el PR #26 sigue sin fusionar.

## R020 — asociación criptográfica del parent-binding al recibo principal H00

- En eventos `pull_request`, el colector `scripts/h00_ci_receipt.py` incorpora `pr-checkout.json` con su tamaño y SHA-256 en `input_records.pr_checkout` y valida su contexto: esquema, autoridad de runner, estado `RUNNER_GIT_PARENT_BINDING_PASS`, ausencia de promoción, ID e intento del run, número de PR, SHA de checkout, base/head y **padres ordenados**.
- La verificación rechaza (código 2 del CLI cuando el upstream era verde) si el archivo falta, está malformado, tiene claves JSON duplicadas o contradice las identidades del evento. `checks.pr_checkout_parent_binding` no se marca verdadero por la mera existencia de un hash.
- Una prueba válida queda registrada como `run.pull_request.checkout_parent_binding=RUNNER_REPORT_CONSISTENT_NOT_INDEPENDENT`, junto con `parent_binding_report_sha256`. Esta consistencia no sustituye verificación independiente, revisión humana ni controles administrativos.
- Los jobs `verify` y `strict-torch` pasan explícitamente `--pr-checkout output/h00/pr-checkout.json`; el reporte debe existir porque ambos ejecutan primero el verificador de padres R016. Para `push` a `main` no se exige ni inventa el archivo de PR.
- Se mantiene el esquema compatible `RIO_H00_CI_RECEIPT/1.0` con campos aditivos, pero se endurecen las condiciones de éxito en un PR. La garantía es **vinculación de bytes y contexto generados por el propio runner**, nunca verdad semántica o custodia externa.
- `MAIN_PROTECTED=true` por ruleset R017, pero los checks administrativos obligatorios y la revisión independiente del PR #26 continúan pendientes.

## R022 — auditoría cruzada read-only dentro de GitHub Actions

- Se añade el job `cross-audit` ejecutable **sólo en pull_request** tras `verify` y `strict-torch` con `permissions: {contents: read, actions: read}`, sin `id-token: write` ni `attestations: write`. No firma, aprueba, fusiona ni publica al exterior.
- El job descarga los dos artefactos **del mismo run y run_attempt**, con los nombres h00-verify-* y h00-strict-torch-*, en directorios separados. Ejecuta 22 regresiones adversariales y el auditor `scripts/h00_cross_artifact_audit.py`, anclando run ID, PR head y checkout SHA del contexto del runner. Si falta un artefacto o existe discrepancia se marca FAIL y se emite diagnóstico JSON cuando es posible.
- Como `actions/download-artifact` **extrae** los artefactos, el auditor realiza un reempaquetado temporal, acotado y sin ejecutar sus contenidos. Los SHA-256 resultantes corresponden únicamente a **ZIP reconstruidos localmente**, **no** se presentan como digests originales de los ZIP de GitHub. Se verifican los hashes de reportes internos y su consistencia entre jobs.
- El diagnóstico `output/h00/cross-audit.json` se publica como `h00-cross-audit-<attempt>`. La clasificación de éxito es `CONSISTENT_SELF_REPORTED_NOT_INDEPENDENT`: no significa revisión humana independiente ni autorización externa.
- La suite `strict-torch` incorpora los tests R022 por discovery. La protección `main.protected=true` está activa, pero se mantiene como deuda independiente la regla administrativa `required_status_checks` (verify/strict-torch) y la aprobación real de un revisor distinto del autor. El PR #26 no se fusiona automáticamente.

## R023 — control del ruleset administrativo en CI (fail-closed)

- El job **H00 admin policy gate (read-only)** consulta por GET el ruleset `26688691` de GitHub antes de declarar conformidad administrativa. No usa permisos de escritura, no realiza `PUT`, `PATCH`, `POST` ni aprueba el PR.
- El control espera `RIO_MAIN_PROTECTION_R001` activo, aplicado exclusivamente a `refs/heads/main`, sin bypass, sin eliminación ni non-fast-forward, al menos una aprobación, invalidación de aprobaciones obsoletas y nueva aprobación del último cambio.
- **Debido a R022**, exige exactamente cuatro checks de GitHub Actions (integration ID `15368`): `verify`, `strict-torch`, `H00 cross-audit receipts (read-only)` y `H00 admin policy gate (read-only)`. Deben estar anclados a GitHub Actions, con actualización de base obligatoria. No exige los dos jobs de firma, que son omitidos en PR.
- Si GitHub devuelve un ruleset incompleto, ausente, no accesible o incongruente, el job escribe `output/h00/admin-policy.json`, devuelve código **2** y publica la evidencia con `if: always()`. La ausencia de permisos de lectura se clasifica UNKNOWN/READBACK_FAILED, no como éxito.
- `ACTIVE_ADMIN_POLICY_VERIFIED` significa sólo que el runner observó la configuración exigida, **no** que exista una revisión humana independiente ni holdout H08. La verificación se ejecuta en CI, pero todavía no es una regla administrativamente obligatoria hasta que GitHub incorpore el propio check al ruleset.
- **Situación comprobada antes de R023:** `main.protected=true`, ruleset `26688691` activo, con aprobaciones, pero sin `required_status_checks`, PR #26 sin revisiones y sin merge. El job está diseñado para FALLAR en esa situación (resultado correcto, no degradación accidental). Se preserva el bloqueo.
- Las 26 regresiones offline cubren cambios de bypass, ámbitos, integraciones, aprobación, checks omitidos, duplicados JSON, valores no finitos, tamaño, tokens ausentes y una solicitud GET de sólo lectura.

**Instrucción de configuración administrativa restante:** editar `https://github.com/ivaniaworkshop-commits/rio-evidence-engine/rules/26688691`, activar `Require status checks to pass`, marcar los cuatro nombres exactos anteriores y `Require branches to be up to date`; preservar todas las restricciones existentes y no habilitar bypass. Hacer readback y volver a ejecutar CI. Una aprobación independiente sigue siendo una condición separada.
