// Client of the Smart Flow site API (Cloudflare Pages Functions, web/server). Wallet owners prove ownership with a
// CIP-30 signature over a one-time message; until the Smart Flow builder code is registered on Strike, agents start on
// paper (`info.paper`). VITE_API_BASE="mock" runs an in-browser simulation (demos, screenshots, tests).
import { utf8ToHex } from "./cardano/bech32";
import type { Look } from "./city/look";
import type { Portfolio } from "./city/portfolio-types";

export type RiskPreset = "conservative" | "standard" | "assertive";
export type AgentAction = "pause" | "resume" | "revoke" | "show" | "hide" | "look" | "settings" | "test";

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
  mode?: "paper" | "live";
  live?: LiveView;
  signin?: boolean;         // signed in to an agent that already existed: its settings as they are
  agent?: { name: string; markets: string[]; risk: RiskPreset; public: boolean; look: Look | null; strategy: string };
}

export interface StartOptions { risk: RiskPreset; markets: string[]; name: string; public: boolean; look?: Look; strategy?: string }

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
  live?: LiveView;
  portfolio?: Portfolio | null;   // connected to Strike: the real account (amounts: only the owner gets them)
  strategy?: string;
  hold?: { since: number; why: string[] } | null;   // its strategy's safety hold: new trades wait
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
  actionChallenge(accountId: string, action: AgentAction, look?: Look, settings?: { strategy: string; markets: string[]; risk: string }): Promise<Challenge>;
  action(sessionId: string, walletSignature: string): Promise<Me | { deleted: true }>;
  /** Builder connect: Strike's message for the owner's wallet, then the signature; off needs only the session. */
  liveChallenge(token: string): Promise<LiveChallenge>;
  liveVerify(token: string, sessionId: string, walletSignature: string): Promise<LiveView>;
  liveOff(token: string): Promise<LiveView>;
  /** Invite-only phase: may this wallet trade on its Strike account. */
  /** Right after the wallet connects: whether it already has an agent and may trade for real now. */
  walletStatus(address: string): Promise<{ live: boolean; agent: boolean }>;
  signIn(address: string): Promise<Challenge>;
}

const real: Api = {
  info: () => call<AppInfo>("/api/info"),
  challenge: (address, o) =>
    call<Challenge>("/api/connect/challenge", { method: "POST", body: JSON.stringify({ address, chain: "cardano", ...o }) }),
  verify: (sessionId, walletSignature) =>
    call<Linked>("/api/connect/verify", { method: "POST", body: JSON.stringify({ sessionId, walletSignature }) }),
  me: (link) => call<Me>("/api/me", { token: link.token }),
  actionChallenge: (accountId, action, look, settings) =>
    call<Challenge>("/api/action/challenge", { method: "POST", body: JSON.stringify({ accountId, action, look, ...settings }) }),
  action: (sessionId, walletSignature) =>
    call<Me | { deleted: true }>("/api/action", { method: "POST", body: JSON.stringify({ sessionId, walletSignature }) }),
  liveChallenge: (token) => call<LiveChallenge>("/api/live/challenge", { method: "POST", body: "{}", token }),
  liveVerify: (token, sessionId, walletSignature) =>
    call<LiveView>("/api/live/verify", { method: "POST", body: JSON.stringify({ sessionId, walletSignature }), token }),
  liveOff: (token) => call<LiveView>("/api/live/off", { method: "POST", body: "{}", token }),
  walletStatus: (address) => call<{ live: boolean; agent: boolean }>(`/api/live/eligible?address=${encodeURIComponent(address)}`),
  signIn: (address) => call<Challenge>("/api/connect/challenge", { method: "POST", body: JSON.stringify({ address, chain: "cardano", signin: true }) }),
};

// ---------------------------------------------------------------- mock (same contract as web/server)
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
let mockMe: Me | null = null;
let pendingAction: AgentAction | null = null;
let pendingLook: Look | undefined;
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
      equity0: 10000, trades: 0, createdAt: now, look: o.look ?? null };
    return {
      sessionId: "mock-session", feeBps: 0, expiresAt: now + 5 * 60_000,
      messageToSign: `Smart Flow · start my paper agent\n\nThis signature only proves that you own this wallet.\nIt cannot move funds, place orders or approve any fee.\n\nWallet: ${address}\nAgent name: ${o.name}\nMarkets: ${o.markets.join(", ")}\nMode: paper (no real money)\nNonce: 019d4a2b-1234-7890-abcd-ef1234567890`,
    };
  },
  async verify() {
    await wait(700);
    return { accountId: mockMe!.accountId, apiWalletPublicKey: "", token: "mock-token", cityId: mockMe!.accountId, mode: "paper" };
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
  async actionChallenge(_accountId, action, look) {
    await wait(300);
    pendingAction = action;
    pendingLook = look;
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
};

export const api: Api = BASE === "mock" ? mock : real;
export const isMock = BASE === "mock";
