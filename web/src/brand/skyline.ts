// The Smart Flow / EdgeCraft-StrikeCity mark: the city's skyline in pixels. BTC (amber windows), ETH (blue) and SOL
// (violet) towers around the tallest one, a 4h candle in mint whose wick rises above the city: the breakout the
// strategy trades. One character per pixel; the 16 grid is for small sizes and the favicon, the 24 grid for the rest.
// public/favicon.svg is drawn from SKYLINE_16 (regenerate it when this changes).
export const SKYLINE_PAL: Record<string, string> = {"k": "#0d1210", "G": "#1b2a24", "b": "#4a3317", "B": "#f7a531", "o": "#7a5426", "e": "#26305a", "E": "#8fa4ff", "u": "#3a4580", "s": "#35245a", "S": "#c49bff", "z": "#4b3680", "m": "#4efab0", "M": "#c4ffe6"};

export const SKYLINE_16 = [
  "kkkkkkkkkmkkkkkk",
  "kkkkkkkkkmkkkkkk",
  "kkkkkkkkkmkkkkkk",
  "kkkkkkkkmmmkkkkk",
  "kkkkkkkkmMmkkkkk",
  "kkkkkeeemmmkkkkk",
  "kkkkkeEemMmkkkkk",
  "kkkkkeeemmmkssss",
  "bbbbkeEemMmksSSs",
  "bBBbkeeemmmkssss",
  "bbbbkeEemmmksSSs",
  "bBBbkeeekmkkssss",
  "bbbbkeEekmkksSSs",
  "bbbbkeeekmkkssss",
  "GGGGGGGGGGGGGGGG",
  "kkkkkkkkkkkkkkkk",
];

export const SKYLINE_24 = [
  "kkkkkkkkkkkkkkmkkkkkkkkk",
  "kkkkkkkkkkkkkkmkkkkkkkkk",
  "kkkkkkkkkkkkkkmkkkkkkkkk",
  "kkkkkkkkkkkkkkmkkkkkkkkk",
  "kkkkkkkkkkkkkmmmkkkkkkkk",
  "kkkkkkkkkkkkkmMmkkkkkkkk",
  "kkkkkkkkkkkkkmmmkkkkkkkk",
  "kkkkkkkeeeeekmMmkkkkkkkk",
  "kkkkkkkeEeEekmmmkkkkkkkk",
  "kkkkkkkeeeeekmMmkkkkkkkk",
  "kkkkkkkeueuekmmmksssssss",
  "bbbbbbkeeeeekmMmkszszszs",
  "bBBbBbkeEeEekmmmksssssss",
  "bbbbbbkeeeeekmMmksSsSsSs",
  "bBBbBbkeEeEekmmmksssssss",
  "bbbbbbkeeeeekmmmksSsSsSs",
  "bBBbBbkeEeEekkmkksssssss",
  "bbbbbbkeeeeekkmkksSsSsSs",
  "bBBbBbkeEeEekkmkksssssss",
  "bbbbbbkeeeeekkmkksSsSsSs",
  "boobobkeEeEekkmkksssssss",
  "bbbbbbkeeeeekkmkksssssss",
  "GGGGGGGGGGGGGGGGGGGGGGGG",
  "kkkkkkkkkkkkkkkkkkkkkkkk",
];

/** The grid as rectangles, one per horizontal run of a colour (a few dozen elements instead of hundreds). */
export function skylineRuns(rows: string[]): { x: number; y: number; w: number; fill: string }[] {
  const out: { x: number; y: number; w: number; fill: string }[] = [];
  rows.forEach((r, y) => {
    let x = 0;
    while (x < r.length) {
      let e = x;
      while (e < r.length && r[e] === r[x]) e++;
      out.push({ x, y, w: e - x, fill: SKYLINE_PAL[r[x]] ?? SKYLINE_PAL.k });
      x = e;
    }
  });
  return out;
}
