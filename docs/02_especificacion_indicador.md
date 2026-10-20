# 02 · Especificación funcional de Smart Flow Signals [EdgeCraft]

Fuente: `SmartFlowSignals.txt` (Pine Script v6, 396 líneas, SHA-256 `8e493e64…0b768d`, v15 2026-09-28). Las
referencias `Lnn` son líneas de ese archivo. Implementación independiente: `src/smartflow/core/` (motor
`engine.py`, sesgo `htf.py`, primitivas `pine.py`, modelo de operaciones de referencia `reference_trades.py`).

## 1. Parámetros que afectan a señales u operaciones (L27-54)

| Input | Defecto | Rango | Uso |
|---|---|---|---|
| `lookN` | 20 | 5-200 | ruptura: el cierre supera el máximo/mínimo de las N velas **anteriores** |
| `rangeMin` | 1.0 | ≥0.3 | rango de la vela ≥ k·ATR(14) |
| `bodyMin` | 0.6 | 0.3-0.95 | cuerpo ≥ fracción del rango |
| `volMin` | 1.5 | ≥0 (0 = off) | volumen ≥ k·SMA(vol,20) **incluida la vela actual** |
| `rangeFilt` / `rangeMax` | off / 12 | 4-40 | descarta señales si el rango de las 100 velas previas > 12 ATR |
| `biasSrc` | HTF structure | 4 opciones | dirección permitida |
| `htfIn` | "" (auto) | — | auto: ≤15m→1h, 30m-1h→4h, 2h-4h→D, D→W |
| `htfSwing` | 5 | 2-20 | fuerza de pivote en el HTF |
| `emaFastN`/`emaSlowN` | 100/200 | — | nube EMA; la lenta es la fuente "Slow EMA" |
| `emaFilt`, `flowFilt` | off | — | filtros opcionales (marcan señal descartada) |
| `stopAtr` | 1.5 | ≥0.3 | stop = entrada ∓ 1.5·ATR; **1R** = esa distancia |
| `exitMode` | Trailing channel | 3 opciones | canal / cruce money-flow / lo primero |
| `chanN` | 10 | 3-100 | canal de salida |
| `tpR` | 0 (sin TP) | ≥0 | objetivo en R |
| `maxOpen` | 300 | 10-2000 | velas máximas en operación |
| `feePct` | 0.10 | ≥0 | coste ida y vuelta en % (solo para el panel) |
| `keepN` | 80 | 5-200 | dibujos conservados **y** operaciones seguidas (ver hallazgo H7) |

## 2. Cálculos por vela (orden de evaluación del script)

1. `atr = ta.atr(14)` (L72): RMA de Wilder del True Range, sembrada con SMA de 14; la primera vela usa high-low.
2. **Sesgo HTF** (L74-101): en las velas del HTF, `ta.pivothigh(high,5,5)` / `ta.pivotlow(low,5,5)` guardan el último
   swing confirmado (5 velas HTF de retraso); un cierre HTF por encima del último swing alto pone `trd=+1` y olvida
   ese alto; por debajo del último bajo, `trd=-1`. El valor es persistente. Se lee con
   `request.security(..., structure()[1], lookahead_on)` ⇒ **cada vela del gráfico ve el `trd` al cierre de la vela HTF
   anterior a la que la contiene**. Sin lookahead.
3. `hiN = highest(high,20)[1]`, `loN = lowest(low,20)[1]` (L105-106): 20 velas previas, sin la actual.
4. **Volumen** (L109-119): volumen propio; si el símbolo nunca tuvo volumen, el de `BINANCE:<base>USDT`; si tampoco
   existe, `vol = na` ⇒ el filtro de volumen **se desactiva** (`volOk` verdadero) y el money flow queda en `na`.
   `hasVol` es pegajoso (basta una vela con volumen > 0).
5. **EMAs** (L122-124): `emaTrend` = +1/-1/0.
6. **Money flow compuesto** (L125-138), sobre `hlc3`:
   - MFI(14) con `>=` como flujo positivo (el MFI estándar excluye los iguales) y `mfi = 100` si el negativo es 0;
   - CMF(21) = SMA(CLV·vol,21)/SMA(vol,21);
   - CCI-like: `(hlc3-EMA10)/(0.015·EMA10(|hlc3-EMA10|))·(1+0.5·ln(vol/SMA21+1))`;
   - `flow = 0.5·EMA21(cci) + 0.3·100·CMF + 0.2·1.2·(MFI-50)`.
