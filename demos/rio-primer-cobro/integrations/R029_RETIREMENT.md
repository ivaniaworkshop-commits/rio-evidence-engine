# RÍO R029 — Cuarentena y auditoría de referencias

GitHub confirmó protección activa para main, no para la rama heredada de Primer Cobro. PR #30 permanece cerrado sin fusionar; PR #36 permanece abierto en borrador. El workflow en deploy/primer-cobro tiene deploy.if=false desde R029, y el job fue SKIPPED en CI.

El auditor inspecciona el historial del archivo de pruebas históricamente afectado, distingue números de 18 dígitos usando checksum y calcula cuáles referencias Git descargadas conservan los commits. Nunca imprime los valores encontrados. Un PASS significa alcance local auditado, NO limpieza global: referencias de pull request no descargadas, objetos huérfanos, caches, clones y forks pueden conservar material.

Retirada administrativa pendiente: completar revisión y protección de la ruta sana; retirar rama histórica con autorización de propietario; solicitar saneamiento de vistas cacheadas mediante el procedimiento de GitHub; verificar nuevamente referencias y superficies. No hacer force-push ni afirmar purga sin evidencia externa.

La integración Pey real, cuentas bancarias, pagos y Android físico continúan bloqueados o sin evidencia.
