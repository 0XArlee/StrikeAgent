# Referencia inmutable

El indicador original `../SmartFlowSignals.txt` (Pine Script v6, © EdgeCraft, propietario) es la **especificación de
referencia** del motor. No se edita, no se mueve y no se publica.

| Archivo | SHA-256 (registrado 2026-10-19) |
|---|---|
| `SmartFlowSignals.txt` | `8e493e64196698b258f24a7bf2c01a2a7f27cafa8c8f159b6ce36c770e0b768d` |

`tests/test_reference_integrity.py` falla si el archivo cambia. Si EdgeCraft publica una versión nueva del indicador, se
añade como archivo nuevo (p. ej. `SmartFlowSignals_v16.txt`) con su propio hash y se vuelve a pasar la regresión.
