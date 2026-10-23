// Strike Finance's alerts in the city (/api/alerts: what the alerts bot on the agents' host saw), and linking the
// owner's agent to the bot (/api/me/telegram, with the session token).
import { useEffect, useState } from "react";

export interface CityAlert {
  id: string; t: number; kind: string; level: "info" | "warn" | "alert"; market: string | null; place: string;
  title: { en: string; es: string }; body: { en: string; es: string };
}
export interface AlertsDoc { bot: string; alerts: CityAlert[]; stale?: boolean; none?: boolean }

export const BOT = "EdgeCraftStrikeCityBot";
export const botUrl = (start = "strike") => `https://t.me/${BOT}?start=${start}`;
export const FRESH_MS = 45 * 60_000;   // an alert stays over its building this long

/** The latest alerts, read every minute (null until the first answer). */
export function useAlerts(): AlertsDoc | null {
  const [doc, setDoc] = useState<AlertsDoc | null>(null);
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const r = await fetch("/api/alerts", { headers: { Accept: "application/json" } });
        if (r.ok && live) {
          const d = (await r.json()) as AlertsDoc;
          setDoc({ bot: d.bot || BOT, alerts: Array.isArray(d.alerts) ? d.alerts : [], stale: d.stale, none: d.none });
        }
      } catch { /* the next minute */ }
    };
    void load();
    const id = window.setInterval(load, 60_000);
    return () => { live = false; window.clearInterval(id); };
  }, []);
  return doc;
}

/** The freshest alert of each building, the most serious first. */
export function byPlace(alerts: CityAlert[], now: number): Record<string, CityAlert> {
  const rank = { alert: 3, warn: 2, info: 1 } as const;
  const out: Record<string, CityAlert> = {};
  for (const a of alerts) {
    if (now - a.t > FRESH_MS) continue;
    const cur = out[a.place];
    if (!cur || rank[a.level] > rank[cur.level] || (rank[a.level] === rank[cur.level] && a.t > cur.t)) out[a.place] = a;
  }
  return out;
}

async function call(method: string, token: string, body?: unknown) {
  const r = await fetch("/api/me/telegram", { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((d as { error?: string }).error || `HTTP ${r.status}`);
  return d;
}
export const tgStatus = (token: string) => call("GET", token) as Promise<{ bot: string; chats: { label: string; since: number }[] }>;
export const tgLink = (token: string, lang: string) => call("POST", token, { lang }) as Promise<{ url: string; expires: number }>;
export const tgUnlink = (token: string) => call("DELETE", token) as Promise<{ ok: boolean }>;
