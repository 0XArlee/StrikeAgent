// EdgeCraft-StrikeCity, the demo: the live product recorded on Strike mainnet, told in fifteen beats.
import React from "react";
import {
  AbsoluteFill, Easing, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";
import { TransitionSeries, springTiming, type TransitionPresentation } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { MONO, SANS } from "./fonts";

const MINT = "#4efab0";
const INK = "#0a0c0b";
const T = 18;   // every transition, in frames

// ---------------------------------------------------------------- pieces
const ease = Easing.bezier(0.16, 1, 0.3, 1);

const Words: React.FC<{ text: string; delay?: number; size: number; weight?: number; color?: string; stagger?: number }> = ({ text, delay = 0, size, weight = 700, color = "#fff", stagger = 3 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <span style={{ display: "inline", fontFamily: SANS, fontSize: size, fontWeight: weight, color, letterSpacing: "-0.02em", lineHeight: 1.08 }}>
      {text.split(" ").map((w, i) => {
        const s = spring({ frame: frame - delay - i * stagger, fps, config: { damping: 200, mass: 0.6 } });
        return (
          <span key={i} style={{ display: "inline-block", overflow: "hidden", verticalAlign: "top", marginRight: "0.26em" }}>
            <span style={{ display: "inline-block", transform: `translateY(${(1 - s) * 105}%)`, opacity: s }}>{w}</span>
          </span>
        );
      })}
    </span>
  );
};

const Kicker: React.FC<{ text: string; delay?: number }> = ({ text, delay = 0 }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame - delay, [0, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const w = interpolate(frame - delay, [0, 20], [0, 56], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, opacity: o, marginBottom: 18 }}>
      <div style={{ width: w, height: 3, background: MINT, boxShadow: `0 0 18px ${MINT}` }} />
      <span style={{ fontFamily: MONO, fontWeight: 600, fontSize: 22, color: MINT, letterSpacing: "0.12em", textTransform: "uppercase" }}>{text}</span>
    </div>
  );
};

const Caption: React.FC<{ kicker: string; title: string; sub?: string; align?: "left" | "right"; top?: boolean }> = ({ kicker, title, sub, align = "left", top }) => {
  const frame = useCurrentFrame();
  const subO = interpolate(frame, [22, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", [top ? "top" : "bottom"]: top ? 80 : 96, [align]: 96, maxWidth: 1060, textAlign: align }}>
      <Kicker text={kicker} delay={4} />
      <div style={{ textShadow: "0 4px 30px rgba(0,0,0,.85)" }}><Words text={title} delay={8} size={74} /></div>
      {sub && <p style={{ fontFamily: SANS, fontSize: 30, color: "rgba(255,255,255,.86)", margin: "22px 0 0", lineHeight: 1.4, opacity: subO,
        textShadow: "0 2px 18px rgba(0,0,0,.9)" }}>{sub}</p>}
    </div>
  );
};

const Shade: React.FC<{ top?: boolean }> = ({ top }) => (
  <AbsoluteFill style={{ background: top
    ? "linear-gradient(0deg, rgba(5,7,6,0) 45%, rgba(5,7,6,.6) 72%, rgba(5,7,6,.94) 100%)"
    : "linear-gradient(180deg, rgba(5,7,6,.15) 0%, rgba(5,7,6,0) 35%, rgba(5,7,6,.55) 68%, rgba(5,7,6,.94) 100%)" }} />
);

/** A recording of the live product, slowly pushing in towards a point of interest. */
const Clip: React.FC<{ src: string; from?: number; zoom?: [number, number]; origin?: string; kicker: string; title: string; sub?: string; dur: number;
  align?: "left" | "right"; top?: boolean; still?: string }> =
  ({ src, from = 0, zoom = [1.0, 1.08], origin = "50% 45%", kicker, title, sub, dur, align, top, still }) => {
    const frame = useCurrentFrame();
    const s = interpolate(frame, [0, dur], zoom, { easing: Easing.inOut(Easing.quad) });
    return (
      <AbsoluteFill style={{ backgroundColor: INK }}>
        <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: origin }}>
          {still ? <Img src={staticFile(`img/${still}`)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <OffthreadVideo src={staticFile(`clips/${src}.mp4`)} startFrom={from} muted style={{ width: "100%", height: "100%" }} />}
        </AbsoluteFill>
        <Shade top={top} />
        <Caption kicker={kicker} title={title} sub={sub} align={align} top={top} />
      </AbsoluteFill>
    );
  };

