# 10 · Estudio de salidas, stops y filtros de entrada (2026-10-20)

Pregunta de Edgar: ¿mejora la estrategia con un take profit fijo o parcial, un stop a break-even, stops unos pips por
debajo de zonas de liquidez, otro trailing o un ajuste de entrada?

**Método.** Mismas señales, misma ejecución y mismos costes que el simulador oficial (entrada a la apertura siguiente,
stops con gap, slippage 2/5 bps, taker 5 bps + builder 20 bps por ejecución, funding). El simulador del estudio
(`src/smartflow/backtest/exit_study.py`) reproduce el oficial operación a operación, en Smart Flow y en Pyramid
(comprobado). 4h, BTC/ETH/SOL, 2022-01 → 2026-10, riesgo 0,5 % por operación; cada variante en los tramos fijos de
desarrollo / validación / test y en 5 activos fuera de muestra (XRP, BNB, ADA, NEAR, ZEC). Las variantes de stop
cambian el tamaño de 1R: se comparan por rentabilidad anual (CAGR) y caída máxima, no solo por R/op. Resultados
completos: `reports/exit_study.md` y `reports/exit_study_phase2.md`.

## Referencia

Stop a 1,5 ATR en Strike, salida al cierre de una vela de 4h al otro lado del canal de 10 velas, sin TP:
**+0,38 R/op, 13,7 %/año, caída máx. 16,5 %**; tramos +0,44 / +0,21 / +0,50; fuera de muestra +0,05; Pyramid 25,3 %.

## Lo que no mejora (descartado con datos)

| Idea | Resultado |
|---|---|
| TP fijo 1,5R … 10R | Peor siempre (de −6,9 % a 10,2 %/año): corta las pocas ganadoras grandes |
| TP parcial (33-50 % a 1-3R, con o sin break-even) | 3,8-9,7 %/año; menos caída, mucha menos rentabilidad |
| Break-even a +1R / +1,5R | 6,6 % / 10,7 %: los retrocesos normales lo cierran en cero |
| Break-even a +3R, o estructural (cierre 2 ATR sobre la vela de ruptura) | 14,3-14,6 %, mejora marginal y no en todos los tramos |
| Stop unos pips bajo el rango roto (0,05-0,2 %) | Hay que saltarse 2/3 de las operaciones (stop > 4 ATR): 1,5 %/año |
| Stop unos pips bajo el último swing o pivote | 0-4,5 %/año: queda más cerca que 1,5 ATR y lo barren |
| Stop bajo la vela de ruptura | 6-6,6 %/año |
| Stop 1,0 ATR | 23,9 % en BTC/ETH/SOL pero **negativo fuera de muestra**: sobreajuste |
| Stop 2,0 / 2,5 ATR | 9,8 % / 6,3 % |
| Salida por tiempo | Igual o peor en test |

## Lo que sí mejora

| Variante | ops | R/op | %/año | caída | dev / val / test | fuera de muestra | Pyramid |
|---|---|---|---|---|---|---|---|
| Referencia | 350 | +0,38 | 13,7 % | 16,5 % | 0,44 / 0,21 / 0,50 | +0,05 | 25,3 % / 26,6 % |
| **Filtro de rango amplio** | 294 | **+0,57** | **17,9 %** | **14,6 %** | 0,74 / 0,25 / 0,73 | **+0,15** (los 5 ≥ 0) | **30,6 % / 20,8 %** |
| Chandelier 4 ATR (stop en Strike que sigue al máximo − 4 ATR) | 355 | +0,44 | 16,1 % | 14,3 % | 0,45 / 0,34 / 0,52 | +0,05 | 31,3 % / 25,9 % |
| Filtro de rango + chandelier 4 ATR | 297 | +0,62 | 20,0 % | 13,3 % | 0,73 / 0,38 / 0,77 | +0,15 | 36,1 % / 20,6 % |

- **Filtro de rango amplio**: no operar rupturas que nacen dentro de un rango de 100 velas mayor que 12 ATR (opción del
  script, `range_filter`). Mejora los tres tramos, los 5 activos fuera de muestra y reduce la caída, en Smart Flow y en
  Pyramid. Ya ganó en los estudios anteriores (E8 y walk-forward E9) y corre en papel como "Smart Flow · Range filter"
  desde 2026-10-19: no es una elección entre 60 variantes de hoy. **Candidato a configuración oficial.**
- **Chandelier 4 ATR**: mejora, pero es un pico estrecho (3,5 ATR: 15,3 %; 4,5: 14,6 %; 5: 13,7 % = referencia). Con
  tantas variantes probadas, un óptimo así puede ser casualidad: **validar primero en papel** antes de usarlo. Tiene
  además una ventaja operativa: el stop vive en Strike y sube, así protege la ganancia aunque el servidor falle.
- Respaldo "stop en Strike = canal − 1 ATR": cuesta ≈ 0,5-1,5 puntos de rentabilidad anual; es un seguro, no una mejora.

## Recomendación

1. Pasar el **filtro de rango amplio** a la configuración oficial de las dos estrategias (decisión de Edgar: afecta a
   todos los usuarios; ~16 % menos operaciones, más beneficio por operación y menos caída).
2. Añadir un agente en papel con **filtro de rango + chandelier 4 ATR** y decidir el chandelier con 8-12 semanas de
   datos en vivo.
3. Mantener sin TP fijo, sin TP parcial y sin break-even temprano.

## Decisión (Edgar, 2026-10-20)

Adoptada ya como configuración oficial de las dos estrategias, igual para todos: **filtro de rango amplio +
chandelier 4 ATR** (`core.config.OFFICIAL`). Backtest oficial con ella: Smart Flow +0,62 R/op, 20,0 %/año, caída 13,3 %,
62 ops/año; Pyramid +0,65 R/op, 36,1 %/año, caída 20,6 %, 101 ops/año. Edgar decidió no esperar a validarlo en papel;
el chandelier queda vigilado en vivo (los agentes oficiales en papel también lo llevan).

**Cómo lo hace el agente** (`runner._chandelier`): tras cada cierre de 4h calcula el mejor extremo desde la entrada
menos 4 ATR; si mejora el stop en ≥ 0,1 ATR pone el stop nuevo en Strike (`tr1`, `tr2`…) y solo después cancela el
anterior; nunca afloja; si el nivel ya cruza el cierre, sale a mercado. Simulador oficial = estudio operación a
operación (tests/test_chandelier.py).

