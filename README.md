# Smart Flow Agent (EdgeCraft) — PRIVADO

Agente de trading para **Strike Finance** basado en el indicador propietario *Smart Flow Signals [EdgeCraft]*
(`SmartFlowSignals.txt`, referencia inmutable, no publicar). Código propietario: este repositorio no debe ser público.

## Estado (2026-10-19)

| Fase | Estado |
|---|---|
| 0 Investigación | ✅ `docs/00-07` |
| 1 Motor de señales | ✅ traducción completa + 58 tests · ✅ verificada contra re-traducción en PyneCore: 4h idéntico (6.000 velas, 123 señales) |
| 2 Datos y backtest | ✅ Binance 2020-09 → hoy (8 activos) · simulador realista · experimentos E1-E9 (`reports/`) |
| 3 Adaptador Strike | ✅ firma y lecturas autenticadas verificadas en testnet · ✅ mecánica de órdenes sin fills verificada en testnet · ⏳ ciclo con fill (testnet tiene libros rotos) |
| 4 Riesgo y paper | ✅ motor de riesgo, ciclo de vida, journal, paper trading sobre el libro real de Strike · ⏳ 4 agentes paper 24/7 en the agents' host (referencia + 3 variantes de prueba) |
| 5 Monetización | ⛔ requiere registro de builder (tú) — **no verificada** |
| 6 Publicación | ⛔ no hay marketplace de agentes documentado (`docs/07`) |
| 7 Web | ✅ **https://edgecraft-strikecity.pages.dev** (Cloudflare): Strike City con los agentes oficiales en papel y los de los usuarios · ✅ alta con wallet de Cardano → agente real en su cuenta de Strike (builder code, abierto a todos desde 2026-10-20) |
| 8 Operación | ✅ (2026-10-21) cuenta vacía y depósitos tratados aparte del resultado · vigilancia del CT y externa (GitHub) · salud de cada estrategia frente al backtest con pausa de seguridad · secretos del PC cifrados · repositorio privado (`docs/08`) |

**Resultado cuantitativo clave** (`docs/05`): con ejecución realista, **4h** tiene ventaja estadísticamente
significativa (≈ +0,54 R/operación, IC95 > 0); **1h no** es significativo; **1D** tiene muy pocas operaciones. Una
builder fee del **1 % hace perder al usuario**. **Fee elegida: 20 bps por ejecución** (2026-10-19): en 4h quedan +0,38 R/op
(IC95 [+0,02, +0,78]); por encima de ~20 bps la ventaja deja de ser estadísticamente significativa (`docs/03`).

## Uso rápido (PowerShell, dentro de esta carpeta)

```powershell
uv venv .venv; uv pip install -e ".[dev]"            # una vez
.venv\Scripts\python -m pytest                        # tests
.venv\Scripts\smartflow data                          # descarga/actualiza Binance
.venv\Scripts\smartflow backtest --tf 240             # backtest realista 4h BTC/ETH/SOL
.venv\Scripts\smartflow backtest --tf 240 --builder-bps 10
.venv\Scripts\smartflow research                      # todos los experimentos -> reports/
.venv\Scripts\smartflow analyze --tf 240              # estado actual explicado (sin órdenes)
.venv\Scripts\smartflow strike-check --env mainnet    # conformidad de la API pública
.venv\Scripts\smartflow keys testnet                  # genera API wallet local (ver docs/CONECTAR_WALLET.md)
.venv\Scripts\python -m smartflow.strike.keys import <archivo.json> testnet   # importa una clave descargada de Strike
.venv\Scripts\smartflow auth-check --env testnet      # lecturas firmadas (no envía órdenes)
copy config\agent.example.toml config\agent.toml
.venv\Scripts\smartflow agent run --config config\agent.toml           # modo del archivo (por defecto: análisis)
.venv\Scripts\smartflow agent approve <trade_id> --config config\agent.toml   # modo confirmación
.venv\Scripts\smartflow verify-tv export.csv --tf 60  # fidelidad vs TradingView
.venv\Scripts\smartflow api --city config\city.toml   # API de solo lectura para Strike City (:8787)
.venv\Scripts\smartflow secrets status                # secrets/ cifrados con DPAPI (lock: cifrar los que estén en claro)
.venv\Scripts\smartflow site-check                    # ¿recibe la web de producción los datos de los agentes?
```

En el CT (como `smartflow`): `smartflow health` (estrategias frente al backtest; `--release <estrategia>` levanta la
pausa de seguridad), `smartflow watchdog`, `smartflow alert-test` (ver `docs/08` "Vigilancia y alertas").

Web (`web/`, Node 20):

```powershell
cd web; npm install; npm run build; npm run preview      # http://localhost:4173  ·  ciudad: /#/city
$env:SMARTFLOW_API="http://HOST:8787"; npm run preview   # la ciudad con los agentes reales del host (LAN, tras abrir 8787)
npm run deploy:cf                                         # publica en https://edgecraft-strikecity.pages.dev (ver docs/08)
# verificación real en navegador (Playwright + axe-core): scripts/verify_ui.py (alta simulada), scripts/verify_city.py,
# scripts/verify_city_live.py y scripts/verify_onboarding_live.py (contra la URL pública)
```

Modos del agente: `analysis` (solo explica) · `simulation` (paper sobre el libro real de Strike) · `confirmation`
(propone y espera tu `approve`) · `autonomous` (requiere `allow_autonomous = true` **y**
`SMARTFLOW_LIVE_ACK="I ACCEPT REAL ORDERS"`; mainnet además `allow_mainnet = true`). Kill switch: crear el archivo
`KILL_SWITCH` en la carpeta o `SMARTFLOW_KILL=1`.

## Documentación

`docs/00` prompt v2 · `01` fuentes · `02` especificación y auditoría del indicador · `03` builder codes y
monetización · `04` capacidades de Strike · `05` informe cuantitativo · `06` arquitectura · `07` riesgos y preguntas
para Strike · `08` runbook · `09` referencia Midnight City e implementación de Strike City · `CONECTAR_WALLET.md`. Tareas y lecciones: `tasks/`.

## Procedencia de componentes

Todo el código es propio. Semántica Pine contrastada con PyneCore (Apache-2.0, solo lectura); API según la doc
oficial de Strike (instantánea en `docs/sources/`); los repos oficiales de Strike se leyeron pero no se copió código
(`strike-builder-reference` no tiene licencia). Datos: API pública de Binance.
