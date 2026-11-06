# RÍO R030 — Backport funcional limpio del PR #35

## Genealogía y operación
El PR #35 se apoya en una referencia histórica afectada. R030 **no fusiona ni aplica cherry-pick** de sus commits. Recupera sólo el cambio funcional y sus pruebas como código nuevo sobre la rama saneada del PR #36.

## Cuatro denegaciones endurecidas
El paso `release-authority` del workflow ahora termina con `exit 2` ante:
1. `UNKNOWN_API_UNAVAILABLE`
2. `BLOCKED_NO_ACTIVE_RULESETS`
3. `UNKNOWN_RULESET_READ`
4. `BLOCKED_POLICY_CHECK`

El camino de autorización positiva permanece intacto. Las diez regresiones ejecutan el script real extraído del workflow con `gh` simulado y condiciones temporales: cinco originales, cinco adversariales (rama diferente, ruleset inactivo, bypass, aprobación ausente y JSON inválido).

## Autoridad explícita
Estos ensayos acreditan **comportamiento del shell**, no una aplicación efectiva de reglas en GitHub. La rama de producción heredada `deploy/primer-cobro` está en cuarentena (`deploy: if: false`); el workflow de esta rama limpia no activa la publicación y la protección de `main` no basta para la rama release.

El PR #35 conserva historia afectada hasta que se retire mediante administración; los archivos de prueba se reintroducen en un commit con otro padre Git. Nadie debe interpretar el nuevo commit como una eliminación de cachés, clones, forks o referencias.

No se añaden datos de titular, CLABE, secretos, pagos reales ni transferencias. Producción pública R016 inalterada. Android físico no observado.

`PROGRAMMED != CI_PASS != RUNTIME_ACTIVE`. Confirmar los tres estados de forma independiente.
