// The landing's entrances, as in the mobile menu: each [data-reveal] block, and the children of each
// [data-reveal-group] one after the other, rise in the first time they come into view. Only with IntersectionObserver
// and without reduced motion (html.reveal-on); otherwise, and before this runs, everything is simply there.
import { useEffect } from "react";

export function useReveal(on: boolean): void {
  useEffect(() => {
    if (!on || typeof IntersectionObserver === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const root = document.documentElement;
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal], [data-reveal-group]"));
    for (const g of els.filter((e) => e.hasAttribute("data-reveal-group"))) {
      Array.from(g.children).forEach((c, i) => (c as HTMLElement).style.setProperty("--i", String(Math.min(i, 8))));
    }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("is-in");
        io.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    root.classList.add("reveal-on");
    els.forEach((e) => io.observe(e));
    return () => { io.disconnect(); root.classList.remove("reveal-on"); };
  }, [on]);
}
