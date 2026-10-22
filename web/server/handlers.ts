// EdgeCraft-StrikeCity API on Cloudflare Pages Functions. Public: info, city. Wallet owners: connect (paper agent), me,
// actions — every change needs a fresh CIP-30 signature over a one-time message. Agents' host: internal/push (HMAC).
// Thin route files under ../functions/api call these.
/// <reference path="./env.d.ts" />
import { REFERENCE_ID, liveAgent, meView, startingAgent, stoppedAgent, storedLook, storedPersona, strikePrices, userAgent, type Agent, type CityDoc } from "./agents";
import { burnKey, finishLink, inviteOnly, linkFor, liveAllowed, liveEnv, liveFee, liveForAll, liveView, startLink, walletNetwork } from "./live";
import { copyView, copying, normalizePlan, planLines, savePlan, type CopyPlan } from "./copyplan";
import { lookId, normalizeLook } from "../src/city/look";
import { normalizePersona, personaId } from "../src/city/persona";
import { isAdmin } from "./feedback";
import { parseAddress, verifyCip30 } from "./cardano";
import { addEvent, audit, auditNow, consumeChallenge, eventsFor, newChallenge, publicUsers, saveSnapshot, snapshot, snapshotAt, tooMany, userById } from "./store";
import {
  CHALLENGE_TTL, MARKETS, RISK, STRATEGIES, riskAllowed, strategyOf, body, cityCacheKey, cleanMarkets, cleanName, edgeCache, fail, hmacHex, ip, issueToken,
  json, readToken, sameText, sha256Hex, type UserRow,
} from "./util";

/** The host pushes the official agents and, under the user's id, the real agent of each user connected to Strike. */
const split = (doc: CityDoc) => ({
  official: doc.agents.filter((a) => !a.id.startsWith("u-")),
  live: new Map<string, Agent>(doc.agents.filter((a) => a.id.startsWith("u-")).map((a) => [a.id, a])),
});

/** Users (of `ids`) whose agent trades their own Strike account on this site's network. */
async function linkedUsers(env: Env, ids: string[]): Promise<Set<string>> {
  if (!ids.length || !env.BUILDER_CODE) return new Set();
  try {
    const rows = (await env.DB.prepare("SELECT user_id FROM live_links WHERE status = 'active' AND env = ?1").bind(liveEnv(env)).all<{ user_id: string }>()).results;
    const want = new Set(ids);
    return new Set(rows.map((r) => r.user_id).filter((x) => want.has(x)));
  } catch { return new Set(); }
}

/** The official paper agent a user's paper agent follows: the one of the strategy they picked. */
const refOf = (official: Agent[], u: UserRow) =>
  official.find((a) => a.id === STRATEGIES[strategyOf(u.strategy)].ref) ?? official.find((a) => a.id === REFERENCE_ID);

const iso = (t: number) => new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
const userIdFor = async (address: string) => "u-" + (await sha256Hex(address)).slice(0, 12);
const purgeCity = (c: Ctx) => c.waitUntil(edgeCache().delete(cityCacheKey(c.request)).catch(() => false));

/** The smallest test trade Strike allows needs about this much available (agent/runner.py test_trade: ~11 $ + 5 %). */
const TEST_MIN_AVAILABLE = 12;

export async function info({ env }: Ctx): Promise<Response> {
  const doc = await snapshot(env.DB, Date.now()).catch(() => null);
  return json({
    env: liveEnv(env), builderCode: "", feeBps: 20, takerFeeBps: 5, markets: MARKETS, riskPresets: RISK,
    agentHealthy: !!doc && doc.agents.some((a) => a.status !== "offline"), engine: doc?.engine ?? "1.0.0",
    // when the agents' host last pushed (its watchdog and the external one alert when this gets old) and the
    // strategies on a safety hold
    pushedAt: await snapshotAt(env.DB).catch(() => null), holds: doc?.holds ?? {},
    connect: false, paper: true,   // agents start on paper; real trading is a separate opt-in (live)
    live: { env: liveEnv(env), enabled: liveForAll(env), invite: inviteOnly(env), feeBps: liveFee(env), code: env.BUILDER_CODE ?? "" },
    copyPilot: env.COPY_PILOT === "1",   // copy with your agent is open here
  }, 200, "public, max-age=30");
}

