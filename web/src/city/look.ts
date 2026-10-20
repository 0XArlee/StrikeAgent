// An agent's look (the character creator): body, hair, clothes and accessories. Shared by the page (sprites, editor)
// and the site API (web/server validates what owners save), so both accept exactly the same values.

export const HAIR_STYLES = ["short", "long", "spiky", "mohawk", "ponytail", "afro", "shaved"] as const;
export const TOP_STYLES = ["tee", "hoodie", "jacket", "suit"] as const;
export const BOTTOM_STYLES = ["pants", "shorts"] as const;
export const FACE_STYLES = ["none", "glasses", "shades", "visor"] as const;
export const HEAD_STYLES = ["none", "cap", "beanie", "headphones", "crown"] as const;
export const BACK_STYLES = ["none", "backpack", "cape"] as const;

export type HairStyle = (typeof HAIR_STYLES)[number];
export type TopStyle = (typeof TOP_STYLES)[number];
export type BottomStyle = (typeof BOTTOM_STYLES)[number];
export type FaceStyle = (typeof FACE_STYLES)[number];
export type HeadStyle = (typeof HEAD_STYLES)[number];
export type BackStyle = (typeof BACK_STYLES)[number];

export interface Look {
  skin: string; eyes: string;
  hair: HairStyle; hairColor: string;
  top: TopStyle; topColor: string; top2: string; accent: string;
  bottom: BottomStyle; pants: string; shoes: string;
  face: FaceStyle; faceColor: string;
  head: HeadStyle; headColor: string;
  back: BackStyle; backColor: string;
}

export interface Swatch { hex: string; en: string; es: string }

export const SKINS: Swatch[] = [
  { hex: "#f7dcc6", en: "Porcelain", es: "Porcelana" }, { hex: "#f0c9a6", en: "Light", es: "Clara" },
  { hex: "#e2ad85", en: "Warm", es: "Cálida" }, { hex: "#c68e6a", en: "Tan", es: "Bronceada" },
  { hex: "#a26b4a", en: "Brown", es: "Morena" }, { hex: "#7a4a33", en: "Deep", es: "Oscura" },
  { hex: "#5a3826", en: "Ebony", es: "Ébano" }, { hex: "#9be7c4", en: "Mint (android)", es: "Menta (androide)" },
];
export const EYES: Swatch[] = [
  { hex: "#0b0b0b", en: "Black", es: "Negro" }, { hex: "#3b2416", en: "Brown", es: "Marrón" },
  { hex: "#1d4ed8", en: "Blue", es: "Azul" }, { hex: "#15803d", en: "Green", es: "Verde" },
  { hex: "#4efab0", en: "Mint glow", es: "Menta brillante" }, { hex: "#f43f5e", en: "Red glow", es: "Rojo brillante" },
];
export const HAIRS: Swatch[] = [
  { hex: "#1c1917", en: "Black", es: "Negro" }, { hex: "#3b2416", en: "Dark brown", es: "Castaño oscuro" },
  { hex: "#6b3a1e", en: "Brown", es: "Castaño" }, { hex: "#a16207", en: "Honey", es: "Miel" },
  { hex: "#facc15", en: "Blond", es: "Rubio" }, { hex: "#c2410c", en: "Ginger", es: "Pelirrojo" },
  { hex: "#e5e7eb", en: "Silver", es: "Plateado" }, { hex: "#4efab0", en: "Mint", es: "Menta" },
  { hex: "#0ea5e9", en: "Blue", es: "Azul" }, { hex: "#7c3aed", en: "Violet", es: "Violeta" },
  { hex: "#ec4899", en: "Pink", es: "Rosa" }, { hex: "#be123c", en: "Crimson", es: "Carmesí" },
];
export const CLOTHES: Swatch[] = [
  { hex: "#4efab0", en: "Strike mint", es: "Menta Strike" }, { hex: "#0f766e", en: "Teal", es: "Verde azulado" },
  { hex: "#15803d", en: "Green", es: "Verde" }, { hex: "#1d4ed8", en: "Blue", es: "Azul" },
  { hex: "#1f6f8b", en: "Ocean", es: "Océano" }, { hex: "#172554", en: "Navy", es: "Marino" },
  { hex: "#7c3aed", en: "Violet", es: "Violeta" }, { hex: "#ec4899", en: "Pink", es: "Rosa" },
  { hex: "#9f1239", en: "Wine", es: "Granate" }, { hex: "#f43f5e", en: "Red", es: "Rojo" },
  { hex: "#f97316", en: "Orange", es: "Naranja" }, { hex: "#facc15", en: "Yellow", es: "Amarillo" },
  { hex: "#e5e7eb", en: "White", es: "Blanco" }, { hex: "#737373", en: "Grey", es: "Gris" },
  { hex: "#334155", en: "Slate", es: "Pizarra" }, { hex: "#171717", en: "Black", es: "Negro" },
];

