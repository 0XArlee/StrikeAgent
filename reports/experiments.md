# Registro de experimentos — Smart Flow Agent

Generado por `smartflow research` en 2026-10-19 01:35 UTC. Datos: Binance spot (señal y precios) + funding de perpetuos Binance como proxy; ventana completa 2022-01-01 → 2026-10-18. Modelo base: taker 5bp + builder 0bp per fill, slip 2/5bp, funding on; entry next_open, exits next_open, gap-aware stops True, policy single. Riesgo por operación para métricas de equity: 0,5 %. R/op = R neto por operación. IC95 = bootstrap del R medio.


## E1 — Del modelo de referencia a la ejecución realista en Strike

**Hipótesis:** Las cifras del script (entrada al cierre, stop exacto, operaciones solapadas) sobrestiman lo que una cuenta de Strike (posición neta por mercado) puede capturar.

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R |
|---|---|---|---|---|---|---|---|---|
| 60 A referencia (solape, fill al cierre, taker 5bp) | 2617 | +0.153 | [+0.05, +0.26] | 2.9 | 29% | 1.22 | +401 | 98 |
| 60 B + una posición por mercado (netting) | 1566 | +0.183 | [+0.05, +0.33] | 2.6 | 29% | 1.27 | +286 | 57 |
| 60 C + entrada/salidas a la apertura siguiente | 1566 | +0.182 | [+0.05, +0.32] | 2.6 | 29% | 1.26 | +284 | 57 |
| 60 D + stops con gap | 1566 | +0.182 | [+0.05, +0.32] | 2.6 | 29% | 1.26 | +284 | 57 |
| 60 E + slippage 2bp mercado / 5bp stop | 1566 | +0.129 | [-0.00, +0.27] | 1.9 | 29% | 1.18 | +202 | 64 |
| 60 F + funding (proxy perp Binance) | 1566 | +0.121 | [-0.01, +0.26] | 1.8 | 29% | 1.17 | +190 | 66 |

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R |
|---|---|---|---|---|---|---|---|---|
| 240 A referencia (solape, fill al cierre, taker 5bp) | 635 | +0.664 | [+0.40, +0.96] | 4.6 | 31% | 2.01 | +422 | 50 |
| 240 B + una posición por mercado (netting) | 350 | +0.605 | [+0.24, +1.03] | 3.0 | 29% | 1.91 | +212 | 28 |
| 240 C + entrada/salidas a la apertura siguiente | 350 | +0.605 | [+0.23, +1.01] | 3.0 | 29% | 1.91 | +212 | 28 |
| 240 D + stops con gap | 350 | +0.605 | [+0.23, +1.01] | 3.0 | 29% | 1.91 | +212 | 28 |
| 240 E + slippage 2bp mercado / 5bp stop | 350 | +0.573 | [+0.21, +0.98] | 2.9 | 29% | 1.84 | +201 | 29 |
| 240 F + funding (proxy perp Binance) | 350 | +0.539 | [+0.17, +0.94] | 2.8 | 29% | 1.79 | +188 | 29 |

**Veredicto:** Ver tablas: el modelo F es la base de todas las comparaciones siguientes.


## E2 — Builder fee: punto de equilibrio

**Hipótesis:** Una builder fee por fill (entrada y salida) del 1 % (100 bps) destruye la ventaja; existe un nivel compatible con una expectativa neta positiva para el usuario.

| config | n | R/op neto | IC95 | coste builder R/op | CAGR (0,5% riesgo/op) | maxDD equity |
|---|---|---|---|---|---|---|
| 60 0 bp | 1566 | +0.121 | [-0.01, +0.26] | 0.000 | 18.4% | 28.4% |
| 60 1 bp | 1566 | +0.105 | [-0.03, +0.24] | 0.017 | 15.2% | 29.5% |
| 60 2 bp | 1566 | +0.088 | [-0.04, +0.23] | 0.033 | 12.1% | 30.5% |
| 60 5 bp | 1566 | +0.038 | [-0.09, +0.18] | 0.083 | 3.3% | 33.5% |
| 60 10 bp | 1566 | -0.045 | [-0.18, +0.09] | 0.167 | -9.8% | 55.7% |
| 60 15 bp | 1566 | -0.129 | [-0.26, +0.01] | 0.250 | -21.3% | 74.7% |
| 60 20 bp | 1566 | -0.212 | [-0.34, -0.07] | 0.333 | -31.3% | 86.3% |
| 60 30 bp | 1566 | -0.378 | [-0.51, -0.23] | 0.500 | -47.7% | 96.1% |
| 60 50 bp | 1566 | -0.712 | [-0.84, -0.57] | 0.833 | -69.7% | 99.7% |
| 60 75 bp | 1566 | -1.128 | [-1.26, -0.98] | 1.249 | -84.7% | 100.0% |
| 60 100 bp | 1566 | -1.544 | [-1.68, -1.39] | 1.666 | -92.3% | 100.0% |

