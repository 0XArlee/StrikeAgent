// The landing's entrances, as in the mobile menu: each [data-reveal] block, and the children of each
// [data-reveal-group] one after the other, rise in the first time they come into view. Only with IntersectionObserver
// and without reduced motion (html.reveal-on); otherwise, and before this runs, everything is simply there.
import { useEffect } from "react";

export function useReveal(on: boolean, page = ""): void {   // page: runs again for each page of the landing
  useEffect(() => {
    if (!on || typeof IntersectionObserver === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const root = document.documentElement;
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal], [data-reveal-group]"));
    for (const g of els.filter((e) => e.hasAttribute("data-reveal-group"))) {
      Array.from(g.children).forEach((c, i) => (c as HTMLElement).style.setProperty("--i", String(Math.min(i, 5))));
    }
    // it starts a little before a block enters the screen, so content is never waited for; one already scrolled past
    // (a jump from the menu) is simply there
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting && e.boundingClientRect.bottom > 0) continue;
        e.target.classList.add(e.isIntersecting ? "is-in" : "is-past");
        io.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px 12% 0px", threshold: 0 });
    root.classList.add("reveal-on");
    els.forEach((e) => io.observe(e));
    return () => { io.disconnect(); root.classList.remove("reveal-on"); };
  }, [on, page]);
}
