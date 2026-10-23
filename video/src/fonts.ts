// IBM Plex (the product's own type), loaded before the first frame is drawn.
import { continueRender, delayRender, staticFile } from "remotion";

const FACES: [string, string, string][] = [
  ["Plex", "ibm-plex-sans-latin-400-normal.woff2", "400"],
  ["Plex", "ibm-plex-sans-latin-600-normal.woff2", "600"],
  ["Plex", "ibm-plex-sans-latin-700-normal.woff2", "700"],
  ["PlexMono", "ibm-plex-mono-latin-500-normal.woff2", "500"],
  ["PlexMono", "ibm-plex-mono-latin-600-normal.woff2", "600"],
];

const handle = delayRender("fonts");
Promise.all(
  FACES.map(([family, file, weight]) => {
    const f = new FontFace(family, `url(${staticFile(`fonts/${file}`)})`, { weight });
    document.fonts.add(f);
    return f.load();
  }),
)
  .then(() => continueRender(handle))
  .catch(() => continueRender(handle));

export const SANS = "Plex, system-ui, sans-serif";
export const MONO = "PlexMono, ui-monospace, monospace";
