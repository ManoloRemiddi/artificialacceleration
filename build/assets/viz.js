/* viz.js: the small shared toolkit of the hardware and harness pages (inlined at build time).
 *
 * The idea that runs through it: when a filter, metric or sort changes, nothing is redrawn
 * from scratch in a way the eye cannot follow. Every keyed element (a bar, a row, a country)
 * moves from where it was to where it now belongs ("FLIP": First, Last, Invert, Play), and
 * new or departing elements fade. Honours prefers-reduced-motion.
 */
const VIZ = (() => {
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Remember where every [data-key] child of `host` is, run `render`, then animate each
     element from its old box to its new one. */
  function flip(host, render, opts = {}) {
    const dur = opts.duration || 420;
    const before = new Map();
    host.querySelectorAll("[data-key]").forEach(el => before.set(el.dataset.key, el.getBoundingClientRect()));
    render();
    if (REDUCED) return;
    host.querySelectorAll("[data-key]").forEach(el => {
      const b = before.get(el.dataset.key);
      const a = el.getBoundingClientRect();
      if (!b) {
        el.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
                   { duration: dur * 0.8, easing: "cubic-bezier(.2,.7,.3,1)", fill: "backwards", delay: 60 });
        return;
      }
      const dx = b.left - a.left, dy = b.top - a.top;
      const sx = a.width ? b.width / a.width : 1;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5 && Math.abs(sx - 1) < 0.01) return;
      el.animate([{ transform: `translate(${dx}px,${dy}px)` }, { transform: "none" }],
                 { duration: dur, easing: "cubic-bezier(.2,.7,.3,1)" });
    });
  }

  /* Animate an SVG attribute (or style property) from its current value to a new one. */
  function tweenAttr(el, attr, to, dur = 420) {
    const from = parseFloat(el.getAttribute(attr));
    if (REDUCED || isNaN(from)) { el.setAttribute(attr, to); return; }
    const t0 = performance.now();
    const step = t => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.setAttribute(attr, from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /* One floating tooltip per page, positioned next to the pointer and kept on screen. */
  let tipEl = null;
  function tip(html, ev) {
    if (!tipEl) {
      tipEl = document.createElement("div");
      tipEl.className = "vtip";
      tipEl.setAttribute("role", "tooltip");
      document.body.appendChild(tipEl);
    }
    if (!html) { tipEl.style.opacity = 0; return; }
    tipEl.innerHTML = html;
    tipEl.style.opacity = 1;
    const pad = 14, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    let x = ev.clientX + 16, y = ev.clientY + 16;
    if (x + w > innerWidth - pad) x = ev.clientX - w - 16;
    if (y + h > innerHeight - pad) y = ev.clientY - h - 16;
    tipEl.style.transform = `translate(${Math.max(pad, x)}px,${Math.max(pad, y)}px)`;
  }

  const fmt = {
    money(v, cur = "USD") {
      if (v == null || isNaN(v)) return "—";
      const s = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", INR: "₹", AUD: "A$", SGD: "S$", BRL: "R$", SEK: "kr ", AED: "AED " }[cur] || cur + " ";
      if (v >= 1e6) return s + (v / 1e6).toFixed(1) + "M";
      if (v >= 1e4) return s + Math.round(v / 1000) + "k";
      if (v >= 100) return s + Math.round(v).toLocaleString("en-US");
      return s + v.toFixed(2);
    },
    num(v) {
      if (v == null) return "—";
      const a = Math.abs(v);
      if (a >= 1e12) return (v / 1e12).toFixed(2) + "T";
      if (a >= 1e9) return (v / 1e9).toFixed(1) + "B";
      if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
      if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "k";
      return String(Math.round(v));
    },
    pct(v) { return v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(0) + "%"; },
    day(iso) {
      return new Date((iso.length === 7 ? iso + "-15" : iso) + "T00:00:00Z")
        .toLocaleDateString("en-GB", { day: iso.length > 7 ? "numeric" : undefined, month: "short", year: "numeric", timeZone: "UTC" });
    },
  };

  /* Diverging colour for "% against a reference": cool = cheaper, neutral = same, warm =
     dearer. Two hues and a grey midpoint, never a rainbow. Clamped at ±cap. */
  function diverging(p, cap = 60) {
    if (p == null || isNaN(p)) return "var(--nodata)";
    const k = Math.max(-1, Math.min(1, p / cap));
    const hue = k < 0 ? "var(--cool)" : "var(--warm)";
    const share = Math.round(18 + Math.abs(k) * 82);
    return `color-mix(in oklab, ${hue} ${share}%, var(--mid))`;
  }

  /* Small inline sparkline (SVG string) for a numeric series. */
  function spark(values, w = 120, h = 30, color = "currentColor") {
    const v = values.filter(x => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
    const pts = v.map((x, i) => `${(i / (v.length - 1) * (w - 2) + 1).toFixed(1)},${(h - 2 - (x - lo) / r * (h - 4)).toFixed(1)}`);
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${pts[pts.length - 1].split(",")[0]}" cy="${pts[pts.length - 1].split(",")[1]}" r="2.4" fill="${color}"/></svg>`;
  }

  return { flip, tweenAttr, tip, fmt, diverging, spark, REDUCED };
})();