const Grid: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ backgroundColor: INK, overflow: "hidden" }}>
      <AbsoluteFill style={{
        backgroundImage: "linear-gradient(rgba(78,250,176,.07) 1px, transparent 1px), linear-gradient(90deg, rgba(78,250,176,.07) 1px, transparent 1px)",
        backgroundSize: "64px 64px", backgroundPosition: `0 ${frame * 0.6}px`,
      }} />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, rgba(78,250,176,.16), rgba(10,12,11,0) 55%)" }} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- scenes
const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - 4, fps, config: { damping: 14, mass: 0.8 } });
  const glow = interpolate(frame, [0, 40, 150], [0, 1, 0.6]);
  const lineO = interpolate(frame, [70, 90], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Grid />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
        <Img src={staticFile("logo.svg")} style={{ width: 200, height: 200, transform: `scale(${pop})`, imageRendering: "pixelated",
          filter: `drop-shadow(0 0 ${40 * glow}px rgba(78,250,176,.65))`, borderRadius: 18 }} />
        <div style={{ marginTop: 48 }}><Words text="EdgeCraft-StrikeCity" delay={22} size={120} stagger={0} /></div>
        <div style={{ marginTop: 26 }}><Words text="Strike, alive." delay={44} size={56} weight={600} color={MINT} stagger={4} /></div>
        <p style={{ fontFamily: MONO, fontSize: 24, color: "rgba(255,255,255,.7)", letterSpacing: "0.14em", marginTop: 40, opacity: lineO, textTransform: "uppercase" }}>
          Trading agents and Strike's copy traders, living in one city
        </p>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** The product's own dialogs, cropped and large: the caption on the left, the screens floating on the right. */
const Screens: React.FC<{ imgs: { src: string; w: number; x: number; y: number }[]; kicker: string; title: string; sub: string }> = ({ imgs, kicker, title, sub }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Grid />
      <div style={{ position: "absolute", left: 110, top: 0, bottom: 0, width: 700, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <Kicker text={kicker} delay={4} />
        <Words text={title} delay={8} size={70} />
        <p style={{ fontFamily: SANS, fontSize: 30, color: "rgba(255,255,255,.82)", lineHeight: 1.45, marginTop: 30,
          opacity: interpolate(frame, [26, 44], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>{sub}</p>
      </div>
      <AbsoluteFill style={{ perspective: 2200 }}>
        {imgs.map((m, i) => {
          const s = spring({ frame: frame - 6 - i * 10, fps, config: { damping: 18 } });
          const drift = interpolate(frame, [0, 220], [0, -18 + i * 10]);
          return (
            <Img key={m.src} src={staticFile(`img/${m.src}`)} style={{
              position: "absolute", left: m.x, top: m.y, width: m.w, borderRadius: 16, border: "1px solid rgba(78,250,176,.4)",
              boxShadow: "0 50px 120px rgba(0,0,0,.75), 0 0 70px rgba(78,250,176,.14)",
              transform: `translateY(${(1 - s) * 160 + drift}px) rotateY(-9deg) rotateX(3deg)`, opacity: s,
            }} />
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const MSGS: { icon: string; title: string; body: string; tone?: string; example?: boolean }[] = [
  { icon: "💸", title: "Extreme funding on SKHYNIX", body: "Shorts pay longs 0.035% an hour (about 305% a year): holding that side costs a lot." },
  { icon: "🛡️", title: "Security alarm: Cysic dangles a 10% bounty, hacker pours loot into Tornado Cash", body: "Copies run by agents pause while it lasts. Source: Cointelegraph.", tone: "#f43f5e" },
  { icon: "📊", title: "Strike now", body: "BTC 81,494 · ETH 2,396 · SOL 104.11\nOpen interest 1.22 M$ · 64% of positions long" },
  { icon: "🚨", title: "SHORT TSLA 2.1% from liquidation", body: "Your copy's sub-account: mark 431.50, liquidation 440.60. Add margin or reduce it now.", tone: "#f43f5e", example: true },
  { icon: "⚠️", title: "Your copy didn't take LONG ETH", body: "The trader holds it and your copy doesn't: a market it excludes, or not enough margin." , tone: "#fbbf24", example: true },
];

const Telegram: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const phone = spring({ frame, fps, config: { damping: 20 } });
  return (
    <AbsoluteFill>
      <Grid />
      <div style={{ position: "absolute", left: 110, top: 250, width: 820 }}>
        <Kicker text="Alerts · Telegram" delay={4} />
        <Words text="What matters on Strike, the moment it happens." delay={8} size={72} />
        <p style={{ fontFamily: SANS, fontSize: 30, color: "rgba(255,255,255,.82)", lineHeight: 1.45, marginTop: 30,
          opacity: interpolate(frame, [30, 50], [0, 1], { extrapolateRight: "clamp" }) }}>
          Moves, extreme funding, a liquidation radar on Strike's live positions, whales, the security alarm, the US releases.
          Linked to your agent: your liquidation risk and every copy, watched every two minutes.
        </p>
        <p style={{ fontFamily: MONO, fontSize: 28, color: MINT, marginTop: 28, opacity: interpolate(frame, [50, 70], [0, 1], { extrapolateRight: "clamp" }) }}>
          @EdgeCraftStrikeCityBot
        </p>
      </div>
      <div style={{ position: "absolute", right: 150, top: 70, width: 560, height: 940, borderRadius: 64, background: "#101415",
        border: "10px solid #1d2422", boxShadow: "0 50px 140px rgba(0,0,0,.75), 0 0 80px rgba(78,250,176,.15)",
        transform: `translateY(${(1 - phone) * 300}px) rotate(${(1 - phone) * 6}deg)`, opacity: phone, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "34px 30px 22px", borderBottom: "1px solid #232b29", background: "#141a19" }}>
          <Img src={staticFile("logo.svg")} style={{ width: 58, height: 58, borderRadius: 29 }} />
          <div>
            <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 26, color: "#fff" }}>EdgeCraft-StrikeCity</div>
            <div style={{ fontFamily: SANS, fontSize: 20, color: MINT }}>bot</div>
          </div>
        </div>
        <div style={{ padding: "26px 22px", display: "flex", flexDirection: "column", gap: 16 }}>
          {MSGS.map((m, i) => {
            const s = spring({ frame: frame - 24 - i * 34, fps, config: { damping: 16 } });
            return (
              <div key={i} style={{ background: "#1b2321", borderRadius: 22, borderTopLeftRadius: 6, padding: "16px 20px", borderLeft: `4px solid ${m.tone ?? MINT}`,
                transform: `translateY(${(1 - s) * 40}px) scale(${0.92 + s * 0.08})`, opacity: s, transformOrigin: "left top" }}>
                <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 22, color: "#fff", lineHeight: 1.3 }}>{m.icon} {m.title}{m.example && <span style={{ fontFamily: MONO, fontWeight: 500, fontSize: 14, color: "rgba(255,255,255,.55)", border: "1px solid rgba(255,255,255,.25)", borderRadius: 8, padding: "1px 7px", marginLeft: 10, verticalAlign: "middle" }}>example</span>}</div>
                <div style={{ fontFamily: SANS, fontSize: 19, color: "rgba(255,255,255,.78)", lineHeight: 1.4, marginTop: 6, whiteSpace: "pre-line" }}>{m.body}</div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Count: React.FC<{ to: number; delay: number; label: string; suffix?: string; dec?: number }> = ({ to, delay, label, suffix = "", dec = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 }, durationInFrames: 45 });
  return (
    <div style={{ padding: "38px 40px", border: "1px solid rgba(78,250,176,.28)", borderRadius: 24, background: "rgba(16,22,20,.8)",
      transform: `translateY(${(1 - s) * 60}px)`, opacity: Math.min(1, s * 1.5) }}>
      <div style={{ fontFamily: MONO, fontWeight: 600, fontSize: 96, color: MINT, textShadow: `0 0 30px rgba(78,250,176,.45)` }}>
        {(to * s).toFixed(dec)}{suffix}
      </div>
      <div style={{ fontFamily: SANS, fontSize: 28, color: "rgba(255,255,255,.85)", marginTop: 10, lineHeight: 1.35 }}>{label}</div>
    </div>
  );
};

const Stats: React.FC = () => (
  <AbsoluteFill>
    <Grid />
    <AbsoluteFill style={{ padding: "110px 120px" }}>
      <Kicker text="Built on Strike" delay={2} />
      <Words text="A complete product, live on Strike mainnet." delay={6} size={70} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 32, marginTop: 70 }}>
        <Count to={46} delay={20} label="Strike endpoints in six integrations" />
        <Count to={1} delay={28} label="wallet signature for an agent on your own account" />
        <Count to={195} delay={36} label="automated tests, and 282 browser checks per language" />
        <Count to={0.2} dec={2} suffix="%" delay={44} label="builder fee on strategy trades: the revenue" />
      </div>
    </AbsoluteFill>
  </AbsoluteFill>
);

const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 14 } });
  const o = interpolate(frame, [24, 44], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Grid />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
        <Img src={staticFile("logo.svg")} style={{ width: 160, height: 160, transform: `scale(${s})`, filter: "drop-shadow(0 0 40px rgba(78,250,176,.6))", borderRadius: 14 }} />
        <div style={{ marginTop: 40 }}><Words text="Come and walk around." delay={10} size={96} /></div>
        <p style={{ fontFamily: MONO, fontSize: 40, color: MINT, marginTop: 40, opacity: o }}>edgecraft-strikecity.pages.dev</p>
        <p style={{ fontFamily: SANS, fontSize: 28, color: "rgba(255,255,255,.75)", marginTop: 18, opacity: o }}>
          Live on Strike mainnet · @EdgeCraftStrikeCityBot · Strike Hackathon 2026
        </p>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** A thin progress line along the bottom, over everything. */
const Progress: React.FC<{ total: number }> = ({ total }) => {
  const frame = useCurrentFrame();
  return <div style={{ position: "absolute", left: 0, bottom: 0, height: 5, width: `${(frame / total) * 100}%`, background: MINT, boxShadow: `0 0 16px ${MINT}` }} />;
};

// ---------------------------------------------------------------- the cut
type Beat = { dur: number; el: (dur: number) => React.ReactNode };
const BEATS: Beat[] = [
  { dur: 150, el: () => <Intro /> },
  { dur: 330, el: (d) => <Clip dur={d} src="flyover" from={30} zoom={[1.0, 1.06]} kicker="The city" title="Every character is real state on Strike."
    sub="Agents walk because something happened in their accounts. The traders people copy stand where their positions are." /> },
  { dur: 285, el: (d) => <Clip dur={d} src="traders" from={20} zoom={[1.02, 1.0]} kicker="Strike's copy traders" title="The traders people copy, walking the city."
    sub="Each with the people copying them behind, and the logos of what they hold." align="right" /> },
  { dur: 300, el: (d) => <Clip dur={d} src="car" from={60} zoom={[1.05, 1.3]} origin="50% 84%" top kicker="Live trades" title="Every car is a real trade on Strike mainnet."
    sub="Green when the taker bought, red when they sold. Press one and it says which trade it is." /> },
  { dur: 320, el: (d) => <Clip dur={d} src="strike_hall" from={15} kicker="Strike Finance, inside" title="Strike's own numbers, live."
    sub="Daily volume, open interest, users, TVL, funding against Binance, Bybit and OKX, the vaults." /> },
  { dur: 300, el: (d) => <Clip dur={d} src="strategies" from={20} zoom={[1.0, 1.05]} origin="40% 35%" kicker="The marketplace" title="Strategies, backtested with every cost."
    sub="Smart Flow and Smart Flow Pyramid: their rules, their risk and their full backtest, in plain view." /> },
  { dur: 240, el: () => <Screens imgs={[{ src: "dlg-character.png", w: 640, x: 860, y: 190 }, { src: "dlg-review.png", w: 440, x: 1400, y: 70 }]}
    kicker="Your agent" title="One signature. Your own Strike account."
    sub="Builder connect: create your character, pick a strategy, and the review says exactly what the agent can and can never do." /> },
  { dur: 285, el: (d) => <Clip dur={d} src="arena" from={10} kicker="The Copy Arena" title="Whom to copy, measured on every copy."
    sub="The Strike City score, re-tested every hour in public on every copy Strike has published." /> },
  { dur: 225, el: () => <Screens imgs={[{ src: "dlg-copy.png", w: 900, x: 900, y: 110 }]} kicker="Copy with your agent"
    title="A signed plan, run on Strike's own copy trading." sub="Your rules, your stop-loss, your sub-accounts. Strike enforces the stop on its side." /> },
  { dur: 285, el: (d) => <Clip dur={d} src="news" from={10} kicker="The News Tower" title="News, measured on Strike's price."
    sub="A reading per market, and an alarm that pauses copies when an exchange or a protocol is hit." /> },
  { dur: 240, el: (d) => <Clip dur={d} src="alerts" still="alert-badge.png" zoom={[1.0, 1.35]} origin="61% 23%" kicker="Alerts, in the city" title="Each alert glows over its building."
    sub="Funding at the Funding Cafe, the liquidation radar over Liquidation Alley, moves over their tower." /> },
  { dur: 300, el: () => <Telegram /> },
  { dur: 255, el: (d) => <Clip dur={d} src="results" from={0} zoom={[1.0, 1.05]} origin="80% 50%" kicker="Results" title="Everything in the open."
    sub="The strategies next to their backtests, the copy pilot, Strike's copy trading, the ranking." /> },
  { dur: 210, el: () => <Stats /> },
  { dur: 180, el: () => <Outro /> },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PRESENT: TransitionPresentation<any>[] = [
  fade(), slide({ direction: "from-right" }), fade(), wipe({ direction: "from-left" }), slide({ direction: "from-bottom" }), fade(),
  slide({ direction: "from-right" }), wipe({ direction: "from-right" }), fade(), slide({ direction: "from-left" }), fade(),
  wipe({ direction: "from-bottom" }), fade(), fade(),
];

export const TOTAL = BEATS.reduce((s, b) => s + b.dur, 0) - (BEATS.length - 1) * T;

export const Demo: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: INK }}>
    <TransitionSeries>
      {BEATS.flatMap((b, i) => [
        <TransitionSeries.Sequence key={`s${i}`} durationInFrames={b.dur}>{b.el(b.dur)}</TransitionSeries.Sequence>,
        ...(i < BEATS.length - 1 ? [<TransitionSeries.Transition key={`t${i}`} presentation={PRESENT[i % PRESENT.length]}
          timing={springTiming({ config: { damping: 200 }, durationInFrames: T })} />] : []),
      ])}
    </TransitionSeries>
    <Progress total={TOTAL} />
  </AbsoluteFill>
);