export async function city(c: Ctx): Promise<Response> {
  const cache = edgeCache(), key = cityCacheKey(c.request);
  const hit = await cache.match(key).catch(() => undefined);
  if (hit) return hit;
  const now = Date.now();
  const doc = await snapshot(c.env.DB, now);
  if (!doc) return json({ generated: now, engine: "1.0.0", agents: [] }, 200, "public, max-age=0, s-maxage=15");
  const users = await publicUsers(c.env.DB);
  const ev = await eventsFor(c.env.DB, users.map((u) => u.id));
  const { official, live } = split(doc);
  const linked = await linkedUsers(c.env, users.map((u) => u.id));
  const copies = await copying(c.env.DB, users.map((u) => u.id), liveEnv(c.env));   // whom each one's agent copies on Strike
  // only public users appear; a connected one shows its real agent (starting, until the host pushes it). Where real
  // trading is open to everyone one that stopped is shown stopped; only invite-only sites still have paper agents,
  // which follow their strategy's paper agent
  const forAll = liveForAll(c.env);
  const mine = users.map((u) => {
    const a = live.get(u.id), evs = ev.get(u.id) ?? [];
    if (a) return { ...liveAgent(u, a, evs), copy: copies.get(u.id) };
    if (linked.has(u.id)) return { ...startingAgent(u, liveEnv(c.env), evs, now), portfolio: undefined };
    return forAll ? stoppedAgent(u, liveEnv(c.env), evs, now) : userAgent(u, refOf(official, u), evs, now);
  });
  // browsers always ask again (an owner who hides their agent must see it gone); the edge copy is purged on changes
  const res = json({ ...doc, agents: [...official, ...mine] }, 200, "public, max-age=0, s-maxage=30");
  c.waitUntil(cache.put(key, res.clone()).catch(() => undefined));
  return res;
}

