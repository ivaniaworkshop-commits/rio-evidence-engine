# Mercado Abierto · API pública de pey

Cierre del 14 de noviembre de 2026. Integración publicada en https://rio-pey-codi-gateway.vercel.app; acceso habitual: https://rio-primer-cobro-frontdesk.vercel.app/app.html.

La aplicación integra las 11 operaciones del contrato público https://docs.pey.mx/openapi.json: QR CoDi; notificación CoDi al celular; registro y consulta de cuentas; creación, actualización y consulta de enlaces; consulta de transacción individual y movimientos por llave, cuenta y QR.

Mis negocios permite registrar CLABEs y consultar su estado, con CLABE enmascarada. Caja incorpora celular y enlaces usando los datos compartidos de la venta. Los enlaces permiten propina y solo se modifica su importe mientras están pendientes. Se conserva historial persistente y recuperación de resultados inciertos sin reenviar automáticamente cobros.

Se procesan los cuatro eventos públicos documentados: pago de QR, pago de notificación, estado de enlace y activación de cuenta. La firma y la lectura autenticada del proveedor preceden a la confirmación. Se reutilizan los comprobantes con QR verificable, correo al cliente y negocio y opción de no enviar. Pagos parciales y retornos de navegación no confirman el pago.

Evidencia: suite completa durante integración 593 aprobadas/28 omitidas; comprobación específica posterior 36 aprobadas; recorrido Chromium de celular, comprobante y alta de cuenta a 390/320 px. El despliegue coincide con los 93 archivos del manifiesto validado. Migración aditiva 021 comprobada en rama aislada y producción, conservando registros anteriores.

Las pruebas de esta ronda usaron un proveedor aislado; no se realizaron pagos, registros bancarios reales ni notificaciones a celulares. La disponibilidad de tarjetas y otros métodos depende de la configuración de cada llave en pey. No se afirma liquidación bancaria independiente.

El contrato no documenta eliminar cuentas, reembolsar, cancelar, crear llaves ni configurar webhooks mediante API. Estas capacidades no se inventaron. Caja mantiene QR de importe fijo y vencimiento para conciliación; no expone cobros abiertos arbitrarios.

El código de producción y la evidencia técnica completa permanecen en el repositorio privado autorizado; este documento publica únicamente el estado funcional.
