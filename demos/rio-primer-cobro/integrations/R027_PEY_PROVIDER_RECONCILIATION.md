# RÍO Primer Cobro · R027 — Reconciliación Pey/CoDi y evidencia de pago
Fecha contextual: 2026-11-06. Rama de revisión: `deploy/primer-cobro`.

## FUENTES Y TIPOS (sin fusionar por parecido)
- Pey: antecedentes R06/R09/R10 y conversación de Primer Cobro. **Fuente histórica no verificada**. Se mencionaron candidatos `POST /codi/qr`, `POST /bank-account`, autenticación `Bearer`, plazo mínimo QR de seis minutos, webhooks y cuentas bancarias; **NO consta** contrato oficial vigente leído y validado ni sandbox bancario observado. Estos son candidatos, no endpoints autorizados ni verificados.
- `portfedh/codi-api`: código fuente público de **un tercero** revisado en R026/R027: `POST /v2/codi/qr`, cabecera `x-api-key`, dependencia de certificados Banxico y Supabase. El repositorio usa licencia Apache-2.0. No consta relación de identidad ni compatibilidad técnica garantizada con Pey.
- Primer Cobro R026: emulador local sin red, cuentas de prueba sintéticas, QR no pagable, eventos de laboratorio. **NUNCA** firma oficial de proveedor, webhook autenticado en producción o liquidación real.

## DELTA R027 — IMPLEMENTADO, SIN RED
`pey_evidence_r027.mjs` expone:
1. `providerEvidenceMatrix()`: conserva procedencia por fuente y dimensiones sin asimilar productos distintos.
2. `compareProviderContracts()`: detecta divergencias de ruta y autenticación; `automaticFieldMapping=false`.
3. `assessProductionEligibility()`: evalúa siete dimensiones declaradas, pero **nunca** activa producción basándose en autodeclaración, incluso cuando todos los indicadores son `true`; no hay atestación del host autenticado.
4. `classifyUnverifiedPaymentSignal()`: rechaza datos bancarios no autorizados, y clasifica QR creado, webhook alegado, abono alegado, referencia duplicada y confirmación de laboratorio como **no liquidatorios**; un evento no autoriza a marcar una venta como pagada.

## MODELO SEMÁNTICO DEL PAGO
`QR_RENDERED != WEBHOOK_REPORTED != PROVIDER_AUTHENTICATED != BANK_SETTLEMENT_VERIFIED`.
La clave `paid` nunca cambia por datos externos sin firma y conciliación. Ni los hashes ni un token sintético elevan la autoridad de una transacción.

## PENDIENTES MATERIALES
- Contrato oficial Pey vigente y entorno de pruebas sin movimientos reales.
- Identidad de proveedor, identidad y autorización del comercio/titular bancario, autenticación/certificados y documentos de conciliación. Guardar cualquier secreto y dato bancario **sólo en sistemas protegidos y autorizados**, nunca en un repo público.
- Prueba de extremo a extremo de firma de webhook, rotación/revocación de secretos, replay, tiempo, duplicados, importes y folio; comprobar abono real únicamente mediante integración bancaria autorizada.
- Despliegue de producción sigue bloqueado por rulesets GitHub ausentes y falta de autorización de secretos.
- Android físico y cobros reales: `NOT_OBSERVED`.

`R027=PROVIDER_SEMANTICS_TESTABLE`, no `PEY_INTEGRATION_ACTIVE`.
