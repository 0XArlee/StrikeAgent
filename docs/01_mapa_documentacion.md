# 01 · Mapa de documentación y fuentes

Instantáneas guardadas el 2026-10-19 en `docs/sources/` (la doc de Strike cambia; esto fija qué se leyó).

| Fuente | Versión / fecha | Qué aporta | Uso |
|---|---|---|---|
| `docs.strikefinance.org/llms-full.txt` | 2026-10-19 (1,1 MB) | Toda la doc en markdown con OpenAPI embebido por endpoint | Referencia principal |
| OpenAPI embebido (fusionado en `strike_openapi_merged_2026-10-19.json`) | Builder 2.0.0 · Common 2.0.0 · Trade 2.2.0 · User 2.2.0 · Market 2.0.0 · Stats 1.0.0 · Vault 1.0.0 · Copy 1.2.0 · L3 1.0.0 | Esquemas exactos de request/response | Cliente REST y parsers |
| `/api/builder-codes` (+ Builder Connect, Deposit, Withdraw, Models) | 2026-10-19 | Flujo builder, cabecera `X-Builder-Fee-Bps`, reglas de fee | `docs/03` |
| `/api/getting-started` | 2026-10-19 | Firma Ed25519 de API wallet, permisos, errores | `strike/auth.py` |
| `/perpetuals/*` (order types, fees, prices, funding, margin, liquidations, sub-accounts, copy trading, vaults) | 2026-10-19 | Reglas de mercado y costes | riesgo, simulador, `docs/03` |
| `github.com/strike-finance/strike-builder-reference` | c926f76, 2026-04-24, **sin licencia** | App React de referencia (builder connect, órdenes, WS) | Solo lectura; no se reutiliza código |
| `github.com/strike-finance/strike-finance-skills` | 614da1a, 2026-04-29, MIT | Skills de agentes de IA + OpenAPI yaml | Contraste; no se copia código |
| `github.com/strike-finance/strike-finance-hermes-skill` | 62d69e6, 2026-06-20 | Skill Hermes: User-Agent obligatorio, confirmación antes de operar | Contraste |
| `github.com/PyneSys/pynecore` | 9360388, 2026-10-18, Apache-2.0 | Semántica Pine **medida contra TradingView** (EMA/RMA, pivotes, tolerancia 1e-10) | Referencia semántica; implementación propia en `core/pine.py` |
| Binance `api/v3/klines`, `fapi/v1/fundingRate` | API pública | Histórico spot 2020-09 → hoy; funding perp | Datos de backtest y feed de señal |
| API pública de Strike (mainnet y testnet) | probada 2026-10-19 | Mercados, velas, libro, funding, fees reales | `smartflow strike-check` |

## Contradicciones encontradas (doc ↔ API real ↔ repos)

| Tema | Documentación | Realidad / repo | Decisión |
|---|---|---|---|
| `/v2/fee-tiers` | claves camelCase | API devuelve PascalCase (`Tier`, `TakerRate`) — **TEST** | Parser tolerante |
| `/price/v2/premiumIndex` | objeto con `lastFundingRate` | lista con `fundingRate` — **TEST** | Parser tolerante |
| builder connect | `fee_share_bps` (requerido) | repo de referencia envía `max_fee_bps` | OpenAPI; verificar en testnet |
| Cobro de builder fee | cabecera `X-Builder-Fee-Bps` en cada orden | repo de referencia no la envía | Se envía; verificar qué pasa sin ella |
| Bracket TP/SL | `tp_order` / `sl_order` (objetos) | repo de referencia: `take_profit_orders[]` / `stop_loss_orders[]` | OpenAPI + skills (objetos); verificar |
| `klines` límite | máx. 1500 | skill dice 5000 | 1500 |
| User-Agent | — | Cloudflare bloquea UAs por defecto (403/1010) — **TEST** | UA propio siempre |
| Marketplace de agentes | no existe en la doc | `/agents` → 404 en app y web — **TEST** | Bloqueado: preguntas a Strike |