Punto de equilibrio 60: ≈ 7 bps por fill.

| config | n | R/op neto | IC95 | coste builder R/op | CAGR (0,5% riesgo/op) | maxDD equity |
|---|---|---|---|---|---|---|
| 240 0 bp | 350 | +0.539 | [+0.17, +0.94] | 0.000 | 20.3% | 13.6% |
| 240 1 bp | 350 | +0.531 | [+0.17, +0.93] | 0.008 | 20.0% | 13.7% |
| 240 2 bp | 350 | +0.523 | [+0.16, +0.92] | 0.016 | 19.6% | 13.9% |
| 240 5 bp | 350 | +0.499 | [+0.13, +0.89] | 0.039 | 18.6% | 14.3% |
| 240 10 bp | 350 | +0.460 | [+0.10, +0.85] | 0.078 | 16.9% | 15.0% |
| 240 15 bp | 350 | +0.421 | [+0.06, +0.81] | 0.118 | 15.3% | 15.8% |
| 240 20 bp | 350 | +0.382 | [+0.02, +0.78] | 0.157 | 13.7% | 16.5% |
| 240 30 bp | 350 | +0.304 | [-0.06, +0.70] | 0.235 | 10.5% | 17.9% |
| 240 50 bp | 350 | +0.147 | [-0.21, +0.53] | 0.392 | 4.3% | 23.1% |
| 240 75 bp | 350 | -0.049 | [-0.40, +0.34] | 0.588 | -2.8% | 34.8% |
| 240 100 bp | 350 | -0.245 | [-0.60, +0.14] | 0.783 | -9.5% | 50.1% |

Punto de equilibrio 240: ≈ 69 bps por fill.

**Veredicto:** Ver tablas y puntos de equilibrio; interpretación en docs/05_informe_cuantitativo.md.


## E3 — Estabilidad temporal: desarrollo / validación / test

**Hipótesis:** Si la ventaja es real debe ser positiva en los tres tramos fijados de antemano.

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R | por activo |
|---|---|---|---|---|---|---|---|---|---|
| 60 dev | 616 | +0.059 | [-0.13, +0.26] | 0.6 | 27% | 1.08 | +37 | 48 | BTC +0.08 (206)  ETH +0.05 (198)  SOL +0.05 (212) |
| 60 val | 537 | +0.089 | [-0.11, +0.29] | 0.9 | 30% | 1.13 | +48 | 66 | BTC +0.03 (189)  ETH +0.09 (180)  SOL +0.16 (168) |
| 60 test | 413 | +0.255 | [-0.04, +0.59] | 1.5 | 29% | 1.35 | +105 | 41 | BTC +0.26 (138)  ETH +0.31 (130)  SOL +0.20 (145) |
| 60 strike | 168 | +0.462 | [-0.13, +1.23] | 1.3 | 30% | 1.62 | +78 | 27 | BTC +0.40 (56)  ETH +0.52 (52)  SOL +0.47 (60) |
| 240 dev | 141 | +0.587 | [+0.02, +1.17] | 1.9 | 30% | 1.88 | +83 | 29 | BTC +1.33 (39)  ETH +0.38 (47)  SOL +0.24 (55) |
| 240 val | 113 | +0.358 | [-0.17, +0.99] | 1.2 | 29% | 1.52 | +40 | 27 | BTC +0.40 (39)  ETH +0.60 (42)  SOL -0.00 (32) |
| 240 test | 96 | +0.680 | [-0.07, +1.59] | 1.6 | 28% | 1.96 | +65 | 22 | BTC +0.93 (30)  ETH +1.10 (35)  SOL -0.04 (31) |
| 240 strike | 47 | +0.784 | [-0.53, +2.46] | 1.0 | 21% | 1.97 | +37 | 18 | BTC +1.54 (14)  ETH +1.31 (18)  SOL -0.55 (15) |

