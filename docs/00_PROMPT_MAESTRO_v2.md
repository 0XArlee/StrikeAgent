# Prompt maestro v2 — Smart Flow Agent para Strike Finance

> Versión mejorada del prompt original (v1, 17 secciones). Mantiene todos sus principios (fidelidad, seguridad,
> transparencia, verificación, no prometer rentabilidad) y corrige lo que la investigación del 2026-10-19 demostró
> falso o incompleto. Cambios respecto a v1 al final.

## Misión

Convertir **Smart Flow Signals [EdgeCraft]** (Pine v6, `SmartFlowSignals.txt`, referencia inmutable) en un agente de
trading para Strike Finance que: reproduce fielmente el indicador, mide con honestidad si tiene ventaja neta en las
condiciones reales de Strike, opera solo a través de la API oficial bajo un motor de riesgo, y se monetiza por un
mecanismo oficial **sin degradar la expectativa del usuario**. La rentabilidad se mide, nunca se promete.

## Hechos de partida (verificados; ver `docs/01`, `docs/04`)

- API oficial REST + WS con autenticación por **API wallet Ed25519** (no retira fondos). **Testnet** existe
  (`api-v2-testnet.strikefinance.org`, app `testnet.strikefinance.org`) pero con liquidez casi nula: sirve para la
  mecánica, no para medir ejecución.
- Posiciones **netas por mercado**; brackets TP/SL nativos; motor asíncrono (consultar por `client_order_id`).
- Builder Codes: cabecera `X-Builder-Fee-Bps` por orden, máx. 100 bps, ≤ lo aprobado por el usuario en el
  *builder connect*; se cobra por fill y se abona al instante.
- Otras dos vías nativas documentadas: **vault de usuario** (líder cobra 0-50 % del beneficio) y **copy trading**
  (líder cobra 10 % del beneficio del copiador).
- **No existe marketplace de agentes documentado.** Todo lo relativo a "publicar el agente en Strike" es una pregunta
  para Strike, no una tarea de implementación.
- Strike tiene histórico propio solo desde marzo 2026 y un volumen ~1e-4 del de Binance: **el feed de señal es
  Binance spot** (el feed de diseño del indicador y su propia fuente de volumen de respaldo), etiquetado como tal.

## Reglas

1. **Fidelidad primero.** Modo referencia = el script exacto. Semántica Pine medida (EMA/RMA sembradas con SMA,
   pivotes izquierda `>=`/derecha `>`, comparaciones con tolerancia 1e-10, `na` ⇒ falso). Verificación final
   **barra a barra contra un export de TradingView** (`smartflow verify-tv`), no solo por inspección.
2. **Las cifras del autor se verifican, no se heredan.** Si no se reproducen, se dice y se usan las medidas.
3. **Investigación pre-registrada.** Ventanas fijas (dev 2022-23, val 2024-H1'25, test H2'25-hoy), activos fuera de
   muestra, IC95 por bootstrap y t-stat en cada cifra; los experimentos fallidos se registran igual que los buenos.
   Nada se "optimiza" sin walk-forward que lo justifique.
4. **Ejecución realista** en todo backtest que se use para decidir: netting por mercado, entrada a la apertura
   siguiente, slippage, stops con gap, taker de Strike, builder fee por fill y funding.
5. **Puerta económica de la monetización.** Antes de fijar una comisión, medir su coste en R por timeframe y el punto
   de equilibrio; la comisión elegida debe dejar al usuario la mayor parte de la ventaja y con IC95 > 0. La
   comisión nunca influye en tamaño ni frecuencia.
6. **Riesgo antes que ejecución**: tamaño por distancia al stop, topes de apalancamiento y exposición, pérdida
   diaria/semanal, spread, impacto, basis, datos obsoletos, kill switch, una posición por mercado, liquidación lejos.
7. **Ciclo de vida explícito** (señal ≠ orden ≠ posición ≠ protegida), reconciliación con el exchange, estado
   desconocido ⇒ bloquear el mercado y alertar.
8. **Seguridad**: por defecto modo análisis y testnet; el autónomo exige configuración + confirmación explícita; nunca
   pedir ni almacenar frases semilla; claves de API wallet solo en `secrets/` (git-ignored), nunca en logs.
9. **Decisiones de negocio para el dueño**: nivel de comisión, canal (builder / vault / copy), mercados y capital.

## Fases y criterios de salida

| Fase | Entregable | Criterio de salida medible |
|---|---|---|
| 0 Investigación | `docs/01-04, 06, 07` | Cada afirmación con fuente y estado (DOC/TEST/HIP/BLOQ) |
| 1 Motor | `core/` + tests | Suite verde; invariancia a prefijos; `verify-tv` **IDENTICAL** en BTC 1h y 4h |
| 2 Datos y backtest | `backtest/`, `reports/experiments.md` | E1-E9 reproducibles con un comando; decisión de timeframe por significación |
| 3 Adaptador | `strike/` | `strike-check` y `auth-check` OK; ciclo bracket→stop→salida en testnet con orden mínima |
| 4 Riesgo y paper | `agent/` | ≥ 8 semanas de paper (4h) sin errores críticos; divergencia señal backtest↔paper = 0; slippage medido vs supuesto |
| 5 Monetización | builder/vault | Atribución y cobro observados en una operación real mínima; respuestas de Strike a `docs/07` |
| 6 Producción | runbook, despliegue LXC | Kill switch probado, recuperación tras reinicio probada, autorización explícita del dueño |

## Cambios respecto a v1

- Elimina la suposición de un marketplace de agentes y la convierte en preguntas; añade vault y copy trading como vías
  nativas reales.
- Añade la **puerta económica** de la comisión (el 1 % resultó incompatible con la estrategia).
- Fija la política de datos (Binance para señal, Strike para ejecución) y los cuatro precios separados.
- Exige verificación contra TradingView por export, con procedimiento concreto.
- Exige IC/significación y ventanas pre-registradas; reconoce que 2022-2026 entero está "visto" por el autor.
- Hace explícito el problema de netting (el script solapa operaciones) y la política para resolverlo.
- Sustituye "pruebas prolongadas" por criterios de salida medibles por fase.
