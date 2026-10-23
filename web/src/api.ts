// Client of the Smart Flow site API (Cloudflare Pages Functions, web/server). Wallet owners prove ownership with a
// CIP-30 signature over a one-time message; until the Smart Flow builder code is registered on Strike, agents start on
// paper (`info.paper`). VITE_API_BASE="mock" runs an in-browser simulation (demos, screenshots, tests).
import { utf8ToHex } from "./cardano/bech32";
import type { Look } from "./city/look";
import type { Persona } from "./city/persona";
import type { Portfolio } from "./city/portfolio-types";

export type RiskPreset = "conservative" | "standard" | "assertive";
export type AgentAction = "pause" | "resume" | "revoke" | "show" | "hide" | "look" | "settings" | "test" | "copy";

/** Copy with your agent (web/server/copyplan.ts): the plan its owner signs. */
export interface CopyPlan {
  mode: "off" | "manual" | "pilot";
  lead: string | null; platform: "strike" | "hyperliquid" | null;
  sizing: { kind: "ratio"; amount: number } | { kind: "fixed"; margin: number; funding: number };
  stopLoss: number; leverage: number; excluded: string[]; until: number | null; alarmPause: boolean;
  macroPause?: boolean;   // also waits out the big scheduled US releases (Fed, CPI, jobs, PCE, GDP)
  account?: string;       // where it runs: "auto" (a free sub-account of yours, else a new one), "new", or a sub-account's id
  pilot: { minScore: number; platforms: ("strike" | "hyperliquid")[]; review: number; maxSwitches: number } | null;
}
/** One of the owner's sub-accounts as the host read it: whom it copies now, and its equity over time. */
export interface SubAccount { id: string; name: string; equity: number | null; available: number; busy: string | null; history?: [number, number][] }
/** How it goes, as the agents' host reported it (smartflow/copytrade/pilot.py). */
export interface CopyStatus {
  state: "copying" | "starting" | "halted" | "off" | "waiting"; why?: string | null; version?: number | null;
  lead?: string | null; platform?: "strike" | "hyperliquid" | null; since?: number | null; subAccount?: string | null;
  reviewAt?: number | null; error?: string | null; at?: number;
  copy?: { copy_amount: number | null; margin_per_entry_order: number | null; total_margin: number | null; total_worth: number | null;
    realized_pnl: number | null; pnl: number | null; total_volume: number | null; stop_loss_amount: number | null; orders: number | null } | null;
  log?: { t: number; kind: string; lead?: string; reason?: string; text?: string; step?: string; status?: number; available?: number; left?: number; mode?: string; account?: string }[];
  accounts?: SubAccount[];
}
export interface CopyView { plan: CopyPlan | null; version: number | null; status: CopyStatus | null }

export interface AppInfo {
  env: "mainnet" | "testnet";
  builderCode: string;
  feeBps: number;           // fee per execution, basis points (20 = 0.20 %)
  takerFeeBps: number;      // Strike's own taker fee
  markets: string[];
  riskPresets: Record<RiskPreset, number>;  // % of equity at risk per trade
  agentHealthy: boolean;
  engine: string;
  connect?: boolean;        // real trading through the builder code is enabled
  paper?: boolean;          // agents start on paper (no real money)
  live?: { env: "mainnet" | "testnet"; enabled: boolean; invite?: boolean; feeBps: number; code?: string };   // builder connect offered (invite: only some wallets)
  pushedAt?: number | null; // when the agents' host last sent the agents
  holds?: Record<string, { since: number; why: string[] }>;   // strategies on a safety hold
  copyPilot?: boolean;      // copy with your agent is open on this site
}

/** The agent trading the owner's own Strike account (builder connect). */
export interface LiveView {
  env: "mainnet" | "testnet";
  enabled: boolean;
  feeBps: number;
  status: "none" | "active" | "off";
  accountId: string | null; // shortened
  since: number | null;
}

export interface LiveChallenge { sessionId: string; messageToSign: string; expiresAt: number; feeBps: number; env: "mainnet" | "testnet" }

export interface Challenge {
  sessionId: string;
  messageToSign: string;
  feeBps: number;
  expiresAt: number;
  live?: boolean;           // Strike's builder-connect message: signing it creates the agent already trading
  signin?: boolean;         // the wallet already has an agent: signing only opens it, nothing changes
}

