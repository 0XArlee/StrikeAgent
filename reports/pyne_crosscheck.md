# Verificación cruzada con PyneCore (2026-10-19)

Sustituto del export de TradingView (requiere plan de pago). `verify_pyne/smartflow_pyne*.py` es una **re-traducción
independiente** del Pine original (L72-168, entradas por defecto) a la sintaxis Pyne, ejecutada en local con PyneCore
(Apache-2.0, commit 9360388, runtime validado contra TradingView en 1.000 scripts publicados). Nada se sube a ningún
servicio (`.pine` → PyneSys API no se usa). Comparación barra a barra con `smartflow/core`: `verify_pyne/compare.py`.

| Gráfico | Velas | Señales PyneCore / motor | Signal | HTF trend | EMA trend | Rel. volume | Money flow | Fast/Slow EMA |
|---|---|---|---|---|---|---|---|---|
| **BTCUSDT 4h, sesgo 1D** (config. del agente) | 6.000 (2024-01 → 2026-10) | **123 / 123** | **0** | **0** | 0 | 0 | 0 | 0 / 0 |
| BTCUSDT 1h, sesgo 4h, modo "closed" | 11.997 (2025-06 → 2026-10) | **268 / 268** | **0** | 18 (*) | 0 | 0 | 0 | 0 / 0 |

Tolerancias: enteros exactos; flotantes ≤ 1e-9 relativo (money flow 1e-7). Coincidencia desde la primera vela, sin
calentamiento.

(*) Diferencias de **PyneCore**, no del motor: con `lookahead_on` (la forma exacta del script, `structure()[1]`)
PyneCore aborta ("developing batch … diverged"), así que se usó `lookahead_off` + `structure()`. En ese modo PyneCore
trata de forma distinta las velas HTF que cierran a medianoche UTC: en 4h/1D entrega la tendencia del día anterior
también en la última vela del día (= semántica del script, de ahí IDENTICAL), y en 1h/4h, en la vela de 4h de las
20:00, adelanta la tendencia que solo se conoce al cierre de las 00:00 (lookahead). El motor sigue la semántica
documentada del script en todos los casos (tendencia de la vela HTF anterior a la que contiene la vela del gráfico).

Conclusión: la traducción reproduce el indicador en todas sus series y señales; la única pieza no contrastable fuera de
TradingView es la alineación HTF en la última vela de cada periodo, que sigue la regla documentada de Pine
(`expr[1]` + `lookahead_on`) y está cubierta por `tests/test_engine.py::test_htf_bias_uses_previous_closed_htf_bar`.
Para el contraste definitivo: export de TradingView (prueba gratuita de un plan de pago) → `smartflow verify-tv`.