**Veredicto:** Ver tabla; interpretación en docs/05_informe_cuantitativo.md.


## E4 — Por año y por régimen

**Hipótesis:** La ventaja no depende de un único año ni de un único régimen de mercado.

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R |
|---|---|---|---|---|---|---|---|---|
| 60 2022 | 320 | -0.101 | n/a | -0.8 | 26% | 0.86 | -32 | 41 |
| 60 2023 | 296 | +0.233 | n/a | 1.4 | 29% | 1.31 | +69 | 48 |
| 60 2024 | 375 | +0.042 | n/a | 0.4 | 31% | 1.06 | +16 | 47 |
| 60 2025 | 333 | +0.086 | n/a | 0.7 | 28% | 1.12 | +29 | 31 |
| 60 2026 | 242 | +0.450 | n/a | 1.7 | 30% | 1.61 | +109 | 27 |
| 60 a favor de la tendencia diaria (SMA200D) | 864 | +0.066 | n/a | 0.8 | 28% | 1.09 | +57 | 40 |
| 60 contra la tendencia diaria | 702 | +0.189 | n/a | 1.6 | 29% | 1.27 | +133 | 45 |
| 60 volatilidad baja (ATR% tercio inferior) | 522 | +0.359 | n/a | 2.2 | 29% | 1.45 | +187 | 41 |
| 60 volatilidad media | 522 | +0.051 | n/a | 0.5 | 29% | 1.07 | +27 | 62 |
| 60 volatilidad alta | 522 | -0.046 | n/a | -0.5 | 29% | 0.93 | -24 | 54 |

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R |
|---|---|---|---|---|---|---|---|---|
| 240 2022 | 67 | +0.346 | n/a | 1.2 | 34% | 1.59 | +23 | 13 |
| 240 2023 | 74 | +0.805 | n/a | 1.6 | 26% | 2.10 | +60 | 29 |
| 240 2024 | 70 | +0.441 | n/a | 1.0 | 29% | 1.62 | +31 | 27 |
| 240 2025 | 80 | +0.214 | n/a | 0.9 | 31% | 1.34 | +17 | 11 |
| 240 2026 | 59 | +0.978 | n/a | 1.5 | 25% | 2.27 | +58 | 22 |
| 240 a favor de la tendencia diaria (SMA200D) | 226 | +0.394 | n/a | 1.9 | 28% | 1.57 | +89 | 30 |
| 240 contra la tendencia diaria | 124 | +0.802 | n/a | 2.0 | 31% | 2.20 | +99 | 23 |
| 240 volatilidad baja (ATR% tercio inferior) | 116 | +1.111 | n/a | 2.3 | 29% | 2.54 | +129 | 15 |
| 240 volatilidad media | 116 | +0.622 | n/a | 2.1 | 29% | 1.92 | +72 | 14 |
| 240 volatilidad alta | 118 | -0.106 | n/a | -0.7 | 29% | 0.84 | -12 | 21 |

**Veredicto:** Ver tablas (los terciles de volatilidad usan la muestra completa: es descriptivo, no una regla).


## E5 — Activos fuera de muestra

**Hipótesis:** El autor midió BTC/ETH/SOL; si la lógica generaliza, debe funcionar en activos que no se usaron para diseñarla (XRP, BNB, ADA, NEAR, ZEC; todos listados en Strike).

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R | por activo |
|---|---|---|---|---|---|---|---|---|---|
| 60 5 activos OOS | 2418 | -0.029 | [-0.12, +0.07] | -0.6 | 26% | 0.96 | -71 | 232 | XRP -0.06 (450)  BNB +0.00 (500)  ADA -0.02 (519)  NEAR +0.03 (506)  ZEC -0.11 (443) |
| 240 5 activos OOS | 558 | +0.175 | [-0.05, +0.41] | 1.4 | 26% | 1.24 | +98 | 48 | XRP +0.21 (105)  BNB +0.17 (116)  ADA +0.09 (125)  NEAR +0.16 (107)  ZEC +0.26 (105) |

