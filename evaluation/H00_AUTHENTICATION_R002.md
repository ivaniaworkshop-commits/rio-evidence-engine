# H00 R002 — autenticación de procedencia de recibos CI (GitHub OIDC + Sigstore)

Estado: **implementación candidata en PR, no promoción**. Esto autentica la **procedencia y los bytes** de los dos recibos cuando una atestación GitHub es verificada contra su política. NO autentica que las métricas sean verdad, que exista holdout independiente, ni que el ejecutor no haya sido comprometido.

## Esquema de confianza

1. `verify` y `strict-torch` generan sus JSON de autodeclaración H00 y datos de prueba, y los publican como artefactos del MISMO run.
2. El job `attest-receipts` solo existe después de ambos jobs exitosos. No hace checkout ni ejecuta programas proporcionados en los artefactos. Descarga artefactos por nombre de esta ejecución, valida pares archivo/hash y recibos contra `GITHUB_REPOSITORY`, `GITHUB_SHA`, `GITHUB_RUN_ID` y `GITHUB_RUN_ATTEMPT`.
3. Solo ese job tiene `id-token: write` y `attestations: write`. `actions/attest-build-provenance` usa identidad OIDC GitHub y la cadena de confianza Sigstore para emitir una atestación de los bytes exactos de `verify-receipt.json` y `strict-receipt.json`.
4. `verify-attestation`, sin permisos OIDC ni de escritura, comprueba criptográficamente ambos sujetos con `gh attestation verify`; obliga a identificar repositorio, workflow firmante y digest de código fuente.
5. Los bundles y resultados de verificación se publican como artefactos. La retención es de 30 días; conservar externamente los paquetes si se necesita prueba histórica.
6. Se permiten atestaciones de `push` a `main` y PRs internos, pero **no** se emiten desde PRs originados en forks con permisos de firma. La validez de la firma no convierte un PR en código aprobado.

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
