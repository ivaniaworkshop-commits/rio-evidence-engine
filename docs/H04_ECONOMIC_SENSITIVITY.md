# H04 · Sensibilidad económica de Mercado Abierto

**Estado:** implementación determinista de análisis de supuestos; **no** es evidencia de rentabilidad real, ventas, factibilidad comercial, ni validación bancaria. Corresponde únicamente al delta **H04** del [backlog #2](https://github.com/ivaniaworkshop-commits/rio-evidence-engine/issues/2). No interpreta sus 16 deltas como completados ni modifica requisitos FRONTIER.

## Ejecutar, sin dependencias externas

Guarda el ejemplo siguiente en `escenario.json`, desde la raíz del repositorio:

```json
{
  "scenario_id": "owner-relayed-2026-10-30",
  "baseline": {
    "ltv_mxn": "606",
    "cac_mxn": "1000",
    "purchase_mxn": "1115",
    "gross_savings_mxn": "46.63"
  },
  "scenarios": [
    {"name": "sin_cambios", "ltv_multiplier": "1", "cac_multiplier": "1", "incremental_cost_mxn": "0"},
    {"name": "ltv_x_1_650", "ltv_multiplier": "1.650", "cac_multiplier": "1", "incremental_cost_mxn": "0"},
    {"name": "ltv_x_1_650166", "ltv_multiplier": "1.650166", "cac_multiplier": "1", "incremental_cost_mxn": "50"},
    {"name": "cac_x_0_606", "ltv_multiplier": "1", "cac_multiplier": "0.606", "incremental_cost_mxn": "0"}
  ]
}
```

```sh
python analysis/h04_economic_sensitivity.py escenario.json
python -m unittest discover -s tests -p 'test_h04_economic_sensitivity.py' -v
```

**Tipos:** las cantidades monetarias y los multiplicadores son cadenas decimales no negativas (máximo 12 dígitos enteros y 6 decimales). Se rechazan floats JSON, claves duplicadas, números no finitos, identificadores inválidos, campos extra y entradas mayores de 65,536 bytes. El campo `cac_multiplier` debe ser mayor que cero; se evalúan entre 1 y 30 escenarios independientes. No hay red, claves ni persistencia.

## Resultado verificable con los supuestos del issue

Las cifras históricas del issue #2 implican `LTV/CAC = 0.606`. Para alcanzar **exactamente** la razón 1 mediante **un solo cambio**:

- Multiplicar LTV por **1000/606 = 1.65016501650165…** (incremento de **65.01650165…%**), manteniendo CAC.
- Reducir CAC en **39.4%** (factor **0.606**), manteniendo LTV.
- Con ahorro bruto MXN 46.63 y compra MXN 1115: **4.182062780269…%** antes de costos adicionales.

**Corrección de precisión:** el multiplicador redondeado `1.650×` señalado en el backlog no supera la barrera: `606 × 1.650 = 999.9`, aún por debajo de CAC 1000. El programa presenta el umbral redondeado a 12 decimales, pero todas las decisiones `meets_ltv_cac_one_gate` se calculan **sin redondear los operandos**. Por eso `1.650165×` falla y `1.650166×` pasa.

La salida `savings_less_incremental_cost_mxn` solamente resta un costo adicional **por la misma operación** al ahorro bruto declarado. **No** se llama beneficio neto, margen, ganancia ni resultado de empresa. El ratio LTV/CAC tampoco acredita retorno causal ni caja positiva.

## Procedencia y límites

Fuente: cifras y estados del backlog #2, registradas allí el 30 de octubre de 2026. El ejemplo de 606 y 1000 MXN es una **normalización aritmética ilustrativa** de la razón 0.606; no confirma valores reales individuales de LTV y CAC. El ahorro 46.63/1115 es un dato transmitido por el propietario, no una extracción de transacciones reales.

No se infieren mercados, flujos de caja, mezcla de clientes, comisiones de cobro, transporte, devoluciones, impagos, impuestos ni crecimiento. El resultado anterior de año 6 de -92.443 M MXN y la variante -53.930 M MXN describen **escenarios históricos del issue**, sin causalidad demostrada ni nuevos modelos de año 6 en este delta.

**Criterio local de aceptación H04:** código reproducible, pruebas positivas/adversariales, cálculo exacto de puertas de razón, readback de la rama del PR y evidencia de versión. El issue #2 se mantiene abierto para los demás deltas y dependencias. GitHub Actions no debe reintentarse mientras la cuota esté bloqueada; una prueba local PASS no es CI remoto PASS.