7. **Desplazamiento y ruptura** (L146-152): `disp = rng ≥ 1·ATR ∧ body ≥ 0.6·rng`; compra si `disp ∧ close>open ∧
   close>hiN`; venta simétrica.
8. **Régimen** (L154-155): `range100 = (highest(high,100)[1]-lowest(low,100)[1])/ATR`.
9. **Sesgo** (L157-162): estructura HTF (defecto), EMA lenta (`close` vs EMA200), cualquiera, o ninguno.
10. **Señal** (L163): `sigRaw = isconfirmed ∧ volOk ? (compra∧sesgoArriba ? 1 : venta∧sesgoAbajo ? -1 : 0) : 0`.
11. **Descartes opcionales** (L165-168), en este orden: rango amplio → contra nube EMA → contra money flow.

## 3. Gestión de operaciones (L171-325), en cada vela cerrada

1. Para cada operación abierta de una vela anterior: **stop** intrabar (`low ≤ sl`) → **objetivo** intrabar →
   **salida** (canal: cierre por debajo del mínimo de las 10 velas previas, solo desde la 2ª vela tras la señal;
   o cruce del money flow por cero; o lo primero) → **límite de velas**. Precio de salida: el stop exacto, el
   objetivo exacto o el cierre.
2. Nueva señal ⇒ **nueva operación** (entrada = cierre, stop = cierre ∓ 1.5·ATR), aunque ya haya otras abiertas.
3. `R = (salida-entrada)·dir/riesgo − feePct/100·entrada/riesgo`. El panel suma operaciones **cerradas**: número,
   % ganadoras (R>0), R medio, profit factor (Σ R ganadoras / Σ |R perdedoras|).

## 4. Auditoría (punto 5 del prompt)

| # | Pregunta | Hallazgo | Tratamiento en el agente |
|---|---|---|---|
| H1 | ¿Señales solo con velas cerradas? | Sí: `barstate.isconfirmed` en señal y gestión. No repinta. | Igual: el motor solo recibe velas cerradas. |
| H2 | ¿HTF sin lookahead? | Sí: `[1]` + `lookahead_on` = última vela HTF cerrada **antes** de la HTF actual. Añade hasta 1 vela HTF de retraso extra en la última vela del gráfico de cada HTF. | Reproducido exactamente (`HtfBias.trend_for`); test dedicado. La variante "fresca" (sin ese retraso) se mide como experimento. |
| H3 | ¿Los pivotes retrasan? | Sí, 5 velas HTF (20 h en 4h, 5 días en D). Es confirmación legítima, no lookahead. | Igual. Regla de empates medida en TradingView (PyneCore): izquierda `>=`, derecha `>` estricto. |
| H4 | Volumen ausente | Desactiva el filtro (pasa todo) y anula el money flow. Coherente, pero cambia la estrategia en silencio. | El feed de señal siempre tiene volumen (Binance spot). Sin volumen: nota explícita en cada barra. |
| H5 | ¿Volumen externo comparable con Strike? | **No**: Strike negocia ~1e-4 del volumen de Binance spot y tiene muchas velas de volumen 0 rellenadas (medido 2026-10-19). | La señal usa Binance spot **etiquetado** como tal, que es exactamente la fuente de respaldo que el propio script usa. Nunca se presenta como volumen de Strike. |
| H6 | Señales con operación abierta | El script abre operaciones **solapadas e incluso opuestas** a la vez. En Strike la posición es **neta por mercado** (`/v2/positions` devuelve un tamaño con signo): no ejecutable tal cual. | Política `single` (una posición por mercado, señales ignoradas mientras hay una abierta y registradas como descartadas); `reverse` medida: idéntica (el sesgo casi nunca da opuestas). |
| H7 | `keepN` | Al superar 80 operaciones se elimina la más antigua **aunque siga abierta** y nunca se contabiliza. | Reproducido en el modo referencia; en 2022-2026 no ocurre ninguna vez (`dropped_open = 0`). |
| H8 | Prioridad stop/objetivo/salida | Stop antes que objetivo en la misma vela: conservador y realista. Stop relleno exactamente en el nivel: optimista ante gaps. | Simulador: stop al nivel −5 bps, o a la apertura si hay gap. |
| H9 | ¿La comisión es ida y vuelta? | `feePct` se aplica sobre el **precio de entrada** solamente; el coste real es fee×(entrada+salida). Diferencia pequeña, a favor de las ganadoras. | Simulador: fee por fill sobre el nocional de cada fill (+ builder fee). |
| H10 | R neto | Correcto en dirección y signo. | R realista sobre el riesgo efectivo `|fill − stop|`. |
| H11 | Estadísticas del panel | Correctas para lo que miden (todas las señales, solapadas). | Reproducidas (`Record`). |
| H12 | Cierre vs precio ejecutable | El script entra al cierre exacto; en vivo la orden llega segundos después en otro mercado (Strike) con su propio libro. | Entrada a la apertura siguiente + slippage; en vivo, IOC con precio protector. Basis Strike–Binance medido (mediana 7-12 bps). |
| H13 | Primera vela tras la señal | La salida por canal no puede disparar en la vela siguiente a la señal (`bar_index > t.bar + 1`), el cruce de money flow sí. | Igual (`core/exits.py`, compartido por backtest y agente). |

