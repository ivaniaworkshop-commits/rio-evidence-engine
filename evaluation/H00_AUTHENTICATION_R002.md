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
