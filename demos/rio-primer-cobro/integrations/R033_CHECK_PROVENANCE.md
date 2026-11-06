# R033 · Checks observados versus autoridad de publicación

Este auditor se ejecuta en otro job de GitHub Actions sin secretos Vercel.
Recupera en tiempo de ejecución el PR #39 cerrado sin fusionar, su commit
de prueba y tres comprobaciones reales: `verify`, `strict-torch` y
`candidate-readiness`. Sólo las acepta si GitHub indica que finalizaron
con éxito y fueron emitidas por GitHub Actions (ID 15368) para el mismo
commit. Rechaza faltantes, duplicados, errores y emisores extraños.

Además consulta la rama candidata y los rulesets vigentes, preservando
la diferencia entre un check del **PR histórico** y la aprobación de un
**nuevo commit de publicación**. Incluso un ruleset que cumpla el contrato
no implica identidad de despliegue, environment protegido, aprobación
independiente o permiso para operar fondos.

La salida siempre mantiene `deployment_enabled=false`,
`release_authorized=false`, `real_bank_payment=false`.
La prueba no limpia las referencias históricas R027 ni acredita a Pey.