export interface Linked {
  accountId: string;
  apiWalletPublicKey: string;
  expiresAt?: string;
  token?: string;           // dashboard session (paper mode)
  cityId?: string;
  citizen?: number | null;  // created: its citizen number in the city (the end card)
  mode?: "paper" | "live";
  live?: LiveView;
  signin?: boolean;         // signed in to an agent that already existed: its settings as they are
  agent?: { name: string; markets: string[]; risk: RiskPreset; public: boolean; look: Look | null; persona?: Persona | null; strategy: string };
}

export interface StartOptions { risk: RiskPreset; markets: string[]; name: string; public: boolean; look?: Look; persona?: Persona; strategy?: string }

/** A journal entry as the city renders it (code + args, see city/text.ts). */
export interface JournalEntry { time: number; market: string; kind: string; code: string; args?: Record<string, string | number | null>; text?: string }

export interface Me {
  accountId: string;
  address: string;
  status: "active" | "paused";
  risk: RiskPreset;
  markets: string[];
  equity: number | null;
  openPositions: { market: string; side: "long" | "short"; size: number; entry: number; stop: number | null; upnl: number | null }[];
  decisions: JournalEntry[];
  feesPaid: number | null;
  name?: string;
  public?: boolean;
  mode?: "paper" | "live";
  agentStatus?: string;
  equity0?: number;
  trades?: number;
  createdAt?: number;
  look?: Look | null;
  persona?: Persona | null;      // personality and trade in the city (never how it trades)
  live?: LiveView;
  portfolio?: Portfolio | null;   // connected to Strike: the real account (amounts: only the owner gets them)
  strategy?: string;
  hold?: { since: number; why: string[] } | null;   // its strategy's safety hold: new trades wait
  admin?: boolean;                                   // reads the site's suggestions (My agent's inbox)
  copy?: CopyView;                                   // copy with your agent: the signed plan and how it goes
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "mock";

async function call<T>(path: string, init?: RequestInit & { token?: string }): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init?.token) headers.Authorization = `Bearer ${init.token}`;
  const r = await fetch(`${BASE}${path}`, { ...init, headers });
  const text = await r.text();
  let body: { error?: string } = {};
  try { body = text ? JSON.parse(text) : {}; } catch { throw new ApiError(r.status, r.statusText || "unexpected response"); }
  if (!r.ok) throw new ApiError(r.status, body?.error ?? r.statusText);
  return body as T;
}

/** Payload for CIP-30 signData: the message as hex (a message that already is hex is passed through). */
export function messageHex(m: string): string {
  return /^[0-9a-f]+$/i.test(m) && m.length % 2 === 0 ? m : utf8ToHex(m);
}

export interface Api {
  info(): Promise<AppInfo>;
  challenge(address: string, opts: StartOptions): Promise<Challenge>;
  verify(sessionId: string, walletSignature: string): Promise<Linked>;
  me(link: { accountId: string; token?: string }): Promise<Me>;
  /** Every change needs a fresh wallet signature over an action challenge. */
  actionChallenge(accountId: string, action: AgentAction, look?: Look, settings?: { strategy: string; markets: string[]; risk: string }, persona?: Persona,
    copy?: CopyPlan): Promise<Challenge>;
  action(sessionId: string, walletSignature: string): Promise<Me | { deleted: true }>;
  /** Builder connect: Strike's message for the owner's wallet, then the signature; off needs only the session. */
  liveChallenge(token: string): Promise<LiveChallenge>;
  liveVerify(token: string, sessionId: string, walletSignature: string): Promise<LiveView>;
  liveOff(token: string): Promise<LiveView>;
  /** Invite-only phase: may this wallet trade on its Strike account. */
  /** Right after the wallet connects: whether it already has an agent and may trade for real now. */
  walletStatus(address: string): Promise<{ live: boolean; agent: boolean }>;
  signIn(address: string): Promise<Challenge>;
  /** The Feedback button: private suggestions (with the session, it says which agent wrote it). */
  feedback(f: FeedbackInput, token?: string): Promise<{ ok: true; id: string }>;
  feedbackInbox(token: string): Promise<FeedbackInbox>;
  feedbackRead(token: string, ids: string[]): Promise<{ ok: true }>;
}