## 5. Verificación de las cifras declaradas en los comentarios (L9-10, tooltips L31-52)

El script declara, para Binance BTC/ETH/SOL 2022-2026: 1h ≈ +0,23 R/señal (≈1.300 señales), 4h ≈ +0,63 R (≈293).
Con la lógica del propio script (modo referencia, comisión 0,10 %):

- Contando **todas** las señales (como el panel) en 2022-01 → 2026-09-28: 1h 2.592 señales a +0,16 R; 4h 634 a +0,67 R.
- Con **una posición a la vez por mercado** en 2022-01 → 2026-01: el **número** coincide (±2 %) en las 8
  configuraciones de sesgo citadas (p. ej. 1.323 vs 1.300; 291 vs 293; 2.219 vs 2.210), pero el R es menor: 1h
  +0,12 R (bruto +0,20), 4h +0,52 R (bruto +0,55).
- Una variante con **lookahead** en el HTF reproduce el R declarado (+0,225 / +0,631) pero no el número de señales.

**Conclusión:** las cifras de los comentarios **no se pueden reproducir exactamente** con la lógica publicada del
script; parecen proceder de un arnés de medición distinto. No se usan como evidencia. Las cifras válidas son las del
informe cuantitativo (`docs/05_informe_cuantitativo.md`). **Pregunta abierta para EdgeCraft:** ¿con qué herramienta,
periodo, regla de solapamiento y costes se midieron?

## 6. Verificación de la traducción

**Hecho (2026-10-19): verificación cruzada con PyneCore** (`reports/pyne_crosscheck.md`): en BTCUSDT 4h con sesgo
diario, motor y re-traducción independiente ejecutada en PyneCore son **idénticos en 6.000 velas y 123 señales**, en
todas las series; en 1h, 268/268 señales idénticas (diferencias solo de alineación HTF atribuibles a PyneCore).

### Contraste definitivo con TradingView (opcional, requiere plan de pago o su prueba gratuita)

Pendiente de un export real del gráfico (no se puede ejecutar Pine fuera de TradingView). Procedimiento:
TradingView → `BINANCE:BTCUSDT` 1h → añadir Smart Flow Signals con valores por defecto → menú del gráfico →
*Export chart data…* → formato de tiempo UNIX → guardar CSV → `smartflow verify-tv <csv> --tf 60`. Compara barra a
barra `Signal`, `HTF trend`, `EMA trend`, `Relative volume`, `Money flow`, `Fast/Slow EMA` (tras 1.500 velas de
calentamiento) y debe dar `IDENTICAL`. Repetir en 4h. Hasta entonces la fidelidad está verificada por inspección
línea a línea, semántica Pine medida (PyneCore) y tests, **no** contra TradingView.

Diferencias conocidas solo en el calentamiento (primeras ~250 velas del histórico cargado): inicialización de EMAs con
entradas `na` y comparaciones con `na` (en Pine v6 son falsas).
