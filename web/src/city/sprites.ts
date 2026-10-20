// Pixel characters (12×16 art px), 4 directions × 2 walk frames, built from layers: head (hair style), body (top
// style), legs (bottom style), then face, head and back accessories. Cached per agent and look.
// Keys: . keep/transparent · o outline · h hair · s skin · e eyes · c top · d top shade · w top second colour ·
//       a accent (emblem, tie) · p pants · b shoes · g face accessory · x dark lens · k head accessory ·
//       K its shade · n back accessory
import { hash, mulberry } from "./rand";
import { randomLook, type Look } from "./look";

export type Dir = "down" | "up" | "left" | "right";
type View = "front" | "back" | "side";
type Rows = string[];
export { hash };

const W = 12, H = 16;

// ---------------------------------------------------------------- heads (rows 0-6) per hair style
const SHORT = {
  front: ["....oooo....", "...ohhhho...", "..ohhhhhho..", "..ohssssho..", "..osesseso..", "..osssssso..", "...osssso..."],
  back: ["....oooo....", "...ohhhho...", "..ohhhhhho..", "..ohhhhhho..", "..ohhhhhho..", "..ohhhhhho..", "...osssso..."],
  side: ["....oooo....", "...ohhhho...", "..ohhhhhho..", "..ohhhssso..", "..ohhssseo..", "..ohhsssso..", "...osssso..."],
};
const shave = (r: Rows) => r.map((x) => x.replace(/h/g, "s"));
const HEADS: Record<string, Record<View, Rows>> = {
  short: SHORT,
  long: {
    front: ["....oooo....", "...ohhhho...", "..ohhhhhho..", ".ohhsssshho.", ".ohsessesho.", ".ohssssssho.", ".ohossssoho."],
    back: ["....oooo....", "...ohhhho...", "..ohhhhhho..", ".ohhhhhhhho.", ".ohhhhhhhho.", ".ohhhhhhhho.", ".ohhhhhhhho."],
    side: ["....oooo....", "...ohhhho...", "..ohhhhhho..", ".ohhhhssso..", ".ohhhssseo..", ".ohhhsssso..", ".ohhosssso.."],
  },
  spiky: {
    front: ["...o.oo.o...", "..ohohhoho..", ...SHORT.front.slice(2)],
    back: ["...o.oo.o...", "..ohohhoho..", ...SHORT.back.slice(2)],
    side: ["...o.oo.o...", "..ohohhoho..", ...SHORT.side.slice(2)],
  },
  mohawk: {
    front: [".....oo.....", "....ohho....", "..osshhsso..", "..osssssso..", "..osesseso..", "..osssssso..", "...osssso..."],
    back: [".....oo.....", "....ohho....", "..osshhsso..", "..osshhsso..", "..osshhsso..", "..osssssso..", "...osssso..."],
    side: ["...oooooo...", "...ohhhho...", "..osssssso..", "..osssssso..", "..ossssseo..", "..osssssso..", "...osssso..."],
  },
  ponytail: SHORT,
  afro: {
    front: ["...oooooo...", "..ohhhhhho..", ".ohhhhhhhho.", ".ohhsssshho.", ".ohsessesho.", "..osssssso..", "...osssso..."],
    back: ["...oooooo...", "..ohhhhhho..", ".ohhhhhhhho.", ".ohhhhhhhho.", ".ohhhhhhhho.", "..ohhhhhho..", "...osssso..."],
    side: ["...oooooo...", "..ohhhhhho..", ".ohhhhhhhho.", ".ohhhhssso..", ".ohhhssseo..", "..ohhsssso..", "...osssso..."],
  },
  shaved: { front: shave(SHORT.front), back: shave(SHORT.back), side: shave(SHORT.side) },
};
// hair that falls below the head, drawn over the body (full 16-row overlays)
const pad = (top: number, rows: Rows): Rows => [...Array(top).fill("............"), ...rows, ...Array(H - top - rows.length).fill("............")];
const HAIR_EXTRA: Record<string, Partial<Record<View, Rows>>> = {
  long: { front: pad(7, [".oh......ho.", ".oh......ho."]), back: pad(7, [".ohhhhhhhho.", "..ohhhhhho..", "...ohhhho..."]), side: pad(7, [".ohh........", ".ohh........", "..oo........"]) },
  ponytail: { back: pad(7, [".....hh.....", ".....hh.....", "......h....."]), side: pad(3, [".oh.........", "ohh.........", ".oh........."]) },
};

