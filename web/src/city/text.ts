// EdgeCraft-StrikeCity strings (EN/ES) and the journal → sentence renderer shared by the feed, the agent card and the details.
import type { Lang } from "../i18n";
import type { Decision, Status } from "./agents";

export function fmtPrice(v: number, lang: Lang): string {
  const loc = lang === "es" ? "es-ES" : "en-US";
  return v.toLocaleString(loc, { maximumFractionDigits: v >= 1000 ? 0 : v >= 10 ? 2 : 4, minimumFractionDigits: v >= 1000 ? 0 : 2 });
}
export const fmtR = (r: number, lang: Lang) => `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}R`;
export const fmtPct = (v: number, lang: Lang, digits = 2) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
export const ticker = (m: string) => m.replace("-USD", "");
/** A trade's money result: cents for small amounts, signed. */
export const money = (v: number, loc: string) => v.toLocaleString(loc, { style: "currency", currency: "USD", minimumFractionDigits: 2,
  maximumFractionDigits: Math.abs(v) < 1 ? 4 : 2, signDisplay: "exceptZero" });
export const pctSigned = (v: number, loc: string) => v.toLocaleString(loc, { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 3,
  signDisplay: "exceptZero" });

const en = {
  title: "EdgeCraft-StrikeCity",
  back: "Smart Flow",
  loading: "Entering EdgeCraft-StrikeCity",
  loadingSteps: ["Syncing order books…", "Reading funding rates…", "Waking up the agents…", "Lighting the streets…"],
  live: "Live",
  liveLong: "Every agent here is real. Smart Flow's own agents run on paper with Strike prices to keep testing the strategies; users' agents (Real) trade their own Strike account. Every decision comes from their journal.",
  realTag: "Paper", kindLive: "Real · Strike", kindTestnet: "Strike testnet · test money", testTag: "Test", ownerUser: "Strike user",
  strategyTag: { smartflow: "Smart Flow", pyramid: "Pyramid" } as Record<string, string>,
  empty: { title: "No agents online right now", body: "The city only shows real agents. Start yours and be the first one here.",
    offline: "The agents cannot be reached right now. The city tries again on its own every 30 seconds." },
  realNote: "Paper agent: real Smart Flow engine decisions on Binance candles, fills simulated on Strike's real order book. No real money.",
  realNoteLive: "Live agent: it trades its owner's own Strike account with the official Smart Flow configuration. Only the owner sees the amounts.",
  welcome: {
    title: "Welcome to EdgeCraft-StrikeCity",
    lead: "Every figure here is a Smart Flow agent trading on Strike Finance. They only walk when they have something to do: analyse at each candle close, take an order to the exchange, come back with the result. One standing still with an hourglass is waiting for its next setup.",
    points: [
      "Drag to move, scroll or pinch to zoom, click an agent to follow it.",
      "Bubbles show what each agent is doing right now. Every decision explains why.",
      "Market towers, the exchange screen and the fountain use live Strike data.",
    ],
    liveNote: "Every agent you see is real: Smart Flow's own agents, on paper, and those of Strike users who chose to show theirs, trading their own Strike account. They check the market at every candle close of their timeframe and every decision comes from their journal.",
    enter: "Enter the city",
  },
  nav: { map: "Map", agents: "Agents", ranks: "Ranks", feed: "Feed", markets: "Markets", guide: "Guide", me: "My agent" },
  me: { back: "Back to the city" },
  stats: { live: "agents online", inTrade: "in a trade", trades: "trades 24h", r: "result 24h" },
  weather: { calm: "Calm", breezy: "Breezy", storm: "Storm", tip: "City weather follows BTC's 24h move on Strike." },
  source: { strike: "Strike live data", binance: "Binance data (Strike unavailable)", offline: "Offline: no market data" },
  status: {
    analyzing: "Analysing", waiting: "Waiting for a setup", signal: "Signal found", risk: "Blocked by risk check",
    entering: "Sending order", in_trade: "In a trade", exiting: "Trade closed", paused: "Paused", offline: "Offline",
    unfunded: "Waiting for a deposit",
  } as Record<Status, string>,
  unfundedNow: "Connected to Strike, but its account has no balance yet: it sends no order and pays nothing. As soon as a deposit arrives it takes the next signal by itself.",
  card: {
    follow: "Follow", following: "Following", details: "Details", close: "Close", markets: "Markets", risk: "Risk per trade",
    now: "Right now", position: "Open position", entry: "Entry", stop: "Stop", exit: "Dynamic exit", rOpen: "Open result",
    today: "Result 24h", owner: "Owner", noPosition: "No open position",
    nextCheck: "Next check", lastCheck: "Last check", account: "Paper account", accountLive: "Strike account", ret: "Account result", positions: "Open positions", pnl: "Open P&L", params: "Parameters",
    reference: "Reference (as published)", official: "Official: the script + wide-range filter + 4 ATR chandelier stop",
    experimental: (c: string) => `Experimental: ${c}`, fee: "Smart Flow fee",
    feeVal: (bps: number) => `${bps} bps (${(bps / 100).toFixed(2)}%) per fill`, more: (n: number) => `+${n} more open`,
    trades: "Closed trades",
  },
  details: { portfolio: "Portfolio", activity: "Activity", trades: "Trades", stats: "Stats", why: "Why", invalidates: "What would cancel it", next: "Next check",
    market: "Market", side: "Side", result: "Result", reason: "Exit", when: "When", empty: "Nothing yet.",
    netNote: "Result in R, and net in money and over the position's size: after the entry and the exit fees. Strike's history takes off only the exit fee on each close, so its figure can be a little better." },
  st: { trades: "Trades", win: "Win rate", total: "Total result", pf: "Profit factor", best: "Best trade",
    onlyAgent: "Only the agent's own strategy trades count here. Test trades are listed in Trades and never counted; anything done by hand on the account shows in Portfolio.",
    testsApart: "Test trades are listed here and never count in any statistic.", money: "Net result" },
  agents: { title: "Agents", search: "Search agents", all: "All", count: (n: number) => `${n} agents`, none: "No agents match." },
  ranks: { title: "Ranks", by: "Ranked by total result in R (1R = the amount risked at the stop).", cta: "Put your own agent in the city",
    rank: "Rank", agent: "Agent", total: "Total", win: "Win", trades: "Trades" },
  feed: { title: "Live feed", pause: "Pause feed", resume: "Resume feed", empty: "Waiting for the first events…" },
  markets: { title: "Markets", price: "Price", change: "24h", funding: "Funding /h", agents: "Agents in trade", long: "long", short: "short",
    fundingTip: "Positive funding: longs pay shorts every hour on Strike. Negative: shorts pay longs." },
  guide: {
    title: "Oracle", sub: "Answers about the city and the Smart Flow strategy.",
    qa: [
      ["Why isn't an agent trading?", "Smart Flow only trades strong breakouts (on 4h by default): a candle of at least 1 ATR with a 60% body that closes beyond the last 20 candles on 1.5× volume, aligned with the daily trend, and not inside a very wide range. Most of the time there is no setup, so agents analyse and wait. Every skipped check is written in their Activity."],
      ["What does 1R mean?", "R is the amount an agent risks between its entry and its protective stop. −1R is a full stop-out; +3R is three times what was risked. Results in R compare agents fairly no matter the account size."],
      ["Why do most trades lose?", "It is a trend strategy: about 2 in 3 trades are small losses and a minority run several R. In the 2022-2026 study the average was +0.62R per trade after Strike fees, the Smart Flow fee (0.20% per execution) and slippage. That is a historical simulation, not a promise."],
      ["Why is an agent standing still?", "Because it is waiting for its setup. Smart Flow only looks at the market at each candle close (every 4 hours by default), so in between there is nothing to do. Agents only walk when something real happens: a candle close sends them to the Signal Lab, an order to the Exchange, a closed trade to the Cafe (or Liquidation Alley if its stop was hit), a rejected signal to the Risk Office."],
      ["What do the buildings mean?", "Plaza: agents waiting for a setup. Signal Lab: analysis at each candle close. Market towers: agents with an open trade in that market. Strike Exchange: where an agent goes when it sends an order. Risk Office: where it goes when the risk engine rejects a signal. Funding Cafe: after a trade closes; Liquidation Alley: when it closed at its stop. Agent Homes: paused or offline agents, and those waiting for a deposit."],
      ["Why does an agent say \"Waiting for a deposit\"?", "Its owner connected it to Strike, but the Strike account has no balance yet. It sends no order and pays nothing; as soon as a deposit arrives it takes the next signals by itself, without restarting anything. A deposit never counts as part of its result."],
      ["What does the fountain show?", "The colour follows BTC funding on Strike: mint when longs pay shorts, red when shorts pay longs."],
      ["Are these agents real?", "Yes. Smart Flow's own agents run 24/7 on paper with Strike prices: the two strategies users can pick (Smart Flow and Smart Flow Pyramid) and the variants under test. The others belong to Strike users who chose to show theirs; the ones labelled Real trade their own Strike account. Everything they show comes from their journals and, for real ones, from their Strike account."],
      ["Can I add my agent?", "Yes: press \"Put your own agent in the city\" in Ranks, connect your Cardano wallet, make your character, pick the strategy and sign Strike's message. Your agent trades your own Strike account with a stop on every trade; tick \"Show my agent in EdgeCraft-StrikeCity\" to appear here with the name you choose."],
    ] as [string, string][],
  },
  legend: { title: "Bubbles" },
  roadmap: { title: "Roadmap", live: "Live", next: "Next", later: "Later", items: {
    live: ["Smart Flow engine, verified bar by bar against TradingView", "Two strategies: Smart Flow and Smart Flow Pyramid",
      "Agents trading their owners' own Strike accounts (builder code)", "EdgeCraft-StrikeCity live, with each agent's real portfolio"],
    next: ["More markets as they prove an edge after costs", "New strategies with an edge of their own", "Alerts on your phone"],
    later: ["Smart Flow vault on Strike", "Clan competitions"],
  } },
  scale: { title: "Swarm scale", level: (l: number, n: number) => `Level ${l} of ${n}`, next: (goal: number) => `next at ${goal} agents`,
    names: ["Spark", "Crew", "Pack", "Swarm", "Hive", "Network"] },
  zoomIn: "Zoom in", zoomOut: "Zoom out", recenter: "Recenter", canvas: (live: number, trade: number) =>
    `Map of EdgeCraft-StrikeCity with ${live} agents online, ${trade} in a trade. Use the arrow keys to move and + or − to zoom. The Agents and Feed panels list the same information.`,
  building: { agentsHere: (n: number) => `${n} agents here`, close: "Close" },
  buildings: {
    lab: "Agents come here at each candle close to analyse the charts: range, displacement, volume and the daily trend.",
    btc: "Agents with an open BTC-USD trade stand here. The sign shows the live Strike price.",
    eth: "Agents with an open ETH-USD trade stand here. The sign shows the live Strike price.",
    sol: "Agents with an open SOL-USD trade stand here. The sign shows the live Strike price.",
    alts: "Agents with an open XRP, BNB, ADA, NEAR or ZEC trade stand here.",
    risk: "Every order passes the risk engine first: spread, daily loss limit, open positions, data freshness. An agent comes here when it rejects a signal.",
    alley: "Where an agent goes when a trade closes at its protective stop: a planned loss, placed on Strike together with the entry.",
    exchange: "An agent comes here when it sends an order to Strike Finance. The screen shows BTC's last 48 hours and the order book.",
    vault: "Strike vaults. A Smart Flow vault is on the roadmap.",
    clan: "Strike clans and competitions. Coming later.",
    homes: "Paused or offline agents, and those waiting for a deposit, rest here until they run again.",
    hq: "Smart Flow HQ, the builder behind the agents.",
    cafe: "Agents stop here for a moment after a trade closes (not at its stop).",
    arena: "The leaderboard: open Ranks to see it.",
  } as Record<string, string>,
  ev: {
    check: (m: string, parts: string) => `No trade on ${m}: ${parts}.`,
    part: {
      range: (v: string, min: string) => `candle range ${v} ATR (needs ${min})`,
      body: (v: string, min: string) => `body ${v}% of the candle (needs ${min}%)`,
      inside: (n: string) => `close inside the ${n}-candle range`,
      against_candle: () => "the breakout candle closes against its own direction",
      volume: (v: string | null, min: string) => v ? `volume ${v}× its average (needs ${min}×)` : "volume average still warming up",
      bias: (side: string) => `${side === "long" ? "buy" : "sell"} setup against the daily trend`,
      wide_range: (span: string, max: string) => `signal born inside a wide range (${span} ATR, filter ${max})`,
      skipped: () => "signal skipped by a filter",
      warmup: () => "indicators still warming up",
      none: () => "no setup",
    } as Record<string, (...a: (string | null)[]) => string>,
    not_traded: (m: string) => `Signal on ${m} not traded: stale candle or unhealthy data.`,
    risk_weekly: () => "Signal skipped by the risk engine: weekly loss limit reached.",
    risk_other: (why: string) => `Signal skipped by the risk engine: ${why}.`,
    not_filled: (m: string) => `Order on ${m} not filled within the protective price: nothing opened.`,
    alert: (msg: string) => `Operational alert: ${msg}`,
    alertRead: (code: string) => `Strike did not answer when the agent checked its account${code ? ` (error ${code})` : ""}. It tries again by itself within a minute.`,
    alertStrike: (code: string) => `Strike did not answer the agent for a moment${code ? ` (error ${code})` : ""}. It checks again by itself.`,
    exitReason: { trail: "close back through the 10-candle channel", stop: "protective stop", chandelier: "stop that followed the price (4 ATR)", target: "target reached",
      time: "candle limit reached", flow: "money-flow cross", test: "end of the test (2 min)", other: "closed on the exchange" } as Record<string, string>,
    no_range: (m: string) => `No trade on ${m}: the close is inside the 20-candle range.`,
    no_body: (m: string) => `No trade on ${m}: breakout without displacement (body under 60% of the range).`,
    low_volume: (m: string, v: string) => `No trade on ${m}: volume only ${v}× its 20-candle average (needs 1.5×).`,
    against_trend: (m: string) => `No trade on ${m}: the breakout goes against the daily structure.`,
    signal: (m: string, side: string, p: string, v: string) => `${side === "long" ? "BUY" : "SELL"} signal on ${m} @ ${p}: close beyond the 20-candle ${side === "long" ? "high" : "low"} on ${v}× volume.`,
    risk_spread: (bps: string) => `Signal skipped by the risk engine: spread ${bps} bps, above the 10 bps limit.`,
    risk_daily: () => "Signal skipped by the risk engine: daily loss limit reached.",
    risk_open: () => "Signal skipped by the risk engine: a position is already open in this market.",
    risk_min: (n: string, min: string) => `Signal skipped: with this balance the order would be ${n}, below Strike's minimum of ${min}. Keep at least 150 $ in the account (300 $ with the conservative risk) so the agent can take its signals.`,
    risk_balance: () => "Signal skipped: its Strike account has no balance yet. Once its owner deposits (at least 150 $; 300 $ with the conservative risk) it takes the next signals by itself.",
    risk_hold: () => "Signal skipped: this strategy is on a safety hold because its real results fell clearly below the backtest. Open trades keep their stop; new ones wait until Smart Flow reviews it.",
    test_funds: (needs: string, avail: string | null) => `The test trade could not run: it needs at least ${needs} available in the Strike account and ${avail ? `there are ${avail}` : "there is nothing"}. Deposit in Strike and try again.`,
    test_busy: () => "The test trade could not run right now: every market was busy (an open trade, no fresh data or a wide spread). Try again in a few minutes.",
    open: (side: string, m: string, p: string, s: string) => `Opened ${side.toUpperCase()} ${m} @ ${p} with the stop at ${s} (−1R) on Strike.`,
    held: (side: string, m: string, p: string) => `Its Strike account holds a ${side.toUpperCase()} ${m} @ ${p} that the agent did not open (no stop from the agent).`,
    close: (side: string, m: string, r: string, reason: string) => `Closed ${side.toUpperCase()} ${m}: ${r} (${reason}).`,
    pause: () => "Paused by its owner.",
    resume: () => "Resumed by its owner.",
    start: () => "Started by its owner.",
    live: () => "Now trading its owner's own Strike account.",
    settings: () => "Its owner changed its strategy, markets or risk.",
    test: () => "Its owner asked for a test trade.",
    test_open: (m: string, p: string, s: string) => `Test trade asked by its owner: bought the minimum of ${m} @ ${p} with the stop at ${s} on Strike.`,
    test_close: (m: string, p: string) => `Test trade closed: sold ${m} @ ${p}. The agent opened, protected and closed it on its own.`,
    account_fill: (side: string, m: string, p: string) => `On its Strike account, outside the agent: ${side === "buy" ? "BUY" : "SELL"} ${m} @ ${p}.`,
    live_off: () => "Stopped: its owner stopped its trading on Strike.",
    why: {
      analysis: "Smart Flow only trades strong, high-volume breakouts aligned with the higher-timeframe trend.",
      signal: "Displacement candle of at least 1 ATR with a 60% body, aligned with the daily structure.",
      risk: "The risk engine checks every order before it reaches Strike.",
      order: "Size makes the stop cost the chosen risk per trade.",
    } as Record<string, string>,
    invalidates: "A candle close back through the 10-candle channel, or the stop on Strike: 1.5 ATR away at first, then following the price 4 ATR below the highest price reached.",
    next: "Next check at the close of its next candle.",
  },
  ago: (s: number) => s < 60 ? `${Math.max(1, Math.round(s))}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : s < 86400 ? `${Math.round(s / 3600)}h ago` : `${Math.round(s / 86400)}d ago`,
  inTime: (s: number) => s <= 60 ? "in under a minute" : s < 3600 ? `in ${Math.round(s / 60)} min` : `in ${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`,
};

type CityText = typeof en;

const es: CityText = {
  ...en,
  title: "EdgeCraft-StrikeCity",
  loading: "Entrando en EdgeCraft-StrikeCity",
  loadingSteps: ["Sincronizando libros de órdenes…", "Leyendo el funding…", "Despertando a los agentes…", "Encendiendo las calles…"],
  live: "En vivo",
  liveLong: "Todos los agentes de aquí son reales. Los de Smart Flow funcionan en papel con precios de Strike para seguir probando las estrategias; los de los usuarios (Real) operan su propia cuenta de Strike. Cada decisión sale de su diario.",
  realTag: "Papel", kindLive: "Real · Strike", kindTestnet: "Strike testnet · dinero de prueba", testTag: "Prueba", ownerUser: "Usuario de Strike",
  strategyTag: { smartflow: "Smart Flow", pyramid: "Pyramid" } as Record<string, string>,
  empty: { title: "Ahora mismo no hay agentes en línea", body: "La ciudad solo muestra agentes reales. Inicia el tuyo y sé el primero.",
    offline: "Ahora mismo no se puede conectar con los agentes. La ciudad lo vuelve a intentar sola cada 30 segundos." },
  realNote: "Agente en papel: decisiones reales del motor Smart Flow sobre velas de Binance, ejecución simulada sobre el libro de órdenes real de Strike. Sin dinero real.",
  realNoteLive: "Agente en vivo: opera la cuenta de Strike de su dueño con la configuración oficial de Smart Flow. Las cantidades solo las ve su dueño.",
  welcome: {
    title: "Bienvenido a EdgeCraft-StrikeCity",
    lead: "Cada figura de aquí es un agente Smart Flow operando en Strike Finance. Solo caminan cuando tienen algo que hacer: analizar al cierre de cada vela, llevar una orden al exchange, volver con el resultado. Uno quieto con un reloj de arena está esperando su próximo setup.",
    points: [
      "Arrastra para moverte, rueda o pellizca para hacer zoom, pulsa un agente para seguirlo.",
      "Las burbujas muestran qué hace cada agente ahora mismo. Cada decisión explica el porqué.",
      "Las torres de mercado, la pantalla del exchange y la fuente usan datos de Strike en vivo.",
    ],
    liveNote: "Todos los agentes que ves son reales: los de Smart Flow, en papel, y los de usuarios de Strike que han querido mostrar el suyo, operando su propia cuenta de Strike. Revisan el mercado en cada cierre de vela de su timeframe y cada decisión sale de su diario.",
    enter: "Entrar en la ciudad",
  },
  nav: { map: "Mapa", agents: "Agentes", ranks: "Ranking", feed: "Actividad", markets: "Mercados", guide: "Guía", me: "Mi agente" },
  me: { back: "Volver a la ciudad" },
  stats: { live: "agentes en línea", inTrade: "en operación", trades: "operaciones 24h", r: "resultado 24h" },
  weather: { calm: "Calma", breezy: "Brisa", storm: "Tormenta", tip: "El clima de la ciudad sigue el movimiento de BTC en 24h en Strike." },
  source: { strike: "Datos de Strike en vivo", binance: "Datos de Binance (Strike no disponible)", offline: "Sin conexión: sin datos de mercado" },
  status: {
    analyzing: "Analizando", waiting: "Esperando un setup", signal: "Señal encontrada", risk: "Bloqueada por riesgo",
    entering: "Enviando orden", in_trade: "En operación", exiting: "Operación cerrada", paused: "En pausa", offline: "Sin conexión",
    unfunded: "Esperando un depósito",
  },
  unfundedNow: "Conectado a Strike, pero su cuenta todavía no tiene saldo: no envía órdenes ni paga nada. En cuanto llegue un depósito tomará la siguiente señal él solo.",
  card: {
    follow: "Seguir", following: "Siguiendo", details: "Detalles", close: "Cerrar", markets: "Mercados", risk: "Riesgo por operación",
    now: "Ahora mismo", position: "Posición abierta", entry: "Entrada", stop: "Stop", exit: "Salida dinámica", rOpen: "Resultado abierto",
    today: "Resultado 24h", owner: "Dueño", noPosition: "Sin posición abierta",
    nextCheck: "Próxima comprobación", lastCheck: "Última comprobación", account: "Cuenta en papel", accountLive: "Cuenta de Strike", ret: "Resultado de la cuenta", positions: "Posiciones abiertas", pnl: "Resultado abierto", params: "Parámetros",
    reference: "Referencia (los publicados)", official: "Oficial: el script + filtro de rango amplio + stop chandelier de 4 ATR",
    experimental: (c: string) => `Experimental: ${c}`, fee: "Comisión Smart Flow",
    feeVal: (bps: number) => `${bps} pb (${(bps / 100).toLocaleString("es-ES", { minimumFractionDigits: 2 })}%) por ejecución`, more: (n: number) => `+${n} abiertas más`,
    trades: "Operaciones cerradas",
  },
  details: { portfolio: "Cartera", activity: "Actividad", trades: "Operaciones", stats: "Estadísticas", why: "Por qué", invalidates: "Qué la invalidaría", next: "Próxima comprobación",
    market: "Mercado", side: "Lado", result: "Resultado", reason: "Salida", when: "Cuándo", empty: "Todavía nada.",
    netNote: "Resultado en R y, neto, en dinero y sobre el tamaño de la posición: después de las comisiones de entrada y de salida. El historial de Strike solo descuenta la de salida en cada cierre, por eso su cifra puede ser algo mejor." },
  st: { trades: "Operaciones", win: "Acierto", total: "Resultado total", pf: "Factor de beneficio", best: "Mejor operación",
    onlyAgent: "Aquí solo cuentan las operaciones de la estrategia del agente. Las de prueba salen en Operaciones y no cuentan nunca; lo que se haga a mano en la cuenta sale en Cartera.",
    testsApart: "Las operaciones de prueba salen aquí y no cuentan en ninguna estadística.", money: "Resultado neto" },
  agents: { title: "Agentes", search: "Buscar agentes", all: "Todos", count: (n: number) => `${n} agentes`, none: "Ningún agente coincide." },
  ranks: { title: "Ranking", by: "Ordenado por resultado total en R (1R = lo que se arriesga hasta el stop).", cta: "Pon tu propio agente en la ciudad",
    rank: "Puesto", agent: "Agente", total: "Total", win: "Acierto", trades: "Operaciones" },
  feed: { title: "Actividad en vivo", pause: "Pausar actividad", resume: "Reanudar actividad", empty: "Esperando los primeros eventos…" },
  markets: { title: "Mercados", price: "Precio", change: "24h", funding: "Funding /h", agents: "Agentes en operación", long: "largo", short: "corto",
    fundingTip: "Funding positivo: los largos pagan a los cortos cada hora en Strike. Negativo: los cortos pagan a los largos." },
  guide: {
    title: "Oráculo", sub: "Respuestas sobre la ciudad y la estrategia Smart Flow.",
    qa: [
      ["¿Por qué un agente no opera?", "Smart Flow solo opera rupturas fuertes (en 4h por defecto): una vela de al menos 1 ATR con un cuerpo del 60% que cierra más allá de las últimas 20 velas con 1,5× de volumen, a favor de la tendencia diaria y fuera de un rango muy amplio. Casi siempre no hay setup, así que los agentes analizan y esperan. Cada comprobación descartada queda escrita en su Actividad."],
      ["¿Qué significa 1R?", "R es lo que un agente arriesga entre la entrada y su stop de protección. −1R es un stop completo; +3R es tres veces lo arriesgado. Medir en R compara agentes con justicia sea cual sea el tamaño de la cuenta."],
      ["¿Por qué pierden la mayoría de operaciones?", "Es una estrategia de tendencia: unas 2 de cada 3 operaciones son pérdidas pequeñas y una minoría corre varias R. En el estudio 2022-2026 la media fue +0,62R por operación tras comisiones de Strike, la comisión de Smart Flow (0,20 % por ejecución) y el deslizamiento. Es una simulación histórica, no una promesa."],
      ["¿Por qué un agente está quieto?", "Porque está esperando su setup. Smart Flow solo mira el mercado al cierre de cada vela (cada 4 horas por defecto), así que entre medias no hay nada que hacer. Los agentes solo caminan cuando pasa algo real: el cierre de una vela los lleva al Signal Lab, una orden al Exchange, una operación cerrada al Cafe (o al Liquidation Alley si saltó su stop) y una señal rechazada a la Risk Office."],
      ["¿Qué significan los edificios?", "Plaza: agentes esperando un setup. Signal Lab: el análisis al cierre de cada vela. Torres de mercado: agentes con una operación abierta en ese mercado. Strike Exchange: adonde va un agente cuando envía una orden. Risk Office: adonde va cuando el motor de riesgo rechaza una señal. Funding Cafe: tras cerrar una operación; Liquidation Alley: si se cerró en su stop. Agent Homes: agentes en pausa o desconectados, y los que esperan un depósito."],
      ["¿Por qué un agente dice \"Esperando un depósito\"?", "Su dueño lo conectó a Strike, pero la cuenta de Strike todavía no tiene saldo. No envía órdenes ni paga nada; en cuanto llega un depósito toma las siguientes señales él solo, sin reiniciar nada. Un depósito nunca cuenta como parte de su resultado."],
      ["¿Qué muestra la fuente?", "El color sigue el funding de BTC en Strike: menta cuando los largos pagan a los cortos, rojo cuando los cortos pagan a los largos."],
      ["¿Son reales estos agentes?", "Sí. Los agentes de Smart Flow funcionan 24/7 en papel con precios de Strike: las dos estrategias que pueden elegir los usuarios (Smart Flow y Smart Flow Pyramid) y las variantes en prueba. Los demás son de usuarios de Strike que han querido mostrar el suyo; los que llevan la etiqueta Real operan su propia cuenta de Strike. Todo lo que muestran sale de sus diarios y, en los reales, de su cuenta de Strike."],
      ["¿Puedo añadir mi agente?", "Sí: pulsa \"Pon tu propio agente en la ciudad\" en Ranking, conecta tu wallet de Cardano, crea tu personaje, elige la estrategia y firma el mensaje de Strike. Tu agente opera tu propia cuenta de Strike con un stop en cada operación; marca \"Mostrar mi agente en EdgeCraft-StrikeCity\" para aparecer aquí con el nombre que elijas."],
    ],
  },
  legend: { title: "Burbujas" },
  roadmap: { title: "Hoja de ruta", live: "Activo", next: "Siguiente", later: "Más adelante", items: {
    live: ["Motor Smart Flow, verificado vela a vela contra TradingView", "Dos estrategias: Smart Flow y Smart Flow Pyramid",
      "Agentes que operan la propia cuenta de Strike de su dueño (builder code)", "EdgeCraft-StrikeCity en vivo, con la cartera real de cada agente"],
    next: ["Más mercados a medida que demuestren ventaja después de costes", "Estrategias nuevas con ventaja propia", "Alertas en el móvil"],
    later: ["Vault de Smart Flow en Strike", "Competiciones de clanes"],
  } },
  scale: { title: "Escala del enjambre", level: (l: number, n: number) => `Nivel ${l} de ${n}`, next: (goal: number) => `siguiente con ${goal} agentes`,
    names: ["Chispa", "Equipo", "Manada", "Enjambre", "Colmena", "Red"] },
  zoomIn: "Acercar", zoomOut: "Alejar", recenter: "Centrar", canvas: (live: number, trade: number) =>
    `Mapa de EdgeCraft-StrikeCity con ${live} agentes en línea, ${trade} en operación. Usa las flechas para moverte y + o − para el zoom. Los paneles Agentes y Actividad muestran la misma información.`,
  building: { agentsHere: (n: number) => `${n} agentes aquí`, close: "Cerrar" },
  buildings: {
    lab: "Los agentes vienen aquí al cierre de cada vela a analizar los gráficos: rango, desplazamiento, volumen y tendencia diaria.",
    btc: "Aquí están los agentes con una operación abierta en BTC-USD. El cartel muestra el precio de Strike en vivo.",
    eth: "Aquí están los agentes con una operación abierta en ETH-USD. El cartel muestra el precio de Strike en vivo.",
    sol: "Aquí están los agentes con una operación abierta en SOL-USD. El cartel muestra el precio de Strike en vivo.",
    alts: "Aquí están los agentes con una operación abierta en XRP, BNB, ADA, NEAR o ZEC.",
    risk: "Cada orden pasa antes por el motor de riesgo: spread, límite de pérdida diaria, posiciones abiertas, frescura de datos. Un agente viene aquí cuando rechaza una señal.",
    alley: "Adonde va un agente cuando una operación se cierra en su stop de protección: una pérdida prevista, colocada en Strike junto con la entrada.",
    exchange: "Un agente viene aquí cuando envía una orden a Strike Finance. La pantalla muestra las últimas 48 horas de BTC y el libro de órdenes.",
    vault: "Vaults de Strike. Un vault de Smart Flow está en la hoja de ruta.",
    clan: "Clanes y competiciones de Strike. Más adelante.",
    homes: "Los agentes en pausa o desconectados, y los que esperan un depósito, descansan aquí hasta que vuelven a funcionar.",
    hq: "Smart Flow HQ, el builder detrás de los agentes.",
    cafe: "Los agentes pasan aquí un momento tras cerrar una operación (si no fue en su stop).",
    arena: "La clasificación: abre Ranking para verla.",
  },
  ev: {
    check: (m: string, parts: string) => `Sin operación en ${m}: ${parts}.`,
    part: {
      range: (v: string, min: string) => `rango de la vela ${v} ATR (necesita ${min})`,
      body: (v: string, min: string) => `cuerpo del ${v}% de la vela (necesita ${min}%)`,
      inside: (n: string) => `cierre dentro del rango de ${n} velas`,
      against_candle: () => "la vela de ruptura cierra contra su propia dirección",
      volume: (v: string | null, min: string) => v ? `volumen ${v}× su media (necesita ${min}×)` : "la media de volumen aún se está calculando",
      bias: (side: string) => `setup de ${side === "long" ? "compra" : "venta"} contra la tendencia diaria`,
      wide_range: (span: string, max: string) => `señal nacida dentro de un rango amplio (${span} ATR, filtro ${max})`,
      skipped: () => "señal descartada por un filtro",
      warmup: () => "indicadores aún calentando",
      none: () => "sin setup",
    } as CityText["ev"]["part"],
    not_traded: (m: string) => `Señal en ${m} no operada: vela atrasada o datos poco fiables.`,
    risk_weekly: () => "Señal descartada por el motor de riesgo: límite de pérdida semanal alcanzado.",
    risk_other: (why: string) => `Señal descartada por el motor de riesgo: ${why}.`,
    not_filled: (m: string) => `Orden en ${m} no ejecutada dentro del precio de protección: no se abrió nada.`,
    alert: (msg: string) => `Alerta operativa: ${msg}`,
    alertRead: (code: string) => `Strike no respondió cuando el agente revisó su cuenta${code ? ` (error ${code})` : ""}. Lo vuelve a intentar solo en menos de un minuto.`,
    alertStrike: (code: string) => `Strike no respondió al agente por un momento${code ? ` (error ${code})` : ""}. Lo vuelve a comprobar solo.`,
    exitReason: { trail: "cierre de vuelta dentro del canal de 10 velas", stop: "stop de protección", chandelier: "stop que siguió al precio (4 ATR)", target: "objetivo alcanzado",
      time: "límite de velas alcanzado", flow: "cruce del money flow", test: "fin de la prueba (2 min)", other: "cerrada en el exchange" },
    no_range: (m: string) => `Sin operación en ${m}: el cierre está dentro del rango de 20 velas.`,
    no_body: (m: string) => `Sin operación en ${m}: ruptura sin desplazamiento (cuerpo por debajo del 60% del rango).`,
    low_volume: (m: string, v: string) => `Sin operación en ${m}: volumen de solo ${v}× su media de 20 velas (necesita 1,5×).`,
    against_trend: (m: string) => `Sin operación en ${m}: la ruptura va contra la estructura diaria.`,
    signal: (m: string, side: string, p: string, v: string) => `Señal de ${side === "long" ? "COMPRA" : "VENTA"} en ${m} @ ${p}: cierre más allá del ${side === "long" ? "máximo" : "mínimo"} de 20 velas con ${v}× de volumen.`,
    risk_spread: (bps: string) => `Señal descartada por el motor de riesgo: spread de ${bps} pb, por encima del límite de 10 pb.`,
    risk_daily: () => "Señal descartada por el motor de riesgo: límite de pérdida diaria alcanzado.",
    risk_open: () => "Señal descartada por el motor de riesgo: ya hay una posición abierta en este mercado.",
    risk_min: (n: string, min: string) => `Señal descartada: con este saldo la orden sería de ${n}, por debajo del mínimo de Strike de ${min}. Mantén al menos 150 $ en la cuenta (300 $ con el riesgo conservador) para que el agente pueda tomar sus señales.`,
    risk_balance: () => "Señal descartada: su cuenta de Strike todavía no tiene saldo. En cuanto su dueño deposite (al menos 150 $; 300 $ con el riesgo conservador) tomará las siguientes señales él solo.",
    risk_hold: () => "Señal descartada: esta estrategia está en pausa de seguridad porque sus resultados reales han quedado claramente por debajo del backtest. Las operaciones abiertas mantienen su stop; las nuevas esperan a que Smart Flow la revise.",
    test_funds: (needs: string, avail: string | null) => `La prueba no se pudo hacer: necesita al menos ${needs} disponibles en la cuenta de Strike y ${avail ? `hay ${avail}` : "no hay nada"}. Deposita en Strike y vuelve a probar.`,
    test_busy: () => "La prueba no se pudo hacer ahora: todos los mercados estaban ocupados (una operación abierta, sin datos recientes o con el spread alto). Vuelve a intentarlo en unos minutos.",
    open: (side: string, m: string, p: string, s: string) => `Abrió ${side === "long" ? "LARGO" : "CORTO"} ${m} @ ${p} con el stop en ${s} (−1R) en Strike.`,
    held: (side: string, m: string, p: string) => `Su cuenta de Strike tiene un ${side === "long" ? "LARGO" : "CORTO"} en ${m} @ ${p} que no abrió el agente (sin stop del agente).`,
    close: (side: string, m: string, r: string, reason: string) => `Cerró ${side === "long" ? "LARGO" : "CORTO"} ${m}: ${r} (${reason}).`,
    pause: () => "Pausado por su dueño.",
    resume: () => "Reanudado por su dueño.",
    start: () => "Iniciado por su dueño.",
    live: () => "Ahora opera en la propia cuenta de Strike de su dueño.",
    settings: () => "Su dueño cambió su estrategia, sus mercados o su riesgo.",
    test: () => "Su dueño pidió una operación de prueba.",
    test_open: (m: string, p: string, s: string) => `Operación de prueba pedida por su dueño: compró el mínimo de ${m} @ ${p} con el stop en ${s} en Strike.`,
    test_close: (m: string, p: string) => `Operación de prueba cerrada: vendió ${m} @ ${p}. El agente la abrió, la protegió y la cerró él solo.`,
    account_fill: (side: string, m: string, p: string) => `En su cuenta de Strike, fuera del agente: ${side === "buy" ? "COMPRA" : "VENTA"} ${m} @ ${p}.`,
    live_off: () => "Detenido: su dueño paró sus operaciones en Strike.",
    why: {
      analysis: "Smart Flow solo opera rupturas fuertes y con volumen, a favor de la tendencia del marco superior.",
      signal: "Vela de desplazamiento de al menos 1 ATR con un cuerpo del 60%, a favor de la estructura diaria.",
      risk: "El motor de riesgo revisa cada orden antes de que llegue a Strike.",
      order: "El tamaño hace que el stop cueste el riesgo elegido por operación.",
    },
    invalidates: "Un cierre de vuelta dentro del canal de 10 velas, o el stop en Strike: a 1,5 ATR al principio, y después siguiendo al precio 4 ATR por debajo del máximo alcanzado.",
    next: "Próxima comprobación al cierre de su siguiente vela.",
  },
  ago: (s: number) => s < 60 ? `hace ${Math.max(1, Math.round(s))} s` : s < 3600 ? `hace ${Math.round(s / 60)} min` : s < 86400 ? `hace ${Math.round(s / 3600)} h` : `hace ${Math.round(s / 86400)} d`,
  inTime: (s: number) => s <= 60 ? "en menos de un minuto" : s < 3600 ? `en ${Math.round(s / 60)} min` : `en ${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`,
};

export const cityText: Record<Lang, CityText> = { en, es };
export type { CityText };

/** Journal entry → sentence (+ explanation fields for the Activity tab). */
/** An operational alert as people read it: Strike not answering, in plain words, and never its raw answer (an HTML
 *  error page). The agent's journal keeps the full message for the audit. */
function alertText(raw: string, T: CityText): string {
  const m = /HttpError\(status=(\d+)|HTTP (\d{3})/.exec(raw);
  const code = m ? (m[1] ?? m[2]) : "";
  const down = (code && (Number(code) >= 500 || code === "429")) || /timed out|URLError|ConnectionError|TimeoutError|RemoteDisconnected/i.test(raw);
  if (down) return /read failed|unavailable/i.test(raw) ? T.ev.alertRead(code) : T.ev.alertStrike(code);
  return T.ev.alert(raw.split("body=")[0].replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").replace(/[\s(:,]+$/, "").trim().slice(0, 160));
}

export function describe(d: Decision, T: CityText, lang: Lang): { text: string; why?: string; invalidates?: string; next?: string } {
  const a = d.args ?? {};
  const m = ticker(d.market);
  const p = (k: string) => fmtPrice(Number(a[k] ?? 0), lang);
  const num = (k: string) => Number(a[k] ?? 0).toLocaleString(lang === "es" ? "es-ES" : "en-US");
  const fix = (k: string, d: number) => Number(a[k] ?? 0).toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const has = (k: string) => a[k] !== undefined && a[k] !== null && Number.isFinite(Number(a[k]));
  switch (d.code) {
    case "check": {
      const P = T.ev.part;
      const parts = String(a.r ?? "").split(",").filter(Boolean).map((r) => {
        switch (r) {
          case "range": return P.range(fix("range", 2), fix("rmin", 1));
          case "body": return P.body(num("body"), num("bmin"));
          case "inside": return P.inside(num("n"));
          case "volume": return P.volume(has("vol") ? fix("vol", 2) : null, fix("vmin", 1));
          case "bias": return P.bias(String(a.side));
          case "wide_range": return P.wide_range(fix("span", 1), fix("fmax", 0));
          case "unknown": return d.text ?? P.none();
          default: return (P[r] ?? P.none)();
        }
      });
      return { text: T.ev.check(m, parts.join("; ") || P.none()), why: T.ev.why.analysis, next: T.ev.next };
    }
    case "not_traded": return { text: T.ev.not_traded(m), why: T.ev.why.risk };
    case "risk_weekly": return { text: T.ev.risk_weekly(), why: T.ev.why.risk };
    case "risk_other": return { text: T.ev.risk_other(d.text ?? ""), why: T.ev.why.risk };
    case "not_filled": return { text: T.ev.not_filled(m), why: T.ev.why.risk };
    case "risk_min": return { text: T.ev.risk_min(has("notional") ? `${num("notional")} $` : "—", has("min") ? `${num("min")} $` : "10 $"), why: T.ev.why.risk };
    case "alert": return { text: alertText(d.text ?? "", T) };
    case "risk_balance": case "risk_hold": return { text: T.ev[d.code](), why: T.ev.why.risk };
    case "test_funds": {
      const usd = (k: string) => Number(a[k] ?? 0).toLocaleString(lang === "es" ? "es-ES" : "en-US", { style: "currency", currency: "USD" });
      // the agent always says what the smallest test needs (agent/runner.py test_trade)
      return { text: T.ev.test_funds(usd("needs"), Number(a.available ?? 0) > 0 ? usd("available") : null) };
    }
    case "test_busy": return { text: T.ev.test_busy() };
    case "no_range": case "no_body": case "against_trend":
      return { text: T.ev[d.code](m), why: T.ev.why.analysis, next: T.ev.next };
    case "low_volume": return { text: T.ev.low_volume(m, num("vol")), why: T.ev.why.analysis, next: T.ev.next };
    case "signal": return { text: T.ev.signal(m, String(a.side), p("price"), has("vol") ? num("vol") : "—"), why: T.ev.why.signal, invalidates: T.ev.invalidates };
    case "risk_spread": return { text: T.ev.risk_spread(num("bps")), why: T.ev.why.risk };
    case "risk_daily": case "risk_open": return { text: T.ev[d.code](), why: T.ev.why.risk };
    case "open": return { text: T.ev.open(String(a.side), m, p("price"), has("stop") ? p("stop") : "—"), why: T.ev.why.order, invalidates: T.ev.invalidates };
    case "held": return { text: T.ev.held(String(a.side), m, p("price")) };
    case "close": return { text: T.ev.close(String(a.side), m, fmtR(Number(a.r), lang), T.ev.exitReason[String(a.reason)] ?? T.ev.exitReason.other) };
    case "pause": case "resume": case "start": case "live": case "live_off": case "settings": case "test": return { text: T.ev[d.code]() };
    case "test_open": return { text: T.ev.test_open(m, p("price"), has("stop") ? p("stop") : "—") };
    case "test_close": return { text: T.ev.test_close(m, p("price")) };
    case "account_fill": return { text: T.ev.account_fill(String(a.side), m, p("price")) };
  }
}