const HEX = /^#[0-9a-f]{6}$/i;
const pick = <T extends string>(v: unknown, allowed: readonly T[], dflt: T): T => (allowed.includes(v as T) ? (v as T) : dflt);
const color = (v: unknown, dflt: string) => (typeof v === "string" && HEX.test(v) ? v.toLowerCase() : dflt);

export const DEFAULT_LOOK: Look = {
  skin: SKINS[2].hex, eyes: EYES[0].hex, hair: "short", hairColor: HAIRS[1].hex,
  top: "tee", topColor: CLOTHES[4].hex, top2: CLOTHES[12].hex, accent: CLOTHES[0].hex,
  bottom: "pants", pants: CLOTHES[5].hex, shoes: "#0b0b0b",
  face: "none", faceColor: CLOTHES[15].hex, head: "none", headColor: CLOTHES[0].hex, back: "none", backColor: CLOTHES[14].hex,
};

/** Any input -> a valid look (unknown values fall back to defaults), or null when it is not an object. */
export function normalizeLook(v: unknown): Look | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const o = v as Record<string, unknown>, d = DEFAULT_LOOK;
  return {
    skin: color(o.skin, d.skin), eyes: color(o.eyes, d.eyes),
    hair: pick(o.hair, HAIR_STYLES, d.hair), hairColor: color(o.hairColor, d.hairColor),
    top: pick(o.top, TOP_STYLES, d.top), topColor: color(o.topColor, d.topColor), top2: color(o.top2, d.top2),
    accent: color(o.accent, d.accent),
    bottom: pick(o.bottom, BOTTOM_STYLES, d.bottom), pants: color(o.pants, d.pants), shoes: color(o.shoes, d.shoes),
    face: pick(o.face, FACE_STYLES, d.face), faceColor: color(o.faceColor, d.faceColor),
    head: pick(o.head, HEAD_STYLES, d.head), headColor: color(o.headColor, d.headColor),
    back: pick(o.back, BACK_STYLES, d.back), backColor: color(o.backColor, d.backColor),
  };
}

/** Deterministic look for an agent without one (stable per id, varied across the city). */
export function randomLook(R: () => number): Look {
  const one = <T,>(xs: readonly T[]) => xs[Math.floor(R() * xs.length)];
  const rare = <T extends string>(xs: readonly T[], p: number) => (R() < p ? one(xs.slice(1)) : xs[0]);
  return {
    skin: one(SKINS.slice(0, 7)).hex, eyes: R() < 0.8 ? EYES[0].hex : one(EYES).hex,
    hair: one(HAIR_STYLES), hairColor: one(R() < 0.75 ? HAIRS.slice(0, 7) : HAIRS).hex,
    top: one(TOP_STYLES), topColor: one(CLOTHES).hex, top2: one(CLOTHES).hex, accent: one(CLOTHES).hex,
    bottom: R() < 0.8 ? "pants" : "shorts", pants: one(CLOTHES.slice(4)).hex, shoes: R() < 0.7 ? "#0b0b0b" : one(CLOTHES).hex,
    face: rare(FACE_STYLES, 0.3), faceColor: one(CLOTHES).hex,
    head: rare(HEAD_STYLES, 0.3), headColor: one(CLOTHES).hex,
    back: rare(BACK_STYLES, 0.2), backColor: one(CLOTHES).hex,
  };
}

/** Short stable fingerprint (shown in the signed message: what you sign is the look that gets saved). */
export function lookId(l: Look): string {
  let h = 2166136261;
  const s = JSON.stringify(l);
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(16).padStart(8, "0");
}
