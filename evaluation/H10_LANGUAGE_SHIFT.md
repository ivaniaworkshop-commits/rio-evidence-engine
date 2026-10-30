# H10 — redacciones nuevas fuera de las cuatro gramáticas H09

**Tipo:** diagnóstico nuevo redactado por el proyecto; NO datos externos independientes. Se generan 40 casos positivos (8 familias de redacción × 5 variantes numéricas) y 12 casos negativos de duración ausente, contradicción, dependencia ambigua e instrucciones ajenas. Etiquetas de grafos creadas explícitamente, contrastadas con canonical(), no deducidas de las salidas. Sin solapamiento textual exacto con train/dev/evaluation; esto no prueba ausencia de contaminación semántica.

Ejecutar `python scripts/evaluate_language_shift.py` para comparar los dos extractores en los mismos 52 casos: exactitud completa, abstención, familias y latencia por ejecución. Los resultados de CI son la única evidencia nueva de desempeño; no presumir resultados. Dado que los ejemplos están publicados, jamás podrán usarse como holdout externo.

**Hallazgo de auditoría:** H08 comparaba contra graph_copy, no contra H09. Se corrige a extended_graph y se añaden pruebas para impedir referencia obsoleta. La ejecución es desde el worktree actual, sin atestación criptográfica del commit declarado. Los outputs y latencias proporcionados siguen sin autenticar y candidate_promoted=false permanece obligatorio.

Un corpus realmente externo, con recogida independiente y etiquetas adjudicadas, sigue bloqueado en H08 issue #8. No hay evidencia de mejora neuronal ni datos humanos autenticados.
