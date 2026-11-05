# RÍO R010 — Contrato de integración financiera pendiente

**Estado:** `NOT_IMPLEMENTED / NOT_TESTED / NO_CREDENTIALS / NO_REAL_MONEY`.

El historial proporcionado menciona documentación de pey para solicitudes CoDi (QR/push) y notificaciones. **Esta ronda no consultó documentación viva**, por lo que las propiedades exactas, firmas, entornos de prueba, comisiones y condiciones vigentes son `UNKNOWN` hasta validar la especificación actual y la autorización del usuario.

## Gates requeridos antes de cualquier pago real

1. Leer la documentación técnica **vigente** de pey, las reglas de firma de webhooks, acuerdos, requisitos legales y disponibilidad del entorno de prueba.
2. Mantener secretos y claves en servidor, jamás en HTML, JSON exportado, localStorage ni código distribuible.
3. Registrar solicitud de pago vinculada a una venta con identificador interno inmutable, importe entero en centavos, moneda, vencimiento y referencia externa conforme a restricciones del proveedor.
4. Un QR o solicitud generada produce estado `REQUESTED/PENDING`, **nunca** `PAID`.
5. Sólo aceptar eventos de confirmación provenientes de un canal autenticado, firma verificada con material actual autorizado y correspondencia exacta de comercio, solicitud, importe, moneda y transacción; definir reconciliación cuando el proveedor permita consulta de estado.
6. Idempotencia y replay protection: rechazar duplicados sin sumar ventas ni duplicar entregas; conservar procedencia y registro de eventos. Eventos fuera de orden pasan a revisión, nunca a confirmación automática por intuición.
7. Si hay caída, webhook retrasado, firma inválida, discrepancia o resultado ambiguo: `UNKNOWN / REVIEW_REQUIRED`; consulta de estado por el canal financiero autorizado.
8. Separar demostración y producción también en UI, dominio, métricas, registros, credenciales y pruebas. Confirmación `SIMULATED` no puede promoverse a `REAL`.
9. Pruebas autorizadas primero en sandbox **sólo si** su existencia y condiciones están verificadas; ninguna transacción real está autorizada por este documento.
10. Diseño accesible, privacidad por defecto, manejo de controversias y procedimientos de recuperación para comerciantes.

**Invariante:** `QR_GENERATED != PAYMENT_CONFIRMED`, `AI_RESPONSE != BANK_EVIDENCE`, `MOCK_EVENT != REAL_SETTLEMENT`.