// ---------------------------------------------------------------- bodies (rows 7-10) per top style
const BACK_TEE = ["..occcccco..", ".occcccccco.", ".osccccccso.", ".osccccccso."];
const TOPS: Record<string, Record<View, Rows>> = {
  tee: { front: ["..occaacco..", ".occcccccco.", ".osccccccso.", ".osccccccso."], back: BACK_TEE,
    side: ["...occaco...", "..occccco...", "..occcsco...", "..occcsco..."] },
  hoodie: { front: ["..odwddwdo..", ".occcccccco.", ".osccddccso.", ".osccddccso."], back: ["..oddddddo..", ".occddddcco.", ".osccccccso.", ".osccccccso."],
    side: ["...odddo....", "..odcccco...", "..occcsco...", "..occcsco..."] },
  jacket: { front: ["..ocwwwwco..", ".occwwwwcco.", ".oscdwwdcso.", ".osccwwccso."], back: ["..occcccco..", ".occcccccco.", ".osccddccso.", ".osccccccso."],
    side: ["...ocwco....", "..occwcco...", "..occcsco...", "..occcsco..."] },
  suit: { front: ["..ocwaawco..", ".occwaawcco.", ".osccaaccso.", ".osccccccso."], back: BACK_TEE,
    side: ["...ocwco....", "..occacco...", "..occcsco...", "..occcsco..."] },
};

// ---------------------------------------------------------------- waist + legs (rows 11-15), 2 walk frames
const LEGS: Record<string, Record<"front" | "side", Rows[]>> = {
  pants: {
    front: [["..oppppppo..", "..opp..ppo..", "..opp..ppo..", "..obb..bbo..", "...oo..oo..."],
            ["..oppppppo..", ".opp....ppo.", ".opp....ppo.", ".obb....bbo.", "..oo....oo.."]],
    side: [["...opppo....", "...opppo....", "...op.po....", "...ob.bo....", "...oo.oo...."],
           ["...opppo....", "..opo.opo...", "..opo..opo..", "..obo..obo..", "..oo....oo.."]],
  },
  shorts: {
    front: [["..oppppppo..", "..opp..ppo..", "..oss..sso..", "..obb..bbo..", "...oo..oo..."],
            ["..oppppppo..", ".opp....ppo.", ".oss....sso.", ".obb....bbo.", "..oo....oo.."]],
    side: [["...opppo....", "...opppo....", "...os.so....", "...ob.bo....", "...oo.oo...."],
           ["...opppo....", "..opo.opo...", "..oso..oso..", "..obo..obo..", "..oo....oo.."]],
  },
};

// ---------------------------------------------------------------- accessories (16-row overlays)
const FACE: Record<string, Partial<Record<View, Rows>>> = {
  glasses: { front: pad(4, ["..ogeggego.."]), side: pad(4, [".......geg.."]) },
  shades: { front: pad(4, ["...xxxxxx..."]), side: pad(4, [".......xxx.."]) },
  visor: { front: pad(4, ["..oggggggo.."]), side: pad(4, [".......gggo."]) },
};
const HEADWEAR: Record<string, Record<View, Rows>> = {
  cap: { front: pad(0, ["....oooo....", "...okkkko...", "..okkkkkko..", "..oKKKKKKo.."]),
    back: pad(0, ["....oooo....", "...okkkko...", "..okkkkkko..", "..okkkkkko.."]),
    side: pad(0, ["....oooo....", "...okkkko...", "..okkkkkko..", "..okkkKKKKKo"]) },
  beanie: { front: pad(0, [".....kk.....", "...okkkko...", "..okkkkkko..", "..oKKKKKKo.."]),
    back: pad(0, [".....kk.....", "...okkkko...", "..okkkkkko..", "..oKKKKKKo.."]),
    side: pad(0, ["....kk......", "...okkkko...", "..okkkkkko..", "..oKKKKKKo.."]) },
  headphones: { front: pad(0, ["....kkkk....", "...k....k...", "............", ".kk......kk.", ".kk......kk."]),
    back: pad(0, ["....kkkk....", "...k....k...", "............", ".kk......kk.", ".kk......kk."]),
    side: pad(0, ["....kkkk....", "...k...k....", "...k........", "...kkk......", "...kkk......"]) },
  crown: { front: pad(0, ["..k.k..k.k..", "..kkkkkkkk.."]), back: pad(0, ["..k.k..k.k..", "..kkkkkkkk.."]),
    side: pad(0, ["...k.k.k....", "...kkkkkk..."]) },
};
const BACKPACK: Record<string, Record<View, Rows>> = {
  backpack: { front: pad(7, ["...n....n...", "...n....n...", "...n....n..."]),
    back: pad(7, ["...onnnno...", "...onnnno...", "...onnnno...", "....oooo...."]),
    side: pad(7, [".onn........", ".onn........", ".onn........", "..oo........"]) },
  cape: { front: pad(7, [".nn......nn.", "nn........nn", "nn........nn", "nn........nn", "n..........n", "n..........n"]),
    back: pad(7, ["..onnnnnno..", ".onnnnnnnno.", ".onnnnnnnno.", ".onnnnnnnno.", ".onnnnnnnno.", "..onnnnnno.."]),
    side: pad(7, ["onn.........", "onn.........", "onnn........", "onnn........", ".onnn.......", "..oo........"]) },
};

