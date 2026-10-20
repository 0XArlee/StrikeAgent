import { useId, useState, type ReactNode } from "react";
import { SKYLINE_16, SKYLINE_24, skylineRuns } from "../brand/skyline";

const S = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const Icon = {
  check: (p: { size?: number }) => <svg {...S} width={p.size ?? 18} height={p.size ?? 18}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>,
  shield: () => <svg {...S}><path d="M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6z" /><path d="M9 12l2 2 4-4" /></svg>,
  close: () => <svg {...S}><path d="M6 6l12 12M18 6L6 18" /></svg>,
  chevron: () => <svg {...S} width={16} height={16}><path d="M9 6l6 6-6 6" /></svg>,
  back: () => <svg {...S} width={16} height={16}><path d="M15 6l-6 6 6 6" /></svg>,
  alert: () => <svg {...S} width={16} height={16}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5h.01" /></svg>,
  external: () => <svg {...S} width={14} height={14}><path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" /></svg>,
  globe: () => <svg {...S}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18" /></svg>,
  pause: () => <svg {...S} width={16} height={16}><path d="M9 5v14M15 5v14" /></svg>,
  play: () => <svg {...S} width={16} height={16}><path d="M7 5l12 7-12 7z" /></svg>,
  logout: () => <svg {...S} width={16} height={16}><path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l-5-5 5-5M5 12h11" /></svg>,
  wallet: () => <svg {...S} width={16} height={16}><path d="M4 7h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a1 1 0 0 1-1-1z" /><path d="M4 7l11-3v3M16 13h.01" /></svg>,
};

/** Smart Flow mark: own brand (never Strike's logo), Strike's mint as accent. */
/** The Smart Flow / EdgeCraft-StrikeCity mark: the city's skyline in pixels (see src/brand/skyline.ts), the 16 grid at
 *  small sizes so every pixel stays crisp, the 24 grid above. */
export function Mark({ size = 32 }: { size?: number }) {
  const rows = size <= 36 ? SKYLINE_16 : SKYLINE_24;
  const n = rows.length;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${n} ${n}`} shapeRendering="crispEdges" aria-hidden="true" className="mark">
      {skylineRuns(rows).map((r) => <rect key={`${r.x}-${r.y}`} x={r.x} y={r.y} width={r.w} height={1} fill={r.fill} />)}
    </svg>
  );
}

export function CardanoLogo({ size = 22 }: { size?: number }) {
  // simplified Cardano glyph (ring of dots), drawn here
  const dots = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2;
    return <circle key={i} cx={12 + Math.cos(a) * 7} cy={12 + Math.sin(a) * 7} r={1.25} fill="#2a71d0" />;
  });
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#fff" />
      {dots}
      <circle cx="12" cy="12" r="2.3" fill="#2a71d0" />
    </svg>
  );
}

/** Dashed-underline term with an accessible tooltip (hover, focus, tap). */
export function Tip({ label, text }: { label: ReactNode; text: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="tip-wrap" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className="tip" aria-describedby={open ? id : undefined} onFocus={() => setOpen(true)}
              onBlur={() => setOpen(false)} onClick={() => setOpen((o) => !o)}
              onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
        {label}
      </button>
      {open && <span role="tooltip" id={id} className="tip-bubble">{text}</span>}
    </span>
  );
}

export function WalletIcon({ name, icon }: { name: string; icon?: string }) {
  if (icon && /^(data:image\/|https:\/\/)/.test(icon)) return <img className="wicon" src={icon} alt="" width={28} height={28} />;
  return <span className="wicon-letter" aria-hidden="true">{name.slice(0, 2)}</span>;
}

export function Alert({ kind, children }: { kind: "err" | "warn" | "ok" | "info"; children: ReactNode }) {
  return (
    <div className={`alert alert-${kind}`} role={kind === "err" ? "alert" : kind === "info" ? "note" : "status"}>
      {kind === "ok" ? <Icon.check size={16} /> : <Icon.alert />}
      <div>{children}</div>
    </div>
  );
}
