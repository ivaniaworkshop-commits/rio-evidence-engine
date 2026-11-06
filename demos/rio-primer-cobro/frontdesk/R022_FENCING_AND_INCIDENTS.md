# RÍO Primer Cobro — R022 · Fencing de promoción e incidentes

**Objetivo:** impedir publicaciones sobre un estado obsoleto y preservar la genealogía de incidentes sin una reversión automática potencialmente destructiva.

## Estado inicial observado

- Rama: `deploy/primer-cobro`; PR #30 en borrador, `main` sin modificar.
- Proyecto Vercel autorizado: `prj_J7YrJusN08qUXrZNPDBmspVRKW6d`; alias: `rio-primer-cobro-frontdesk.vercel.app`.
- Alias en el último readback: `dpl_3j8jWcQ84xkEKXYk5Fym4odB9RFU` (R016).
- GitHub Rulesets: `[]` en la consulta inicial R022. Por tanto, publicación de producción **BLOCKED**; no hay nuevo `deploy=SUCCESS` ni promoción automática.
- Último ensayo del candidato R021: 2/2 HTML exactos y 33/33 controles en Chrome; esa evidencia no acredita ejecución Android física.

## Ruta de promoción R022 (PROGRAMMED, NO ACTIVE)

```
VERIFY_SOURCE
 → OBSERVE_LIVE_ALIAS (baseline + commit)
 → STAGE_PRODUCTION_WITHOUT_DOMAIN
 → CANDIDATE_BYTE_READBACK
 → CANDIDATE_CHROME_E2E
 → RECHECK_GITHUB_HEAD_SHA
 → READ_CANDIDATE_IDENTITY (project, READY, production, URL)
 → RECHECK_LIVE_ALIAS (must equal baseline)
 → PROMOTE_CANDIDATE
 → RECHECK_LIVE_ALIAS (must equal candidate ID)
 → LIVE_PUBLIC_BYTE_READBACK
 → REPORT_PASS
```

Si una verificación falla después de preparar el candidato, registrar un incidente tipado: `ALIAS_UNKNOWN_MANUAL_REVIEW`, `ALIAS_CHANGED_OR_PROMOTION_NOT_APPLIED_NO_ROLLBACK` o `CANDIDATE_OWNS_ALIAS_BUT_POSTCHECK_FAILED`. El workflow falla cuando una comprobación crítica falla; el registro de incidente no la convierte en PASS.

**NO_ROLLBACK_AUTOMATICO:** comprobar el alias y promover no constituyen una operación atómica de compare-and-swap. Puede ocurrir una escritura externa entre ambas. Por ello, el verificador reconoce incertidumbre y nunca intenta revertir el alias de forma automática: podría sobrescribir la versión legítima de otro operador. Exige readback posterior y revisión/rebase humano ante discrepancia.

## Garantías y límites

- Credencial Vercel **solo** en los pasos que consultan el API autenticado y publican; nunca se imprime ni se guarda en los recibos.
- Llamadas de observación limitadas al proyecto y al alias autorizados, sin redirecciones HTTP del API autenticado.
- Se rechazan candidatos preview, no READY, ajenos al proyecto, dominios ajenos y commits obsoletos.
- El resultado `FENCE_PASS` no equivale a activación de runtime ni prueba que Vercel no pueda cambiar concurrentemente: es una barrera de detección, no un bloqueo distribuido atómico.
- `ALIAS_CONFIRMED` no equivale a `PUBLIC_BYTE_READBACK_PASS`: ambas evidencias son independientes.
- Los ensayos unitarios son **sintéticos**. La integración de este módulo con el API real de Vercel aún no se ha ejecutado porque los secretos y rulesets siguen pendientes.
- Sin pagos bancarios reales; QR de práctica `NO-PAGABLE`; Android físico `NOT_OBSERVED`.

## Pruebas y aceptación

`python3 -m unittest discover -s demos/rio-primer-cobro/frontdesk/tests -v`

Se exigen pruebas de candidato correcto, proyecto/target incorrectos, alias concurrente antes/después de promoción, commit obsoleto, API malformado o redirigido y ausencia de rollback automático. La suite CI debe mantener las pruebas HTTP y el navegador del candidato. El manifest `MANIFEST.json` contabiliza el código y los recibos versionados.

## Deltas siguientes

**P1 externo:** proteger `deploy/primer-cobro`, configurar el environment secret `VERCEL_TOKEN` y las variables de CI, ejecutar un primer despliegue autorizado con `verify`, `release-authority`, `browser-public`, `deploy`, confirmación de alias y readback, todos en PASS.

**P1 físico:** completar Android, cámara y TalkBack con recibos observados. **P2 técnico:** evaluar soporte transaccional real de compare-and-swap en el proveedor antes de ofrecer rollback automatizado.