// every template must be exactly 12 wide (a wrong row would silently misdraw)
for (const set of [HEADS, HAIR_EXTRA, TOPS, FACE, HEADWEAR, BACKPACK])
  for (const v of Object.values(set)) for (const rows of Object.values(v)) for (const r of rows as Rows)
    if (r.length !== W) throw new Error(`sprite row is ${r.length} wide: "${r}"`);
for (const l of Object.values(LEGS)) for (const f of [...l.front, ...l.side]) for (const r of f) if (r.length !== W) throw new Error(`leg row "${r}"`);

function shade(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.max(0, Math.min(255, Math.round(v * k)));
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => f(v).toString(16).padStart(2, "0")).join("")}`;
}

function compose(look: Look, view: View, frame: number): Rows {
  const legView = view === "side" ? "side" : "front";
  const rows = [...HEADS[look.hair][view], ...TOPS[look.top][view], ...LEGS[look.bottom][legView][frame]].map((r) => r.split(""));
  const over = (ov?: Rows) => ov?.forEach((r, y) => { for (let x = 0; x < W; x++) if (r[x] !== ".") rows[y][x] = r[x]; });
  over(HAIR_EXTRA[look.hair]?.[view]);
  if (look.back !== "none" && view !== "front") over(BACKPACK[look.back][view]);
  if (look.face !== "none" && view !== "back") over(FACE[look.face][view]);
  if (look.head !== "none") over(HEADWEAR[look.head][view]);
  if (look.back !== "none" && view === "front") over(BACKPACK[look.back].front);
  return rows.map((r) => r.join(""));
}

function paint(rows: Rows, look: Look, mirror: boolean): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d")!;
  const col: Record<string, string> = {
    o: "#05070a", h: look.hairColor, s: look.skin, e: look.eyes, c: look.topColor, d: shade(look.topColor, 0.72),
    w: look.top2, a: look.accent, p: look.pants, b: look.shoes, g: look.faceColor, x: "#0b0f14",
    k: look.headColor, K: shade(look.headColor, 0.72), n: look.backColor,
  };
  rows.forEach((row, y) => {
    for (let x = 0; x < W; x++) {
      const fill = col[row[x]];
      if (!fill) continue;
      g.fillStyle = fill;
      g.fillRect(mirror ? W - 1 - x : x, y, 1, 1);
    }
  });
  g.globalCompositeOperation = "source-atop";   // one-pixel shading for volume
  g.fillStyle = "rgba(0,0,0,0.2)";
  g.fillRect(mirror ? 2 : 7, 8, 2, 4);
  return c;
}

/** The look of an agent without a saved one: stable per id, varied across the city. */
export function lookFor(seed: string): Look { return randomLook(mulberry(hash(seed))); }

export function buildSprites(look: Look): Record<Dir, HTMLCanvasElement[]> {
  const two = (view: View, mirror = false) => [0, 1].map((f) => paint(compose(look, view, f), look, mirror));
  return { down: two("front"), up: two("back"), right: two("side"), left: two("side", true) };
}

const cache = new Map<string, Record<Dir, HTMLCanvasElement[]>>();

export function spritesFor(seed: string, look?: Look | null): Record<Dir, HTMLCanvasElement[]> {
  const key = look ? `${seed}|${JSON.stringify(look)}` : seed;
  const hit = cache.get(key);
  if (hit) return hit;
  const set = buildSprites(look ?? lookFor(seed));
  if (cache.size > 400) cache.clear();
  cache.set(key, set);
  return set;
}
