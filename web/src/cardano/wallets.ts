// Cardano wallet discovery and use through CIP-30 (https://cips.cardano.org/cip/CIP-0030).
// Every CIP-30 wallet injects a provider under window.cardano[<key>] with { name, icon, apiVersion, enable }.
// Wallets inject asynchronously and some register aliases (e.g. Eternl as "eternl" and "ccvault"), so discovery
// polls for a few seconds and de-duplicates by name.
import { addressHexToBech32, walletKey } from "./bech32";

export interface Cip30Provider {
  name: string;
  icon: string;
  apiVersion?: string;
  enable: () => Promise<Cip30Api>;
  isEnabled?: () => Promise<boolean>;
}

export interface Cip30Api {
  getNetworkId: () => Promise<number>;
  getChangeAddress: () => Promise<string>;
  getUsedAddresses: (paginate?: unknown) => Promise<string[]>;
  getRewardAddresses?: () => Promise<string[]>;
  signData: (addr: string, payloadHex: string) => Promise<{ signature: string; key: string }>;
}

export interface DetectedWallet {
  key: string;
  name: string;
  icon: string;
  apiVersion: string;
  provider: Cip30Provider;
}

/** Well-known Cardano wallets, offered as install links when not detected. */
export const KNOWN_WALLETS: { id: string; name: string; url: string }[] = [
  { id: "lace", name: "Lace", url: "https://www.lace.io" },
  { id: "eternl", name: "Eternl", url: "https://eternl.io" },
  { id: "yoroi", name: "Yoroi", url: "https://yoroi-wallet.com" },
  { id: "typhoncip30", name: "Typhon", url: "https://typhonwallet.io" },
  { id: "vespr", name: "VESPR", url: "https://vespr.xyz" },
  { id: "nufi", name: "NuFi", url: "https://nu.fi" },
  { id: "begin", name: "Begin", url: "https://begin.is" },
  { id: "gerowallet", name: "GeroWallet", url: "https://gerowallet.io" },
];

const NON_WALLET_KEYS = new Set(["_events", "_eventsCount", "_maxListeners", "isEnabled", "enable"]);

type CardanoWindow = Window & { cardano?: Record<string, unknown> };

/** Reads a provider property without letting the wallet break the page. Lace exposes its provider through a Proxy
 *  whose `get` violates the invariant of its frozen `enable` (any `p.enable` throws a TypeError); the property
 *  descriptor still holds the real function. */
function prop(o: object, k: string): unknown {
  try { return (o as Record<string, unknown>)[k]; } catch { /* fall back to the descriptor */ }
  try { return Object.getOwnPropertyDescriptor(o, k)?.value; } catch { return undefined; }
}

export function scanWallets(): DetectedWallet[] {
  let root: Record<string, unknown> | undefined;
  try { root = (window as CardanoWindow).cardano; } catch { return []; }
  if (!root || typeof root !== "object") return [];
  const seen = new Map<string, DetectedWallet>();
  let keys: string[] = [];
  try { keys = Object.keys(root); } catch { return []; }
  for (const key of keys) {
    if (NON_WALLET_KEYS.has(key)) continue;
    const p = prop(root, key);
    if (!p || typeof p !== "object") continue;
    const enable = prop(p, "enable"), isEnabled = prop(p, "isEnabled");
    if (typeof enable !== "function") continue;
    const nm = prop(p, "name"), icon = prop(p, "icon"), apiVersion = prop(p, "apiVersion");
    const raw = (typeof nm === "string" && nm.trim()) || key;
    const name = raw === raw.toLowerCase() ? raw.charAt(0).toUpperCase() + raw.slice(1) : raw;  // e.g. Lace reports "lace"
    const id = name.toLowerCase();
    if (seen.has(id)) continue;
    // our own provider object: later calls never touch the wallet's getters again (`this` stays the wallet's object)
    const provider: Cip30Provider = {
      name, icon: typeof icon === "string" ? icon : "", apiVersion: typeof apiVersion === "string" ? apiVersion : "",
      enable: () => (enable as Cip30Provider["enable"]).call(p),
      isEnabled: typeof isEnabled === "function" ? () => (isEnabled as () => Promise<boolean>).call(p) : undefined,
    };
    seen.set(id, { key, name, icon: provider.icon, apiVersion: provider.apiVersion ?? "", provider });
  }
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
}