export async function connectChallenge({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const b = await body<{ address?: unknown; chain?: unknown; risk?: unknown; markets?: unknown; name?: unknown; public?: unknown; look?: unknown;
    persona?: unknown; strategy?: unknown; signin?: unknown }>(request);
  if (!b) return fail(400, "invalid request");
  if (b.chain !== undefined && b.chain !== "cardano") return fail(400, "only Cardano wallets are supported");
  let address: string;
  try {
    const a = parseAddress(String(b.address ?? ""));
    if (a.network !== walletNetwork(env)) return fail(400, `switch your wallet to Cardano ${liveEnv(env) === "mainnet" ? "mainnet" : "Preprod (testnet)"}`);
    address = a.bech32;
  } catch { return fail(400, "invalid Cardano address"); }
  // a wallet that already has an agent only signs in to it: nothing about the agent changes
  const uid = await userIdFor(address);
  const prev = await userById(env.DB, uid);
  if (prev || b.signin === true) {
    if (!prev) return fail(404, "this wallet has no agent yet: create one");
    if (await tooMany(env.DB, ip(request), address, "connect", now)) return fail(429, "too many attempts: wait a few minutes");
    return signInChallenge(env, request, prev, address, now);
  }
  const name = cleanName(b.name);
  if (!name) return fail(400, "choose a name of 2 to 24 letters or numbers (names with Smart Flow or Strike are reserved)");
  const markets = cleanMarkets(b.markets);
  if (!markets) return fail(400, "choose at least one market");
  const risk = typeof b.risk === "string" && b.risk in RISK ? b.risk : null;
  if (!risk) return fail(400, "invalid risk level");
  const pub = b.public === true;
  const strategy = strategyOf(b.strategy);
  if (b.strategy !== undefined && b.strategy !== strategy) return fail(400, "unknown strategy");
  if (!riskAllowed(strategy, risk)) return fail(400, `${STRATEGIES[strategy].name} goes up to the ${STRATEGIES[strategy].maxRisk} risk (${RISK[STRATEGIES[strategy].maxRisk]}% per trade)`);
  const look = b.look === undefined || b.look === null ? null : normalizeLook(b.look);
  if (b.look && !look) return fail(400, "invalid character");
  const persona = b.persona === undefined || b.persona === null ? null : normalizePersona(b.persona);
  if (b.persona && !persona) return fail(400, "invalid personality");
  if (await tooMany(env.DB, ip(request), address, "connect", now)) return fail(429, "too many attempts: wait a few minutes");
  const id = crypto.randomUUID();
  const payload = { name, markets, risk, public: pub, look, persona, strategy };
  // where real trading is offered, creating the agent IS connecting it: the only message is Strike's builder connect
  // (it names the wallet and a nonce, so it also proves ownership)
  const link = env.BUILDER_CODE ? await linkFor(env.DB, uid) : null;
  if (liveAllowed(env, address) && !(link && link.env === liveEnv(env))) {
    const st = await startLink(env, uid, address, markets, now);
    if (st instanceof Response) return st;
    await newChallenge(env.DB, { address, kind: "connect", payload: { ...payload, live: { pub: st.pub, nonce: st.nonce, env: st.env } }, message: st.message, ip: ip(request) }, id, now);
    return json({ sessionId: id, messageToSign: st.message, feeBps: liveFee(env), expiresAt: now + CHALLENGE_TTL, live: true });
  }
  const mode = !link ? "paper (no real money)" : link.status === "active" ? `your Strike ${link.env} account (already connected)`
    : liveForAll(env) ? "stopped (connect it to Strike again in My agent)" : "paper (real trading is off)";
  const message = [
    link ? "Smart Flow · sign in to my agent" : "Smart Flow · start my paper agent", "",
    "This signature only proves that you own this wallet.",
    "It cannot move funds, place orders or approve any fee.", "",
    `Wallet: ${address}`, `Agent name: ${name}`, `Strategy: ${STRATEGIES[strategy].name}`, `Markets: ${markets.join(", ")}`,
    `Risk per trade: ${RISK[risk]}%`,
    `Show in EdgeCraft-StrikeCity: ${pub ? "yes" : "no"}`, `Character: ${look ? lookId(look) : "automatic"}`,
    ...(persona ? [`Personality in the city: ${personaId(persona)} (never changes how it trades)`] : []), `Mode: ${mode}`,
    `Site: ${new URL(request.url).host}`, `Nonce: ${id}`, `Issued: ${iso(now)}`, `Expires: ${iso(now + CHALLENGE_TTL)}`,
  ].join("\n");
  await newChallenge(env.DB, { address, kind: "connect", payload, message, ip: ip(request) }, id, now);
  return json({ sessionId: id, messageToSign: message, feeBps: 0, expiresAt: now + CHALLENGE_TTL });
}

/** Signing in to an existing agent: proves the wallet, changes nothing. */
async function signInChallenge(env: Env, request: Request, u: UserRow, address: string, now: number): Promise<Response> {
  const id = crypto.randomUUID();
  const link = env.BUILDER_CODE ? await linkFor(env.DB, u.id) : null;
  const connected = !!link && link.status === "active" && link.env === liveEnv(env);
  const mode = connected ? `your Strike ${link.env} account (already connected)`
    : liveForAll(env) ? "stopped (connect it to Strike again in My agent)" : link ? "paper (real trading is off)" : "paper (no real money)";
  const message = [
    "Smart Flow · sign in to my agent", "",
    "This signature only proves that you own this wallet.",
    "It cannot move funds, place orders or approve any fee, and it changes nothing in your agent.", "",
    `Wallet: ${address}`, `Agent name: ${u.name}`, `Mode: ${mode}`,
    `Site: ${new URL(request.url).host}`, `Nonce: ${id}`, `Issued: ${iso(now)}`, `Expires: ${iso(now + CHALLENGE_TTL)}`,
  ].join("\n");
  await newChallenge(env.DB, { address, kind: "connect", payload: { signin: true }, message, ip: ip(request) }, id, now);
  return json({ sessionId: id, messageToSign: message, feeBps: 0, expiresAt: now + CHALLENGE_TTL, signin: true });
}

/** Right after a wallet connects: whether it already has an agent (then it only signs in) and may trade for real now. */
export async function walletStatus({ request, env }: Ctx): Promise<Response> {
  const raw = new URL(request.url).searchParams.get("address") ?? "";
  if (raw.length > 200) return fail(400, "invalid address");
  let address: string;
  try { address = parseAddress(raw).bech32; } catch { return fail(400, "invalid Cardano address"); }
  return json({ live: liveAllowed(env, address), env: liveEnv(env), agent: !!(await userById(env.DB, await userIdFor(address))) });
}

export async function connectVerify(c: Ctx): Promise<Response> {
  const { request, env } = c;
  const now = Date.now();
  const b = await body<{ sessionId?: unknown; walletSignature?: unknown }>(request);
  if (!b || typeof b.sessionId !== "string" || typeof b.walletSignature !== "string") return fail(400, "invalid request");
  const ch = await consumeChallenge(env.DB, b.sessionId, "connect", now);
  if (!ch) return fail(410, "this sign-in request expired or was already used: start again");
  const p = JSON.parse(ch.payload) as { name: string; markets: string[]; risk: string; public: boolean; look: unknown; persona?: unknown;
    strategy?: string; live?: { pub: string; nonce: string; env: string }; signin?: boolean };
  const why = await verifyCip30(ch.address, b.walletSignature, new TextEncoder().encode(ch.message));
  const id = await userIdFor(ch.address);
  const proof = { user: id, address: ch.address, action: p.signin ? "signin" : "create", message: ch.message, signature: b.walletSignature };
  if (why) {
    if (p.live) await burnKey(env, p.live.pub, now);
    await auditNow(env.DB, request, liveEnv(env), { ...proof, ok: false, detail: { error: `invalid wallet signature (${why})` } }, now);
    return fail(401, `the wallet signature is not valid (${why})`);
  }
  if (p.signin) {   // the agent as it is: the page needs its settings for My agent
    const u = await userById(env.DB, id);
    if (!u) {
      await auditNow(env.DB, request, liveEnv(env), { ...proof, ok: false, detail: { error: "no agent for this wallet" } }, now);
      return fail(404, "this agent no longer exists");
    }
    await auditNow(env.DB, request, liveEnv(env), { ...proof, ok: true, detail: { name: u.name } }, now);
    const link = env.BUILDER_CODE ? await linkFor(env.DB, id) : null;
    const t = await issueToken(env.SESSION_SECRET, id, now);
    return json({
      accountId: id, apiWalletPublicKey: "", token: t.token, expiresAt: iso(t.exp), cityId: id, signin: true,
      mode: link && link.status === "active" && link.env === liveEnv(env) ? "live" : liveForAll(env) ? "live" : "paper",
      live: env.BUILDER_CODE ? liveView(env, link, liveAllowed(env, u.address)) : undefined,
      agent: { name: u.name, markets: JSON.parse(u.markets) as string[], risk: u.risk, public: !!u.public, look: storedLook(u),
        persona: storedPersona(u), strategy: strategyOf(u.strategy) },
    });
  }
  const look = normalizeLook(p.look);
  const persona = normalizePersona(p.persona);
  // the same signature goes to Strike, which links the user's account to our API wallet (nothing is saved if it fails)
  const linkStmts = p.live ? await finishLink(env, id, { ...p.live, address: ch.address }, b.walletSignature, now,
    { req: request, message: ch.message }) : [];
  if (linkStmts instanceof Response) return linkStmts;   // refused by Strike: finishLink recorded why
  const prev = await userById(env.DB, id);
  const stmts = [env.DB.prepare(
    "INSERT INTO users (id, address, name, risk, markets, public, status, created_at, updated_at, look, strategy, persona) VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'active', ?7, ?7, ?8, ?9, ?10) "
    + "ON CONFLICT(id) DO UPDATE SET name = excluded.name, risk = excluded.risk, markets = excluded.markets, public = excluded.public, "
    + "updated_at = excluded.updated_at, look = COALESCE(excluded.look, users.look), strategy = excluded.strategy, persona = COALESCE(excluded.persona, users.persona)",
  ).bind(id, ch.address, p.name, p.risk, JSON.stringify(p.markets), p.public ? 1 : 0, now, look ? JSON.stringify(look) : null,
    strategyOf(p.strategy), persona ? JSON.stringify(persona) : null)];
  if (!prev) stmts.push(addEvent(env.DB, id, "start", now));
  else if (!!prev.public !== p.public) stmts.push(addEvent(env.DB, id, p.public ? "show" : "hide", now));
  stmts.push(audit(env.DB, request, liveEnv(env), { ...proof, ok: true, detail: {
    name: p.name, strategy: strategyOf(p.strategy), markets: p.markets, risk: p.risk, riskPct: RISK[p.risk] ?? null, public: p.public,
    look: look ? lookId(look) : null, persona: persona ? personaId(persona) : null, live: !!p.live, replaced: prev ? { name: prev.name, strategy: prev.strategy, markets: JSON.parse(prev.markets), risk: prev.risk } : null,
  } }, now));
  await env.DB.batch([...stmts, ...linkStmts]);
  purgeCity(c);
  const t = await issueToken(env.SESSION_SECRET, id, now);
  const live = p.live ? liveView(env, await linkFor(env.DB, id), true) : undefined;
  // its citizen number in the city (the row's order of arrival: "Meet <name>, citizen #0042")
  const citizen = (await env.DB.prepare("SELECT rowid AS n FROM users WHERE id = ?1").bind(id).first<{ n: number }>())?.n ?? null;
  return json({ accountId: id, apiWalletPublicKey: "", token: t.token, expiresAt: iso(t.exp), cityId: id, mode: live ? "live" : "paper", live, citizen });
}

async function meFor(env: Env, id: string, now: number): Promise<Response> {
  const u = await userById(env.DB, id);
  if (!u) return fail(404, "this agent no longer exists");
  const doc = await snapshot(env.DB, now);
  const parts = doc ? split(doc) : null;
  const ref = parts ? refOf(parts.official, u) : undefined;
  const events = (await eventsFor(env.DB, [id])).get(id) ?? [];
  const real = parts?.live.get(id);
  const link = await linkFor(env.DB, id);
  const connected = !!link && link.status === "active" && link.env === liveEnv(env);
  // stopped by its owner: shown stopped at once, not as the host's last push (it stops within ~10 s)
  const a = real && (connected || !liveForAll(env)) ? liveAgent(u, real, events, true)   // the owner sees the amounts
    : connected ? startingAgent(u, liveEnv(env), events, now)
    : liveForAll(env) ? stoppedAgent(u, liveEnv(env), events, now) : userAgent(u, ref, events, now);
  // agent: the owner's own agent as the city draws it, with the amounts (the city shows it to its owner this way);
  // hold: its strategy's safety hold, if any (new trades wait; open ones keep their stop)
  return json({ ...meView(u, a, a.positions.length ? await strikePrices() : {}), live: liveView(env, await linkFor(env.DB, id), liveAllowed(env, u.address)),
    admin: isAdmin(env, id),   // reads the site's suggestions (My agent's inbox)
    agent: a, hold: doc?.holds?.[strategyOf(u.strategy)] ?? null,
    copy: env.COPY_PILOT === "1" ? await copyView(env.DB, id, liveEnv(env)) : undefined });   // copy with your agent: the signed plan and how it goes
}

export async function me({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const id = await readToken(env.SESSION_SECRET, request, now);
  if (!id) return fail(401, "sign in again with your wallet");
  return meFor(env, id, now);
}

const ACTIONS: Record<string, string> = { pause: "pause", resume: "resume", revoke: "delete", show: "show in EdgeCraft-StrikeCity", hide: "hide from EdgeCraft-StrikeCity",
  look: "change the character of", settings: "change the strategy, markets and risk of", test: "run a test trade with",
  copy: "set the copy trading of" };

export async function actionChallenge({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const b = await body<{ accountId?: unknown; action?: unknown; look?: unknown; persona?: unknown; strategy?: unknown; markets?: unknown; risk?: unknown; copy?: unknown }>(request);
  if (!b || typeof b.accountId !== "string" || typeof b.action !== "string" || !(b.action in ACTIONS)) return fail(400, "invalid request");
  let copy: CopyPlan | null = null;
  if (b.action === "copy") {
    const v = normalizePlan(b.copy, now);
    if (typeof v === "string") return fail(400, v);
    copy = v;
  }
  const look = b.action === "look" && b.look != null ? normalizeLook(b.look) : null;
  const persona = b.action === "look" && b.persona != null ? normalizePersona(b.persona) : null;
  if (b.action === "look" && ((b.look != null && !look) || (b.persona != null && !persona) || (!look && !persona))) return fail(400, "invalid character");
  const u = await userById(env.DB, b.accountId);
  if (!u) return fail(404, "this agent no longer exists");
  let settings: { strategy: string; markets: string[]; risk: string } | null = null;
  if (b.action === "settings") {
    const markets = cleanMarkets(b.markets);
    const risk = typeof b.risk === "string" && b.risk in RISK ? b.risk : null;
    if (!markets || !risk || (b.strategy !== undefined && strategyOf(b.strategy) !== b.strategy)) return fail(400, "invalid settings");
    const strategy = strategyOf(b.strategy);
    if (!riskAllowed(strategy, risk)) return fail(400, `${STRATEGIES[strategy].name} goes up to the ${STRATEGIES[strategy].maxRisk} risk (${RISK[STRATEGIES[strategy].maxRisk]}% per trade)`);
    settings = { strategy, markets, risk };
  }
  if (b.action === "copy") {   // the copy runs with the agent's API wallet: it must be connected to Strike here
    if (env.COPY_PILOT !== "1") return fail(409, "copying with your agent is not open on this site yet");
    const link = await linkFor(env.DB, u.id);
    if (!link || link.status !== "active" || link.env !== liveEnv(env)) return fail(409, "connect your agent to Strike first");
  }
  if (b.action === "test") {
    const link = await linkFor(env.DB, u.id);
    if (!link || link.status !== "active" || link.env !== liveEnv(env)) return fail(409, "connect your agent to Strike first");
    if (link.env !== "mainnet") return fail(409, "test trades run on mainnet only (Strike testnet cannot close positions)");
    // the agent would refuse it anyway: say so before the owner signs (its account as the host last read it)
    const real = await snapshot(env.DB, now).then((d) => (d ? split(d).live.get(u.id) : undefined)).catch(() => undefined);
    const avail = real?.portfolio?.available;
    if (avail != null && avail < TEST_MIN_AVAILABLE) {
      return fail(409, `the test trade needs about ${TEST_MIN_AVAILABLE} $ available in your Strike account (it has ${avail.toFixed(2)} $): deposit in Strike first`);
    }
  }
  if (await tooMany(env.DB, ip(request), u.address, "action", now)) return fail(429, "too many attempts: wait a few minutes");
  const id = crypto.randomUUID();
  const message = [
    `Smart Flow · ${ACTIONS[b.action]} my agent`, "",
    b.action === "test"
      ? "My agent opens the smallest trade Strike allows (about 11 $) with its stop, holds it about 2 minutes and closes it. It costs a few cents in fees."
      : copy ? planLines(copy).join("\n")
      : "This signature only proves that you own this wallet.", "",
    `Wallet: ${u.address}`, `Agent: ${u.name}`, `Action: ${b.action}`, ...(look ? [`Character: ${lookId(look)}`] : []),
    ...(persona ? [`Personality in the city: ${personaId(persona)} (never changes how it trades)`] : []),
    ...(settings ? [`Strategy: ${STRATEGIES[settings.strategy].name}`, `Markets: ${settings.markets.join(", ")}`, `Risk per trade: ${RISK[settings.risk]}%`] : []),
    `Site: ${new URL(request.url).host}`, `Nonce: ${id}`, `Issued: ${iso(now)}`, `Expires: ${iso(now + CHALLENGE_TTL)}`,
  ].join("\n");
  await newChallenge(env.DB, { address: u.address, kind: "action", payload: { action: b.action, id: u.id, look, persona, settings, copy }, message, ip: ip(request) }, id, now);
  return json({ sessionId: id, messageToSign: message, feeBps: 0, expiresAt: now + CHALLENGE_TTL });
}

export async function action(c: Ctx): Promise<Response> {
  const { request, env } = c;
  const now = Date.now();
  const b = await body<{ sessionId?: unknown; walletSignature?: unknown }>(request);
  if (!b || typeof b.sessionId !== "string" || typeof b.walletSignature !== "string") return fail(400, "invalid request");
  const ch = await consumeChallenge(env.DB, b.sessionId, "action", now);
  if (!ch) return fail(410, "this request expired or was already used: start again");
  const why = await verifyCip30(ch.address, b.walletSignature, new TextEncoder().encode(ch.message));
  const p = JSON.parse(ch.payload) as { action: string; id: string; look?: unknown; persona?: unknown; settings?: { strategy: string; markets: string[]; risk: string } | null;
    copy?: CopyPlan | null };
  const proof = { user: p.id, address: ch.address, action: p.action, message: ch.message, signature: b.walletSignature };
  if (why) {
    await auditNow(env.DB, request, liveEnv(env), { ...proof, ok: false, detail: { error: `invalid wallet signature (${why})` } }, now);
    return fail(401, `the wallet signature is not valid (${why})`);
  }
  const u = await userById(env.DB, p.id);
  if (!u || u.address !== ch.address) {
    await auditNow(env.DB, request, liveEnv(env), { ...proof, ok: false, detail: { error: "no agent for this wallet" } }, now);
    return fail(404, "this agent no longer exists");
  }
  const db = env.DB;
  const set = (sql: string, ...v: unknown[]) => db.prepare(`UPDATE users SET ${sql}, updated_at = ?1 WHERE id = ?2`).bind(now, u.id, ...v);
  const was = { name: u.name, status: u.status, public: !!u.public, strategy: strategyOf(u.strategy), markets: JSON.parse(u.markets) as string[], risk: u.risk };
  if (p.action === "revoke") {   // the agent goes; its audit rows stay
    // and nothing of it keeps running: its Strike connection goes off, and a copy it runs is stopped by the host
    // (copyplan.ts serves the plans of gone agents as "off" until the host reports no copy left)
    await db.batch([audit(db, request, liveEnv(env), { ...proof, ok: true, detail: { deleted: was } }, now),
      db.prepare("UPDATE live_links SET status = 'off', updated_at = ?2 WHERE user_id = ?1").bind(u.id, now),
      db.prepare("UPDATE copy_plans SET plan = json_set(plan, '$.mode', 'off'), version = version + 1, updated_at = ?2 WHERE user_id = ?1").bind(u.id, now),
      db.prepare("DELETE FROM events WHERE user_id = ?1").bind(u.id), db.prepare("DELETE FROM users WHERE id = ?1").bind(u.id)]);
    purgeCity(c);
    return json({ deleted: true });
  }
  const stmts: D1PreparedStatement[] = [];
  if (p.action === "pause" && u.status !== "paused") stmts.push(set("status = 'paused'"), addEvent(db, u.id, "pause", now));
  if (p.action === "resume" && u.status === "paused") stmts.push(set("status = 'active'"), addEvent(db, u.id, "resume", now));
  if (p.action === "show" && !u.public) stmts.push(set("public = 1"), addEvent(db, u.id, "show", now));
  if (p.action === "hide" && u.public) stmts.push(set("public = 0"), addEvent(db, u.id, "hide", now));
  const newLook = p.action === "look" ? normalizeLook(p.look) : null;
  if (newLook) stmts.push(set("look = ?3", JSON.stringify(newLook)));
  const newPersona = p.action === "look" ? normalizePersona(p.persona) : null;
  if (newPersona) stmts.push(set("persona = ?3", JSON.stringify(newPersona)));
  if (p.action === "settings" && p.settings) {
    stmts.push(set("strategy = ?3, markets = ?4, risk = ?5", p.settings.strategy, JSON.stringify(p.settings.markets), p.settings.risk),
      addEvent(db, u.id, "settings", now));
  }
  if (p.action === "test") {
    stmts.push(db.prepare("UPDATE live_links SET test_at = ?2, updated_at = ?2 WHERE user_id = ?1 AND status = 'active'").bind(u.id, now),
      addEvent(db, u.id, "test", now));
  }
  if (p.action === "copy" && p.copy) stmts.push(savePlan(db, u.id, liveEnv(env), p.copy, now));
  // every signed action is kept, also the ones that changed nothing (pausing a paused agent)
  stmts.push(audit(db, request, liveEnv(env), { ...proof, ok: true, detail: {
    changed: stmts.length > 0, before: was,
    ...(p.settings ? { ...p.settings, riskPct: RISK[p.settings.risk] ?? null } : {}), ...(newLook ? { look: lookId(newLook) } : {}), ...(newPersona ? { persona: personaId(newPersona) } : {}),
    ...(p.action === "test" ? { at: now } : {}), ...(p.copy ? { copy: p.copy } : {}),
  } }, now));
  await db.batch(stmts);
  purgeCity(c);
  return meFor(env, u.id, now);
}

/** The agents' host pushes the real agents' public snapshot: HMAC-SHA256 over "{ms}.{body}", 2 minute window. */
export async function push(c: Ctx): Promise<Response> {
  const { request, env } = c;
  const now = Date.now();
  const ts = request.headers.get("X-SF-Time") ?? "", sig = request.headers.get("X-SF-Signature") ?? "";
  if (!/^\d{13}$/.test(ts) || Math.abs(now - Number(ts)) > 120_000) return fail(401, "missing or stale timestamp");
  if (Number(request.headers.get("Content-Length") ?? 0) > 2_000_000) return fail(413, "snapshot too large");
  const raw = await request.text();
  if (raw.length > 2_000_000) return fail(413, "snapshot too large");
  if (!env.PUSH_SECRET || !sameText(await hmacHex(env.PUSH_SECRET, `${ts}.${raw}`), sig)) return fail(401, "bad signature");
  let doc: { generated?: unknown; agents?: unknown };
  try { doc = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  if (!doc || typeof doc.generated !== "number" || !Array.isArray(doc.agents)) return fail(400, "not a city snapshot");
  await saveSnapshot(env.DB, raw, now);
  purgeCity(c);
  return json({ ok: true, agents: doc.agents.length });
}