**Veredicto:** Ver tabla.


## E6 — Otros timeframes

**Hipótesis:** El script dice que por debajo de 1h las comisiones se comen la ventaja; 2h y 1D deberían comportarse entre 1h y 4h si la lógica es robusta.

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R | comisiones R/op |
|---|---|---|---|---|---|---|---|---|---|
| 30m | 2953 | -0.051 | [-0.15, +0.05] | -1.1 | 25% | 0.94 | -151 | 236 | 0.124 |
| 2h | 709 | +0.333 | [+0.11, +0.60] | 2.6 | 30% | 1.48 | +236 | 50 | 0.060 |
| 1h | 1566 | +0.121 | [-0.01, +0.26] | 1.8 | 29% | 1.17 | +190 | 66 | 0.083 |
| 4h | 350 | +0.539 | [+0.17, +0.94] | 2.8 | 29% | 1.79 | +188 | 29 | 0.039 |
| 1D | 48 | +0.600 | [-0.27, +2.06] | 1.0 | 35% | 2.04 | +29 | 12 | 0.015 |

**Veredicto:** Ver tabla.


## E7 — Sensibilidad de parámetros (uno a uno alrededor de los valores por defecto)

**Hipótesis:** Una ventaja robusta forma una meseta: valores vecinos dan resultados parecidos. Un pico aislado en el valor por defecto sería señal de sobreajuste.

| config | n | R/op total | R total | R/op dev | R/op test |
|---|---|---|---|---|---|
| 60 look_n=10 | 1826 | +0.110 | +202 | +0.074 | +0.200 |
| 60 look_n=15 | 1696 | +0.102 | +173 | +0.060 | +0.222 |
| 60 look_n=20 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 look_n=30 | 1356 | +0.158 | +214 | +0.111 | +0.267 |
| 60 look_n=40 | 1271 | +0.155 | +197 | +0.148 | +0.234 |
| 60 range_min=0.7 | 1579 | +0.114 | +181 | +0.056 | +0.241 |
| 60 range_min=0.85 | 1574 | +0.117 | +184 | +0.057 | +0.244 |
| 60 range_min=1.0 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 range_min=1.2 | 1531 | +0.129 | +197 | +0.058 | +0.280 |
| 60 range_min=1.5 | 1419 | +0.133 | +189 | +0.072 | +0.228 |
| 60 body_min=0.5 | 1782 | +0.085 | +152 | +0.025 | +0.150 |
| 60 body_min=0.6 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 body_min=0.7 | 1240 | +0.139 | +173 | +0.044 | +0.314 |
| 60 vol_min=0.0 | 1812 | +0.083 | +150 | +0.037 | +0.214 |
| 60 vol_min=1.0 | 1761 | +0.085 | +149 | +0.049 | +0.215 |
| 60 vol_min=1.5 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 vol_min=2.0 | 1294 | +0.160 | +207 | +0.095 | +0.262 |
| 60 vol_min=2.5 | 993 | +0.205 | +204 | +0.156 | +0.314 |
| 60 stop_atr=1.0 | 1714 | +0.092 | +158 | +0.033 | +0.168 |
| 60 stop_atr=1.25 | 1623 | +0.133 | +216 | +0.059 | +0.262 |
| 60 stop_atr=1.5 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 stop_atr=2.0 | 1485 | +0.101 | +149 | +0.049 | +0.171 |
| 60 stop_atr=2.5 | 1444 | +0.084 | +121 | +0.041 | +0.141 |
| 60 chan_n=5 | 1704 | +0.062 | +105 | -0.027 | +0.187 |
| 60 chan_n=7 | 1627 | +0.103 | +168 | +0.035 | +0.277 |
| 60 chan_n=10 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 chan_n=15 | 1480 | +0.110 | +163 | +0.082 | +0.207 |
| 60 chan_n=20 | 1414 | +0.126 | +179 | +0.076 | +0.256 |
| 60 chan_n=30 | 1316 | +0.125 | +165 | +0.098 | +0.272 |
| 60 htf_swing=3 | 1623 | +0.098 | +160 | +0.088 | +0.139 |
| 60 htf_swing=5 (def) | 1566 | +0.121 | +190 | +0.059 | +0.255 |
| 60 htf_swing=8 | 1538 | +0.132 | +203 | +0.092 | +0.256 |