/** Calls ``onChange`` with the detected wallets now and whenever late-injecting wallets appear (for ~4 s). */
export function watchWallets(onChange: (w: DetectedWallet[]) => void): () => void {
  let last = "";
  const tick = () => {
    const w = scanWallets();
    const sig = w.map((x) => x.name).join("|");
    if (sig !== last) { last = sig; onChange(w); }
  };
  tick();
  const timers = [150, 500, 1000, 2000, 4000].map((ms) => window.setTimeout(tick, ms));
  window.addEventListener("load", tick);
  window.addEventListener("focus", tick);
  return () => { timers.forEach(clearTimeout); window.removeEventListener("load", tick); window.removeEventListener("focus", tick); };
}

export class WalletError extends Error {
  constructor(public kind: "refused" | "declined" | "network" | "no_address" | "unknown", message: string) {
    super(message);
  }
}

/** Normalises CIP-30 APIError / DataSignError codes. */
export function asWalletError(e: unknown): WalletError {
  if (e instanceof WalletError) return e;
  const err = e as { code?: number; info?: string; message?: string };
  const msg = err?.info || err?.message || String(e);
  if (err?.code === -3 || /refus|reject|denied|cancel/i.test(msg)) return new WalletError("refused", msg);
  if (err?.code === 3 || /declin/i.test(msg)) return new WalletError("declined", msg);
  return new WalletError("unknown", msg);
}

export interface Connected {
  wallet: DetectedWallet;
  api: Cip30Api;
  networkId: number;
  addressHex: string;
  address: string;
}

/** The wallet API through `prop`: same protection as discovery for wallets whose objects are Proxies. */
function safeApi(raw: object): Cip30Api {
  const m = <T extends unknown[], R>(k: string) => (...args: T): Promise<R> => {
    const f = prop(raw, k);
    if (typeof f !== "function") return Promise.reject(new WalletError("unknown", `The wallet does not implement ${k}`));
    return (f as (...a: T) => Promise<R>).apply(raw, args);
  };
  return { getNetworkId: m("getNetworkId"), getChangeAddress: m("getChangeAddress"), getUsedAddresses: m("getUsedAddresses"),
    getRewardAddresses: m("getRewardAddresses"), signData: m("signData") };
}

export async function connect(wallet: DetectedWallet): Promise<Connected> {
  let api: Cip30Api;
  try {
    api = safeApi(await wallet.provider.enable());
  } catch (e) {
    throw asWalletError(e);
  }
  const networkId = await api.getNetworkId();
  let addressHex = "";
  try { addressHex = await api.getChangeAddress(); } catch { /* some wallets only expose used addresses */ }
  if (!addressHex) {
    const used = await api.getUsedAddresses();
    addressHex = used?.[0] ?? "";
  }
  if (!addressHex) throw new WalletError("no_address", "The wallet did not return an address");
  const address = /^addr/.test(addressHex) ? addressHex : addressHexToBech32(addressHex);
  return { wallet, api, networkId, addressHex, address };
}

/** Is the wallet the session was opened with still the one selected in the extension? Asked without bothering the
 *  user: only a wallet that already allows this site is read (its enable() does not prompt then).
 *  "same" / "other" (another account selected) / "off" (the wallet no longer allows the site) / "unknown". */
export async function sessionWallet(walletName: string, address: string): Promise<"same" | "other" | "off" | "unknown"> {
  const w = scanWallets().find((x) => x.name.toLowerCase() === walletName.toLowerCase());
  if (!w || !w.provider.isEnabled) return "unknown";
  try {
    if (!(await w.provider.isEnabled())) return "off";
    const c = await connect(w);
    return walletKey(c.address) === walletKey(address) ? "same" : "other";
  } catch { return "unknown"; }
}

/** CIP-30 data signature over the exact message, in Strike's builder-connect format "{coseSign1Hex}:{coseKeyHex}". */
export async function signMessage(c: Connected, messageHex: string): Promise<string> {
  try {
    const { signature, key } = await c.api.signData(c.addressHex, messageHex);
    return `${signature}:${key}`;
  } catch (e) {
    throw asWalletError(e);
  }
}