export interface FeedbackInput { subject: string; message: string; image?: string | null; page?: string; lang?: string }
export interface FeedbackItem { id: string; t: number; subject: string; message: string; image: string | null; page: string | null; lang: string | null;
  user: { id: string; name: string | null } | null; read: boolean }
export interface FeedbackInbox { unread: number; items: FeedbackItem[] }

const real: Api = {
  info: () => call<AppInfo>("/api/info"),
  challenge: (address, o) =>
    call<Challenge>("/api/connect/challenge", { method: "POST", body: JSON.stringify({ address, chain: "cardano", ...o }) }),
  verify: (sessionId, walletSignature) =>
    call<Linked>("/api/connect/verify", { method: "POST", body: JSON.stringify({ sessionId, walletSignature }) }),
  me: (link) => call<Me>("/api/me", { token: link.token }),
  actionChallenge: (accountId, action, look, settings, persona, copy) =>
    call<Challenge>("/api/action/challenge", { method: "POST", body: JSON.stringify({ accountId, action, look, persona, copy, ...settings }) }),
  action: (sessionId, walletSignature) =>
    call<Me | { deleted: true }>("/api/action", { method: "POST", body: JSON.stringify({ sessionId, walletSignature }) }),
  liveChallenge: (token) => call<LiveChallenge>("/api/live/challenge", { method: "POST", body: "{}", token }),
  liveVerify: (token, sessionId, walletSignature) =>
    call<LiveView>("/api/live/verify", { method: "POST", body: JSON.stringify({ sessionId, walletSignature }), token }),
  liveOff: (token) => call<LiveView>("/api/live/off", { method: "POST", body: "{}", token }),
  walletStatus: (address) => call<{ live: boolean; agent: boolean }>(`/api/live/eligible?address=${encodeURIComponent(address)}`),
  signIn: (address) => call<Challenge>("/api/connect/challenge", { method: "POST", body: JSON.stringify({ address, chain: "cardano", signin: true }) }),
  feedback: (f, token) => call<{ ok: true; id: string }>("/api/feedback", { method: "POST", body: JSON.stringify(f), token }),
  feedbackInbox: (token) => call<FeedbackInbox>("/api/feedback/inbox", { token }),
  feedbackRead: (token, ids) => call<{ ok: true }>("/api/feedback/read", { method: "POST", body: JSON.stringify({ ids }), token }),
};

// ---------------------------------------------------------------- mock (same contract as web/server)
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
let mockMe: Me | null = null;
let pendingAction: AgentAction | null = null;
let pendingLook: Look | undefined;
let pendingPersona: Persona | undefined;
let mockLive: LiveView = { env: "testnet", enabled: false, feeBps: 20, status: "none", accountId: null, since: null };