| config | n | R/op total | R total | R/op dev | R/op test |
|---|---|---|---|---|---|
| 240 look_n=10 | 429 | +0.467 | +200 | +0.422 | +0.596 |
| 240 look_n=15 | 392 | +0.465 | +182 | +0.477 | +0.615 |
| 240 look_n=20 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 look_n=30 | 309 | +0.481 | +149 | +0.738 | +0.327 |
| 240 look_n=40 | 291 | +0.455 | +132 | +0.789 | +0.307 |
| 240 range_min=0.7 | 352 | +0.534 | +188 | +0.587 | +0.680 |
| 240 range_min=0.85 | 352 | +0.534 | +188 | +0.587 | +0.680 |
| 240 range_min=1.0 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 range_min=1.2 | 347 | +0.543 | +188 | +0.590 | +0.695 |
| 240 range_min=1.5 | 316 | +0.637 | +201 | +0.671 | +0.858 |
| 240 body_min=0.5 | 391 | +0.493 | +193 | +0.521 | +0.710 |
| 240 body_min=0.6 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 body_min=0.7 | 293 | +0.558 | +163 | +0.650 | +0.578 |
| 240 vol_min=0.0 | 424 | +0.390 | +165 | +0.434 | +0.457 |
| 240 vol_min=1.0 | 408 | +0.438 | +179 | +0.487 | +0.484 |
| 240 vol_min=1.5 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 vol_min=2.0 | 268 | +0.685 | +183 | +0.516 | +1.134 |
| 240 vol_min=2.5 | 189 | +0.625 | +118 | +0.536 | +1.174 |
| 240 stop_atr=1.0 | 368 | +0.847 | +312 | +1.006 | +0.846 |
| 240 stop_atr=1.25 | 354 | +0.718 | +254 | +0.739 | +0.897 |
| 240 stop_atr=1.5 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 stop_atr=2.0 | 335 | +0.406 | +136 | +0.430 | +0.665 |
| 240 stop_atr=2.5 | 329 | +0.285 | +94 | +0.314 | +0.492 |
| 240 chan_n=5 | 389 | +0.407 | +158 | +0.482 | +0.425 |
| 240 chan_n=7 | 363 | +0.547 | +199 | +0.646 | +0.634 |
| 240 chan_n=10 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 chan_n=15 | 337 | +0.678 | +229 | +0.867 | +0.551 |
| 240 chan_n=20 | 329 | +0.675 | +222 | +0.915 | +0.554 |
| 240 chan_n=30 | 307 | +0.701 | +215 | +0.982 | +0.500 |
| 240 htf_swing=3 | 367 | +0.474 | +174 | +0.628 | +0.519 |
| 240 htf_swing=5 (def) | 350 | +0.539 | +188 | +0.587 | +0.680 |
| 240 htf_swing=8 | 348 | +0.255 | +89 | +0.409 | +0.266 |

**Veredicto:** Ver tablas.


## E8 — Filtros opcionales, salidas y sesgo (modo experimental vs referencia)

**Hipótesis:** Cada opción del script se compara con la referencia en los tres tramos; solo se recomendaría una que mejore en desarrollo Y se mantenga en validación y test.

| config | n | R/op total | R total | dev | val | test |
|---|---|---|---|---|---|---|
| 60 referencia | 1566 | +0.121 | +190 | +0.059 | +0.089 | +0.255 |
| 60 filtro rango amplio | 1203 | +0.248 | +298 | +0.234 | +0.154 | +0.388 |
| 60 filtro nube EMA | 1218 | +0.133 | +162 | +0.056 | +0.086 | +0.301 |
| 60 filtro money flow | 1520 | +0.130 | +197 | +0.060 | +0.100 | +0.271 |
| 60 salida money-flow cross | 1562 | +0.092 | +144 | +0.033 | +0.046 | +0.239 |
| 60 salida lo primero | 1601 | +0.098 | +156 | +0.029 | +0.052 | +0.260 |
| 60 TP 2R | 2095 | -0.036 | -76 | -0.020 | -0.045 | -0.050 |
| 60 TP 4R | 1791 | +0.056 | +100 | +0.001 | +0.058 | +0.134 |
| 60 sesgo EMA lenta | 2250 | +0.105 | +237 | +0.023 | +0.094 | +0.243 |
| 60 sesgo cualquiera | 2285 | +0.116 | +265 | +0.032 | +0.116 | +0.243 |
| 60 sin sesgo | 2757 | +0.064 | +175 | +0.012 | +0.035 | +0.180 |

