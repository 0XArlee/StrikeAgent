// The official logos of markets, as Strike's app shows them: Strike's own image for each of its 33 markets (served
// from /markets), Hyperliquid's for an asset Strike does not list (what Strike's app does too), its letters if neither has one.
import { useState } from "react";
import { ticker } from "./text";

const STRIKE = new Set(["AAOI", "ADA", "BNB", "BTC", "COIN", "CRCL", "CXMT", "DOGE", "DRAM", "ETH", "GOOGL", "HYPE", "LIT", "MINIMAX", "MU",
  "NAS100", "NEAR", "NIGHT", "NVDA", "PUMP", "SKHYNIX", "SNDK", "SOL", "SP500", "SPCX", "TSLA", "UNITREE", "WTI", "XAG", "XAU", "XRP", "ZEC", "ZHIPU"]);

export const logoSrc = (m: string) => {
  const b = m.replace(/-USD$/, "");
  return STRIKE.has(b) ? `/markets/${b.toLowerCase()}.${b === "CXMT" ? "svg" : "webp"}` : `https://app.hyperliquid.xyz/coins/${encodeURIComponent(b)}.svg`;
};

export function MarketLogo({ m }: { m: string }) {
  const [bad, setBad] = useState(false);
  return bad ? <span className="mk-logo mk-txt" aria-hidden="true">{ticker(m).slice(0, 3)}</span>
    : <img className="mk-logo" src={logoSrc(m)} alt="" aria-hidden="true" width={20} height={20} loading="lazy" decoding="async" onError={() => setBad(true)} />;
}

/** Up to two logos, then "+n" for the rest; every name stays in the tooltip and for screen readers. One market also
 *  shows its name. `names` replaces the plain list (a trader's sides: "LONG BTC, SHORT ETH"). */
export function MarketLogos({ markets, label, names }: { markets: string[]; label?: string; names?: string }) {
  if (!markets.length) return null;
  const all = names ?? markets.map(ticker).join(", ");
  const rest = markets.length - 2;
  return (
    <span className="mk-logos" title={all}>
      <span className="sr-only">{label ? `${label}: ` : ""}{all}</span>
      <span className="mk-stack" aria-hidden="true">{markets.slice(0, 2).map((m) => <MarketLogo key={m} m={m} />)}</span>
      {rest > 0 && <span className="mk-more" aria-hidden="true">+{rest}</span>}
      {markets.length === 1 && !names && <span className="mk-one" aria-hidden="true">{ticker(markets[0])}</span>}
    </span>
  );
}
