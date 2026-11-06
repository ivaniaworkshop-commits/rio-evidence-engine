# R015 — estado y siguiente delta

**OBJETIVO:** validar el recorrido de uso en Android y distinguir `RELOADED_DOCUMENT` de `PHYSICAL_DEVICE_CLOSURE`, sin exponer datos personales ni atribuir pagos reales.

**IMPLEMENTADO LOCALMENTE:** módulo `app/field_r015.js`, sección «Prueba móvil», checkpoint de venta local, comparación exacta de QR, observaciones TalkBack e importación por declaración, reporte R015 en cada clic y exportación offline.

**PRUEBAS:** ver `reports/R015_TEST_STATUS.json`; resultados válidos solamente para el entorno descrito. Si alguna falla se registra como bloqueo en vez de ocultarla.

**AUTORIDAD:** readback de GitHub para PR y manifiesto, pruebas ejecutadas localmente para funcionalidad, `USER_REPORTED_ONLY` para evidencia de campo. `CANON_PROMOTION=NO`, `MAIN_WRITE=NO`, `REAL_PAYMENT=NO`, `ANDROID_PHYSICAL_INDEPENDENT_VERIFICATION=NO`.

**PENDIENTE:** abrir R015 en un Android físico, recuperar y aportar JSON de pruebas real, medir completitud con TalkBack/cámara, comparar respaldo entre dispositivos y evaluar al menos una tarea con comerciantes voluntarios. No tratar los reportes generados por escritorio como evidencia de usuarios reales.