| config | n | R/op total | R total | dev | val | test |
|---|---|---|---|---|---|---|
| 240 referencia | 350 | +0.539 | +188 | +0.587 | +0.358 | +0.680 |
| 240 filtro rango amplio | 294 | +0.727 | +214 | +0.880 | +0.399 | +0.914 |
| 240 filtro nube EMA | 298 | +0.551 | +164 | +0.500 | +0.422 | +0.789 |
| 240 filtro money flow | 341 | +0.520 | +177 | +0.569 | +0.268 | +0.755 |
| 240 salida money-flow cross | 346 | +0.656 | +227 | +0.698 | +0.656 | +0.595 |
| 240 salida lo primero | 356 | +0.535 | +191 | +0.533 | +0.455 | +0.631 |
| 240 TP 2R | 516 | +0.090 | +47 | +0.151 | +0.032 | +0.072 |
| 240 TP 4R | 428 | +0.258 | +111 | +0.306 | +0.178 | +0.286 |
| 240 sesgo EMA lenta | 515 | +0.441 | +227 | +0.473 | +0.249 | +0.617 |
| 240 sesgo cualquiera | 520 | +0.445 | +231 | +0.490 | +0.268 | +0.583 |
| 240 sin sesgo | 644 | +0.310 | +199 | +0.300 | +0.188 | +0.462 |

**Veredicto:** Ver tablas.


## E9 — Walk-forward de la selección de variante

**Hipótesis:** Elegir cada 6 meses la mejor variante de los 18 meses anteriores ¿mejora fuera de muestra a quedarse siempre con la referencia? (si no, no se optimiza).

| fold | test desde | elegida (train 18m) | R/op test elegida | R/op test referencia |
|---|---|---|---|---|
| 60 fold 1 | 2023-07 | filtro rango amplio | +0.426 | +0.128 |
| 60 fold 2 | 2023-12 | filtro rango amplio | +0.207 | +0.243 |
| 60 fold 3 | 2024-06 | filtro rango amplio | -0.042 | -0.144 |
| 60 fold 4 | 2024-12 | filtro rango amplio | +0.315 | +0.191 |
| 60 fold 5 | 2025-06 | filtro rango amplio | +0.116 | -0.020 |
| 60 fold 6 | 2025-12 | filtro rango amplio | +0.270 | +0.362 |
| 60 fold 7 | 2026-06 | filtro rango amplio | +1.277 | +0.608 |

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R |
|---|---|---|---|---|---|---|---|---|
| 60 walk-forward | 854 | +0.275 | [+0.08, +0.48] | 2.7 | 33% | 1.42 | +235 | 37 |
| 60 referencia fija | 1099 | +0.154 | [-0.00, +0.33] | 1.8 | 29% | 1.22 | +170 | 67 |

| fold | test desde | elegida (train 18m) | R/op test elegida | R/op test referencia |
|---|---|---|---|---|
| 240 fold 1 | 2023-07 | filtro rango amplio | +1.499 | +1.196 |
| 240 fold 2 | 2023-12 | canal 20 | +1.105 | +0.434 |
| 240 fold 3 | 2024-06 | canal 20 | +0.472 | +0.448 |
| 240 fold 4 | 2024-12 | canal 20 | +0.025 | +0.223 |
| 240 fold 5 | 2025-06 | salida money-flow cross | +0.153 | +0.204 |
| 240 fold 6 | 2025-12 | filtro rango amplio | +0.701 | +0.584 |
| 240 fold 7 | 2026-06 | filtro rango amplio | +2.348 | +1.809 |

| config | n | R/op | IC95 | t | win | PF | R total | maxDD R |
|---|---|---|---|---|---|---|---|---|
| 240 walk-forward | 222 | +0.734 | [+0.20, +1.35] | 2.4 | 29% | 2.02 | +163 | 26 |
| 240 referencia fija | 245 | +0.607 | [+0.18, +1.10] | 2.5 | 30% | 1.88 | +149 | 27 |

**Veredicto:** Ver tablas.