const mock: Api = {
  async info() {
    await wait(150);
    return {
      env: "mainnet", builderCode: "", feeBps: 20, takerFeeBps: 5,
      markets: ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD", "NEAR-USD", "ZEC-USD"],
      riskPresets: { conservative: 0.5, standard: 1.0, assertive: 2.0 }, agentHealthy: true, engine: "1.0.0", connect: false, paper: true,
    };
  },
  async challenge(address, o) {
    await wait(500);
    const now = Date.now();
    mockMe = { accountId: "u-1f2e3d4c5b6a", address, status: "active", risk: o.risk, markets: o.markets, equity: 10000,
      openPositions: [], decisions: [], feesPaid: null, name: o.name, public: o.public, mode: "paper", agentStatus: "waiting",
      equity0: 10000, trades: 0, createdAt: now, look: o.look ?? null, persona: o.persona ?? null, admin: true };
    const persona = o.persona ? `Personality in the city: ${o.persona.temper}/${o.persona.job} (never changes how it trades)\n` : "";
    return {
      sessionId: "mock-session", feeBps: 0, expiresAt: now + 5 * 60_000,
      messageToSign: `Smart Flow · start my paper agent\n\nThis signature only proves that you own this wallet.\nIt cannot move funds, place orders or approve any fee.\n\nWallet: ${address}\nAgent name: ${o.name}\nMarkets: ${o.markets.join(", ")}\n${persona}Mode: paper (no real money)\nNonce: 019d4a2b-1234-7890-abcd-ef1234567890`,
    };
  },
  async verify() {
    await wait(700);
    return { accountId: mockMe!.accountId, apiWalletPublicKey: "", token: "mock-token", cityId: mockMe!.accountId, mode: "paper", citizen: 42 };
  },
  async me() {
    await wait(300);
    const t = Date.now();
    return {
      ...mockMe!, equity: 10047.5, live: mockLive,
      openPositions: [{ market: "BTC-USD", side: "long", size: 0.0421, entry: 82116, stop: 80936, upnl: 12.4 }],
      decisions: ([
        { time: t - 2 * 3600_000, market: "BTC-USD", kind: "order", code: "open", args: { side: "long", price: 82116, stop: 80936 } },
        { time: t - 2 * 3600_000, market: "ETH-USD", kind: "analysis", code: "check", args: { r: "inside,volume", n: 20, vol: 1.31, vmin: 1.5 } },
        { time: t - 6 * 3600_000, market: "BTC-USD", kind: "pause", code: "start" },
      ] as JournalEntry[]),
    };
  },
  async actionChallenge(_accountId, action, look, _settings, persona) {
    await wait(300);
    pendingAction = action;
    pendingLook = look;
    pendingPersona = persona;
    return { sessionId: "mock-action", feeBps: 0, expiresAt: Date.now() + 5 * 60_000,
      messageToSign: `Smart Flow · ${action} my paper agent\n\nWallet: ${mockMe?.address}\nAction: ${action}\nNonce: 7c1e…` };
  },
  async action() {
    await wait(400);
    if (pendingAction === "revoke") { mockMe = null; return { deleted: true }; }
    if (mockMe && pendingAction === "pause") mockMe.status = "paused";
    if (mockMe && pendingAction === "resume") mockMe.status = "active";
    if (mockMe && pendingAction === "show") mockMe.public = true;
    if (mockMe && pendingAction === "hide") mockMe.public = false;
    if (mockMe && pendingAction === "look" && pendingLook) mockMe.look = pendingLook;
    if (mockMe && pendingAction === "look" && pendingPersona) mockMe.persona = pendingPersona;
    return mock.me({ accountId: mockMe?.accountId ?? "" });
  },
  async liveChallenge() {
    await wait(400);
    return { sessionId: "mock-live", feeBps: 20, env: "testnet", expiresAt: Date.now() + 5 * 60_000,
      messageToSign: `Connect to Strike via builder "SmartFlowAgent-EdgeCraft".
This authorizes the builder to collect up to 0.2% fee on your trades.
Wallet: ${mockMe?.address}
Nonce: 01a1…` };
  },
  async liveVerify() {
    await wait(600);
    mockLive = { ...mockLive, status: "active", accountId: "0b7c41d2…", since: Date.now() };
    return mockLive;
  },
  async liveOff() {
    await wait(300);
    mockLive = { ...mockLive, status: "off" };
    return mockLive;
  },
  async walletStatus() { return { live: false, agent: !!mockMe }; },
  async signIn(address) {
    await wait(300);
    return { sessionId: "mock-signin", feeBps: 0, expiresAt: Date.now() + 5 * 60_000, signin: true,
      messageToSign: `Smart Flow · sign in to my agent

Wallet: ${address}
Agent name: ${mockMe?.name ?? ""}
Nonce: 5d2a…` };
  },
  async feedback(f) {
    await wait(500);
    if (f.subject.trim().length < 2 || f.message.trim().length < 2) throw new ApiError(400, "write a subject and a message");
    mockFeedback.unshift({ id: `fb-${mockFeedback.length + 1}`, t: Date.now(), subject: f.subject, message: f.message, image: f.image ?? null,
      page: f.page ?? null, lang: f.lang ?? null, user: mockMe ? { id: mockMe.accountId, name: mockMe.name ?? null } : null, read: false });
    return { ok: true, id: mockFeedback[0].id };
  },
  async feedbackInbox() { await wait(200); return { unread: mockFeedback.filter((x) => !x.read).length, items: mockFeedback }; },
  async feedbackRead(_token, ids) { mockFeedback.forEach((x) => { if (ids.includes(x.id)) x.read = true; }); return { ok: true }; },
};
const mockFeedback: FeedbackItem[] = [];

export const api: Api = BASE === "mock" ? mock : real;
export const isMock = BASE === "mock";
