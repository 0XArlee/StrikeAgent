# Fase 2: chandelier y filtros de entrada (Smart Flow 4h, BTC/ETH/SOL)

Costes: taker 5bp + builder 20bp per fill, slip 2/5bp, funding on. Riesgo 0,5 % por operación. Una posición por mercado salvo la columna Pyramid.

| id | variante | ops | R/op | IC95 | acierto | PF | CAGR | caída máx. | dev | val | test | 5 activos OOS | Pyramid CAGR / caída |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref | Referencia | 350 | +0.382 | [+0.02, +0.78] | 29 % | 1.48 | 13.7 % | 16.5 % | +0.44 | +0.21 | +0.50 | +0.053 | 25.3 % / 26.6 % |
| ch3.5 | Chandelier 3.5 ATR | 360 | +0.405 | [+0.08, +0.75] | 31 % | 1.56 | 15.3 % | 14.6 % | +0.39 | +0.33 | +0.52 | +0.013 | 27.8 % / 26.1 % |
| ch4 | Chandelier 4 ATR | 355 | +0.435 | [+0.09, +0.85] | 31 % | 1.58 | 16.1 % | 14.3 % | +0.45 | +0.34 | +0.52 | +0.047 | 31.3 % / 25.9 % |
| ch4.5 | Chandelier 4.5 ATR | 353 | +0.402 | [+0.05, +0.79] | 30 % | 1.52 | 14.6 % | 15.3 % | +0.42 | +0.32 | +0.48 | +0.032 | 28.1 % / 26.0 % |
| ch5 | Chandelier 5 ATR | 353 | +0.378 | [+0.03, +0.75] | 29 % | 1.48 | 13.7 % | 15.8 % | +0.38 | +0.28 | +0.48 | +0.054 | 26.3 % / 26.8 % |
| ch6 | Chandelier 6 ATR | 352 | +0.362 | [+0.01, +0.75] | 29 % | 1.45 | 12.9 % | 16.4 % | +0.42 | +0.21 | +0.45 | +0.058 | 24.6 % / 27.0 % |
| ch8 | Chandelier 8 ATR | 350 | +0.364 | [+0.00, +0.74] | 29 % | 1.46 | 13.0 % | 16.5 % | +0.43 | +0.16 | +0.50 | +0.068 | 23.4 % / 27.0 % |
| ch4+be3 | Chandelier 4 ATR + break-even a +3R | 355 | +0.438 | [+0.10, +0.86] | 31 % | 1.59 | 16.2 % | 14.2 % | +0.46 | +0.35 | +0.52 | +0.050 | 31.3 % / 25.8 % |
| ch4+beS2 | Chandelier 4 ATR + break-even estructural (2 ATR) | 358 | +0.428 | [+0.09, +0.80] | 29 % | 1.59 | 16.0 % | 14.5 % | +0.45 | +0.34 | +0.51 | +0.020 | 31.9 % / 25.5 % |
| rf **✓** | Filtro de rango amplio | 294 | +0.572 | [+0.14, +1.05] | 32 % | 1.76 | 17.9 % | 14.6 % | +0.74 | +0.25 | +0.73 | +0.154 | 30.6 % / 20.8 % |
| vol2 | Volumen >= 2x | 268 | +0.524 | [+0.11, +0.99] | 32 % | 1.69 | 14.7 % | 15.6 % | +0.36 | +0.37 | +0.95 | +0.176 | 20.6 % / 20.2 % |
| rf+vol2 **✓** | Filtro de rango + volumen >= 2x | 226 | +0.693 | [+0.20, +1.22] | 35 % | 1.96 | 16.7 % | 13.4 % | +0.61 | +0.38 | +1.23 | +0.278 | 24.2 % / 17.1 % |
| rf+ch4 **✓** | Filtro de rango + chandelier 4 ATR | 297 | +0.624 | [+0.22, +1.07] | 34 % | 1.88 | 20.0 % | 13.3 % | +0.73 | +0.38 | +0.77 | +0.154 | 36.1 % / 20.6 % |
| rf+ch5 **✓** | Filtro de rango + chandelier 5 ATR | 295 | +0.571 | [+0.15, +1.01] | 33 % | 1.77 | 17.9 % | 14.5 % | +0.66 | +0.33 | +0.73 | +0.173 | 31.8 % / 21.3 % |
| vol2+ch4 | Volumen >= 2x + chandelier 4 ATR | 272 | +0.565 | [+0.16, +1.04] | 35 % | 1.78 | 16.3 % | 14.3 % | +0.34 | +0.51 | +0.97 | +0.179 | 24.1 % / 19.0 % |
| rf+ch4+xt1 **✓** | Filtro de rango + chandelier 4 ATR + respaldo canal-1 ATR | 297 | +0.581 | [+0.21, +1.05] | 34 % | 1.82 | 18.5 % | 13.9 % | +0.61 | +0.40 | +0.77 | +0.147 | 32.3 % / 20.4 % |

✓ = mejor R/op que la referencia en desarrollo, validación y test, y no peor en los 5 activos fuera de muestra.
Las variantes de stop cambian el tamaño de 1R: compáralas por CAGR y caída máxima, no solo por R/op.
