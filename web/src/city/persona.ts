// An agent's personality (temper) and trade in the city (job): chosen by its owner when creating it (or later from My
// agent), never part of how it trades. The strategy, its markets and the risk decide every order; the persona only
// decides what the agent does in EdgeCraft-StrikeCity while it waits for a setup (its job: which building it works in
// and what real data it reads there) and how it talks (its temper: the voice of its lines). Shared by the page and the
// site API (web/server validates what owners save), like look.ts.

export type Temper = "stoic" | "analyst" | "optimist" | "joker" | "cautious";
export type Job = "chartist" | "reporter" | "tape" | "guardian";
export interface Persona { v: 1; temper: Temper; job: Job }

export const TEMPERS: Temper[] = ["stoic", "analyst", "optimist", "joker", "cautious"];
export const JOBS: Job[] = ["chartist", "reporter", "tape", "guardian"];
/** Where each job works (a building of the city) while the agent waits for its next candle. */
export const JOB_PLACE: Record<Job, string> = { chartist: "lab", reporter: "news", tape: "exchange", guardian: "risk" };
export const TEMPER_COLOR: Record<Temper, string> = { stoic: "#94a3b8", analyst: "#60a5fa", optimist: "#fbbf24", joker: "#f472b6", cautious: "#4ade80" };

/** Any input -> a valid persona, or null (absent or not an object). Unknown values fall back to the defaults. */
export function normalizePersona(v: unknown): Persona | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const o = v as Record<string, unknown>;
  return { v: 1, temper: TEMPERS.includes(o.temper as Temper) ? (o.temper as Temper) : "stoic",
    job: JOBS.includes(o.job as Job) ? (o.job as Job) : "chartist" };
}

export const personaId = (p: Persona) => `${p.temper}/${p.job}`;

/** The persona of an agent without a saved one: stable per id (the official agents get theirs here too). */
export function personaFor(id: string): Persona {
  const fixed: Record<string, Persona> = {
    "sf-reference": { v: 1, temper: "stoic", job: "chartist" }, "sf-pyramid": { v: 1, temper: "optimist", job: "tape" },
    "sf-range": { v: 1, temper: "cautious", job: "guardian" }, "sf-2h": { v: 1, temper: "analyst", job: "chartist" },
    "sf-flowexit": { v: 1, temper: "joker", job: "reporter" },
  };
  if (fixed[id]) return fixed[id];
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  h >>>= 0;
  return { v: 1, temper: TEMPERS[h % TEMPERS.length], job: JOBS[(h >>> 8) % JOBS.length] };
}

/** The five questions of the personality quiz: each answer leans to one temper (the most chosen wins; a tie goes to
 *  the answer given last). */
export const QUIZ: Temper[][] = [
  ["stoic", "analyst", "optimist", "joker", "cautious"],
  ["analyst", "cautious", "stoic", "optimist", "joker"],
  ["joker", "stoic", "cautious", "analyst", "optimist"],
  ["optimist", "joker", "analyst", "cautious", "stoic"],
  ["cautious", "optimist", "joker", "stoic", "analyst"],
];
export function quizResult(answers: (number | null)[]): Temper | null {
  const count = new Map<Temper, number>();
  let last: Temper | null = null;
  answers.forEach((a, q) => {
    if (a == null) return;
    const t = QUIZ[q][a];
    count.set(t, (count.get(t) ?? 0) + 1);
    last = t;
  });
  if (!last) return null;
  const best = Math.max(...count.values());
  const tied = [...count.entries()].filter(([, n]) => n === best).map(([t]) => t);
  return tied.includes(last) ? last : tied[0];
}

/** What happened, for the agent's line (its voice depends on its temper). */
export type Moment = "win" | "loss" | "enter" | "wait" | "signal" | "risk" | "analyze";
