# 05 · Informe cuantitativo — ¿tiene Smart Flow ventaja neta en condiciones de Strike?

Tablas completas y reproducibles: `reports/experiments.md` / `.json` (comando `smartflow research`, 528 s).
Fecha de los datos: 2026-10-18. **Nada de esto es una promesa de rentabilidad futura.**

## Método

- **Datos**: Binance spot, velas 1h/4h/1D/1W (+30m) desde 2020-09 (calentamiento) para BTC, ETH, SOL (activos del
  autor) y XRP, BNB, ADA, NEAR, ZEC (**fuera de muestra**: no usados al diseñar el indicador, todos listados en
  Strike). Validados: sin duplicados ni OHLC inválidos; 10 huecos de mantenimiento en 2020-21; agregación 1h→4h idéntica
  a las velas nativas.
- **Ventana**: 2022-01-01 → 2026-10-18; tramos fijados de antemano: dev 2022-23 · val 2024→2025-06 · test
  2025-07→2026-10 · "era Strike" 2026-03-20→.
- **Modelo realista (F)**: una posición por mercado (netting de Strike), entrada y salidas por cierre a la apertura
  siguiente, slippage 2 bps (mercado) / 5 bps (stop), stops con gap, taker de Strike 5 bps por fill, funding de
  perpetuos de Binance como proxy (Strike solo tiene funding desde 2026-03), builder fee variable.
- **Estadística**: R neto por operación, IC95 por bootstrap del R medio, t-stat; equity con 0,5 % de riesgo por
  operación (interés compuesto) solo como ilustración.

## Resultados principales (BTC+ETH+SOL salvo indicación)

| Experimento | 1h | 4h |
|---|---|---|
| Referencia del script (solapes, fill al cierre) | +0,153 R (n=2.617) | +0,664 R (n=635) |
| **Realista F** | **+0,121 R [−0,01, +0,26], t=1,8 → no significativo** | **+0,539 R [+0,17, +0,94], t=2,8** |
| dev / val / test | +0,06 / +0,09 / +0,26 (ninguno significativo) | +0,59 / +0,36 / +0,68 (todos > 0) |
| Por año 2022…2026 | −0,10, +0,23, +0,04, +0,09, +0,45 | +0,35, +0,81, +0,44, +0,21, +0,98 (todos > 0) |
| 5 activos fuera de muestra | −0,03 R (sin ventaja) | +0,175 R [−0,05, +0,41], los 5 positivos |
| Builder fee de equilibrio | ≈ 7 bps/fill | ≈ 69 bps/fill |
| Con builder 100 bps (1 %) | −1,54 R | −0,25 R |

**Otros timeframes (E6)**: 30m −0,05 R (las comisiones se comen la señal, como dice el script) · **2h +0,33 R
[+0,11, +0,60]** · 1D +0,60 R pero solo 48 operaciones en 4,8 años (IC −0,27…+2,06; −0,35 R en el tramo test).

**Regímenes (E4, descriptivo)**: la ventaja vive en volatilidad baja-media; el tercio de mayor volatilidad (ATR % del
precio) es negativo en 1h y 4h. Funciona tanto a favor como en contra de la tendencia diaria (SMA200D).

**Sensibilidad (E7, 4h)**: meseta razonable en `look_n` (10-20: +0,47…+0,54), `range_min` (0,7-1,2 ≈ igual),
`body_min`, `vol_min` (2,0 mejor que 1,5), `chan_n` (7-30 ≥ 10). Puntos sensibles: `htf_swing` (3: +0,47; **8:
+0,26**) y `stop_atr` (1,0 ATR: +0,85 R; 2,5: +0,29 R). No se cambian: ver regla de fidelidad.

**Opciones del script (E8)**: objetivo fijo (TP 2R/4R) empeora en todos los tramos (confirma el tooltip del autor).
La salida por money flow mejora dev/val en 4h pero empeora test (no consistente). El **filtro de rango amplio** mejora
en **los tres tramos** y en ambos timeframes.

**Walk-forward (E9)**: elegir cada 6 meses la mejor de 5 variantes con los 18 meses previos elige casi siempre el
filtro de rango amplio y supera a la referencia fija fuera de muestra (1h +0,275 vs +0,154; 4h +0,734 vs +0,607).

## Prueba decisiva del filtro de rango amplio en activos fuera de muestra

| 4h | Referencia | Filtro rango amplio |
|---|---|---|
| BTC+ETH+SOL | +0,539 R (t=2,8), maxDD 29 R | **+0,727 R (t=3,2)**, maxDD 25 R |
| 5 activos OOS | +0,175 R (t=1,4) | **+0,275 R (t=1,9)**, los 5 positivos |
| Los 8 activos | +0,315 R (t=3,0), maxDD 65 R | **+0,453 R (t=3,6)**, maxDD 45 R |
| BTC+ETH+SOL con builder 10 bps | +0,460 R | **+0,650 R**, CAGR ≈ 20,7 %, maxDD equity 13 % (0,5 %/op) |

En 1h el filtro tampoco rescata los activos fuera de muestra (+0,01 R): **1h no generaliza**.

## Conclusiones y recomendación

1. **Hay ventaja estadística en 4h** con costes y ejecución realistas, estable por tramos y por años, y que
   generaliza (más débil) a activos no usados para diseñarla. **En 1h no se puede afirmar ventaja.**
2. **Configuración recomendada para el agente** (modo experimental documentado, **decisión tuya**): 4h, filtro de
   rango amplio activado (opción original del indicador, no un filtro nuevo), BTC + ETH como núcleo (mejor liquidez en
   Strike y mayor R), resto de mercados opcionales con tamaño reducido. El resto de parámetros, los de referencia.
3. **Builder fee ≤ 10 bps** (ver `docs/03`). El 1 % es incompatible con la estrategia.
4. Las cifras del comentario del indicador no se reproducen (`docs/02 §5`); estas sí, con un comando.

## Limitaciones honestas

- 2022-2026 completo es historia que el autor pudo ver al elegir los valores por defecto: el único fuera de muestra
  "limpio" son los activos OOS y lo que pase de aquí en adelante (paper trading).
- Funding: proxy de Binance (perp USDT) antes de 2026-03; el de Strike puede diferir.
- Slippage modelado en 2/5 bps: correcto para BTC/ETH en Strike (impacto medido 0,3-1,1 bps para 10 k$), optimista
  para NEAR/ADA (4-7 bps).
- Basis Strike-Binance y disparo del stop por mark price de Strike no se modelan antes de 2026-03 (en la era Strike,
  basis mediano 7-12 bps ≈ 0,01 R en 1h, menos en 4h).
- Muestras pequeñas: 4h ≈ 73 operaciones/año en 3 mercados; los IC son anchos. Un año malo (2025: +0,21 R) es normal.
