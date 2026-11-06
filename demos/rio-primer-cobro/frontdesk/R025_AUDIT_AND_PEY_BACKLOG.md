# RÍO Primer Cobro — R025 · Auditoría independiente del artefacto

Objetivo: leer el archivo ZIP original de GitHub Actions R024, verificar el digest SHA-256 **del servidor**, la identidad del run y commit, la estructura de ambos JSON y el log del job que registró los errores 47 y 49.

El auditor se ejecuta en un job nuevo, distinto al que creó el artefacto. Tiene permisos solo de lectura de Actions y Contents. No necesita tokens Vercel, no crea pagos, no cambia main y no toca la URL pública.

Fuente congelada:
- Run: `42199945830`, commit `5eba35f0b8a28133a07d29a02f71218871e66b1c`.
- Artifact: `13492779462`, nombre `rio-r024-incidents`.
- SHA-256 oficial del ZIP: `f7e2ff5dd0a61207aaec628d8ff1baf852db07a6ba643fe41e665e127b94c6d9`.
- Escenarios: recibos ausentes vs corruptos; incidentes abiertos, no rollback.

Contrato fail-closed: archivo ZIP fuera de límites, hash discordante, origen incorrecto, JSON duplicado, clasificación invertida, rollback afirmado, ausencia de evidencia en logs o resultados inconsistentes → FAIL. El recibo del auditor no afirma que exista un pago ni que un hash sea verdad semántica.

**Prioridad posterior, aún sin ejecución:** evaluar el contrato de API de Pey con información histórica y el código del adaptador existente. Verificar autenticación, titularidad y autorización antes de registrar cuentas o usar CLABEs reales. Ninguna CLABE, dato de beneficiario, clave o token se incluye en el repositorio. No se programan transferencias bancarias ni pruebas de dinero irreversible sin un entorno y autorización contrastados. La caja pública permanece con QR NO PAGABLE.

La activación del despliegue automático a Vercel sigue BLOQUEADA hasta que existan las reglas de GitHub y un entorno de secretos protegido.
