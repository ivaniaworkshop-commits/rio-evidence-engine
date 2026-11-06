# RÍO Primer Cobro — R026: contrato Pey/CoDi y adaptador emulado

## Evidencia recuperada

- Contrato histórico Pey aportado al proyecto, **CANDIDATE_UNVERIFIED**: `POST /codi/qr`, posible `POST /bank-account`, firma de webhooks, `Authorization: Bearer …`, estados de alta bancaria y supuestas capacidades de sandbox. Ninguna llamada se ha ejecutado ni se ha confirmado la disponibilidad real del proveedor.
- Repositorio público de terceros `portfedh/codi-api`: `POST /v2/codi/qr`, cabecera `x-api-key`, verificación con certificados Banxico, dependencia de Supabase y endpoints de QR/push/consulta. Su documentación sostiene estas características, pero **no es la API Pey** ni acredita interoperabilidad, licencia operativa o autorización bancaria.
- Los componentes de Primer Cobro R015 muestran actualmente QR educativo `NO-PAGABLE` y no tienen procesador de pagos reales.
- Contrato de aprendizaje previo: `DemoAccount/demo-account-001`, alias `Puesto de prueba`, modo `SIMULADA_NO_BANCARIA`. Nada de datos de titular, CLABE, RFC, teléfono bancario, keys, PIN/OTP o transferencias reales en el repositorio.

## R026 — alcance de ejecución

`pey_emulated_r026.mjs` es un módulo **offline puro**, sin llamadas HTTP, almacenamiento de credenciales, rutas activas, cuentas reales ni transferencias.

Garantías del contrato implementado:
- Importes enteros en centavos, moneda MXN y caducidad explícita.
- QR sintético siempre marcado `NO-PAGABLE`.
- Campos de cuenta restringidos a `DemoAccount/demo-account-001`; claves adicionales rechazadas.
- Eventos sintéticos localmente autenticados con secreto de laboratorio (HMAC) para detectar alteraciones **dentro de pruebas**, nunca confundidos con webhooks firmados por Pey o Banxico.
- Idempotencia por identificador de evento, rechazo de cambios bajo el mismo ID, de discrepancias de importe, de eventos expirados y de transiciones desde estados terminales.
- `DEMO_SIMULATED_CONFIRMED` es solo evidencia de simulación. `realPaymentConfirmed=false`, `bankSettlementConfirmed=false`, `externalTransferExecuted=false` permanecen inmutables.

## Gates pendientes para una integración de verdad

1. Identificar inequívocamente el proveedor y la documentación oficial vigente; resolver contradicciones de endpoints, sandbox y producción.
2. Demostrar titularidad/autorización de la cuenta receptora sin publicar datos personales ni bancarios, y obtener un ambiente de pruebas que **no mueva fondos**.
3. Proveer backend aislado con credenciales en servidor, autenticación real, validación criptográfica del webhook oficial, correlación y reconciliación de liquidaciones.
4. Separar formalmente QR creado, notificación recibida, abono confirmado y liquidación bancaría verificada. No promover a `PAID` por un webhook no verificado o por un QR.
5. Auditoría de seguridad, autorización de despliegue, protección de la rama y pruebas reales antes de cualquier activación.

## Autoridad, publicación y límites

El adaptador R026 **no está conectado a la UI pública**, sólo al CI en la rama `deploy/primer-cobro`; no crea cuentas reales ni modifica la página R016. No se copió código de `portfedh/codi-api`. Cualquier banco, usuario beneficiario o CLABE discutido permanece fuera del artefacto público. `AUTO_DEPLOY=BLOCKED_NO_ACTIVE_RULESETS`; producción no se promociona.

## Aceptación

`node --test demos/rio-primer-cobro/tests/test_pey_r026.mjs` debe aprobar los casos con evidencia de GitHub Actions y manifest reconciliado. Las pruebas son deterministas y locales; **no equivalen a integración Pey/CoDi activa**.
