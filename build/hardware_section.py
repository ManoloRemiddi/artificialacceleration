# -*- coding: utf-8 -*-
"""Section 04 on the main page: what it costs to run it yourself (a summary; the full
tracker with every vendor and market is site/hardware/, built by hardware_page.py).

Sources, kept visibly apart:
  data/gpu_rental.json  automatic, weekly, GetDeploying open dataset (CC BY 4.0)
  build/hardware.json   purchase prices with a source per number (v2, see hwdata.py),
                        re-checked monthly by the price agent

Everything is drawn here as static SVG at build time; colours are CSS variables so
the theme switch still applies.
"""
import html, json, pathlib
from datetime import date

import hwdata

R = pathlib.Path(__file__).resolve().parent.parent


def esc(t):
    return html.escape(str(t), quote=True)


def money(v):
    if v is None:
        return "—"
    if v >= 1e6:
        return "$%.1fM" % (v / 1e6)
    if v >= 10000:
        return "$%.0fk" % (v / 1000)
    if v >= 1000:
        return "$%s" % format(int(round(v)), ",")
    return "$%.2f" % v


MIN_PROVIDERS = 3      # below this a "median" is one or two listings, and one listing moves it


def yoy(points):
    """Change against the week closest to 52 weeks before the latest, if the series is that
    long and both ends are a real market (enough providers), not a single listing."""
    last_d, last_v = date.fromisoformat(points[-1][0]), points[-1][1]
    older = [p for p in points if (last_d - date.fromisoformat(p[0])).days >= 357]
    if not older:
        return None, None
    base = older[-1]
    if base[3] < MIN_PROVIDERS or points[-1][3] < MIN_PROVIDERS:
        return None, base
    return (last_v - base[1]) / base[1] * 100, base


# ---- colour: one hue per vendor, stepped by generation (ordinal, so light -> strong) ----
NV_STEPS = {"nvidia-a100": 34, "nvidia-h100": 52, "nvidia-h200": 68, "nvidia-b200": 84, "nvidia-b300": 100,
            "nvidia-rtx-3090": 40, "nvidia-rtx-4090": 60, "nvidia-rtx-5090": 80, "nvidia-rtx-pro-6000": 100}
AMD_STEPS = {"amd-mi300x": 50, "amd-mi325x": 72, "amd-mi355x": 100}
INTEL_STEPS = {"intel-gaudi2": 70, "intel-gaudi3": 100}


def hue(slug):
    if slug in AMD_STEPS:
        return "color-mix(in srgb, var(--hw-amd) %d%%, var(--panel))" % AMD_STEPS[slug]
    if slug in INTEL_STEPS:
        return "color-mix(in srgb, var(--hw-intel) %d%%, var(--panel))" % INTEL_STEPS[slug]
    return "color-mix(in srgb, var(--hw-nv) %d%%, var(--panel))" % NV_STEPS.get(slug, 70)


def rental_chart(series, slugs, title, aria):
    """Small multiple: weekly median $/GPU-hour, one line per GPU, labelled at the end."""
    pts = {s: series[s]["points"] for s in slugs if s in series}
    if not pts:
        return ""
    W, H, PL, PR, PT, PB = 660, 270, 44, 214, 16, 26
    d0 = min(date.fromisoformat(p[0][0]) for p in pts.values())
    d1 = max(date.fromisoformat(p[-1][0]) for p in pts.values())
    span = max(1, (d1 - d0).days)
    vmax = max(p[1] for ps in pts.values() for p in ps) * 1.12
    step = next(s for s in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10) if vmax / s <= 6)
    x = lambda iso: PL + (date.fromisoformat(iso) - d0).days / span * (W - PL - PR)
    y = lambda v: PT + (H - PT - PB) * (1 - v / vmax)
    o = ['<svg class="hwchart" viewBox="0 0 %d %d" width="100%%" role="img" aria-label="%s">' % (W, H, esc(aria))]
    v = 0
    while v <= vmax:
        o.append('<line class="ax" x1="%d" x2="%d" y1="%.1f" y2="%.1f" opacity="%s"/>' % (PL, W - PR, y(v), y(v), "1" if v == 0 else ".22"))
        o.append('<text class="axl" x="%d" y="%.1f" text-anchor="end">$%s</text>' % (PL - 6, y(v) + 3.5, ("%g" % v)))
        v = round(v + step, 4)
    # month ticks: first of each quarter-ish month that falls inside
    m = date(d0.year, d0.month, 1)
    while m <= d1:
        if m >= d0 and m.month in (1, 4, 7, 10):
            o.append('<text class="axl" x="%.1f" y="%d" text-anchor="middle">%s</text>'
                     % (x(m.isoformat()), H - 6, m.strftime("%b ’%y")))
        m = date(m.year + (m.month // 12), m.month % 12 + 1, 1)
    labels = []
    for s, ps in pts.items():
        d = " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % (x(p[0]), y(p[1])) for i, p in enumerate(ps))
        dash = ' stroke-dasharray="5 3"' if s in AMD_STEPS else ' stroke-dasharray="1.5 2.5"' if s in INTEL_STEPS else ""
        o.append('<path class="hwline" d="%s" style="stroke:%s"%s/>' % (d, hue(s), dash))
        ch, _ = yoy(ps)
        last = ps[-1]
        o.append('<circle cx="%.1f" cy="%.1f" r="3" style="fill:%s"><title>%s · %s/hr median, week of %s, %d providers</title></circle>'
                 % (x(last[0]), y(last[1]), hue(s), esc(series[s]["name"]), money(last[1]), last[0], last[3]))
        labels.append([y(last[1]), s, last[1], ch, last[3]])
    # end labels: in dot order, pushed apart so none overlap
    labels.sort()
    for i in range(1, len(labels)):
        if labels[i][0] - labels[i - 1][0] < 14:
            labels[i][0] = labels[i - 1][0] + 14
    for ly, s, val, ch, nprov in labels:
        chtxt = ("" if ch is None else (' <tspan class="%s">%+.0f%%</tspan>' % ("up" if ch > 0 else "down", ch)))
        if nprov < MIN_PROVIDERS:
            chtxt = ' <tspan class="thin">%d provider%s</tspan>' % (nprov, "" if nprov == 1 else "s")
        o.append('<text class="hwlab" x="%d" y="%.1f"><tspan style="fill:%s">%s</tspan> <tspan class="v">%s</tspan>%s</text>'
                 % (W - PR + 8, ly + 4, hue(s), esc(series[s]["name"]), money(val), chtxt))
    o.append('</svg>')
    return '<figure class="hwfig"><figcaption>%s</figcaption><div class="hwscroll">%s</div></figure>' % (title, "".join(o))


FEATURED = ["rtx-5090", "rtx-5080", "rtx-pro-6000", "dgx-spark-128", "asus-gx10", "framework-desktop-128",
            "gmktec-evo-x2-128", "amd-radeon-ai-pro-r9700", "arc-pro-b60", "arc-pro-b70", "mac-studio-m3-ultra-96", "rtx-3090"]


def home_rows(hw, featured_only=False):
    """US launch price and latest US price per product, the like-for-like pair."""
    rows = []
    for pr in hw["products"]:
        if featured_only and pr["id"] not in FEATURED:
            continue
        first, last = hwdata.first_last(pr, "US")
        if not first or first is last:
            continue
        rows.append({"name": pr["name"], "vendor": pr["vendor"], "kind": pr.get("kind") or pr["segment"],
                     "mem_gb": pr.get("mem_gb"), "bw_gbps": pr.get("bw_gbps"), "launch": first, "now": last, "src": last.get("src")})
    return rows


def dumbbell(rows):
    """Launch price -> today (US), one row per machine, across vendors."""
    rows = sorted(rows, key=lambda h: h["now"]["amount"])
    W, RH, PL, PR, PT = 1360, 40, 420, 170, 30
    H = PT + RH * len(rows) + 30
    vmax = max(max(h["now"].get("high") or h["now"]["amount"], h["launch"]["amount"]) for h in rows) * 1.06
    step = next(s for s in (1000, 2000, 2500, 5000, 10000) if vmax / s <= 8)
    x = lambda v: PL + v / vmax * (W - PL - PR)
    o = ['<div class="hwscroll wide"><svg class="hwchart" viewBox="0 0 %d %d" width="100%%" role="img" '
         'aria-label="Launch price against today\'s price for home-lab AI hardware, US">' % (W, H)]
    v = 0
    while v <= vmax:
        o.append('<line class="ax" x1="%.1f" x2="%.1f" y1="%d" y2="%d" opacity=".18"/>' % (x(v), x(v), PT - 8, H - 26))
        o.append('<text class="axl" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x(v), H - 10, ("$%gk" % (v / 1000)) if v else "$0"))
        v += step
    o.append('<text class="axl d" x="%d" y="14">launch price</text><text class="axl d" x="%d" y="14">\u25cf today</text>' % (PL, PL + 92))
    o.append('<text class="axl d" x="%d" y="14" text-anchor="end">today, per GB</text>' % (W - 6))
    for i, h in enumerate(rows):
        cy = PT + RH * i + RH / 2
        lp, np_ = h["launch"]["amount"], h["now"]["amount"]
        ch = (np_ - lp) / lp * 100
        lo, hi = h["now"].get("low") or np_, h["now"].get("high") or np_
        o.append('<text class="hwname" x="0" y="%.1f">%s</text>' % (cy - 3, esc(h["name"])))
        spec = " \u00b7 ".join(x for x in (esc(h["vendor"]), esc(h["kind"]), ("%d GB" % h["mem_gb"]) if h.get("mem_gb") else "",
                                           ("%s GB/s" % format(h["bw_gbps"], ",")) if h.get("bw_gbps") else "") if x)
        o.append('<text class="axl" x="0" y="%.1f">%s</text>' % (cy + 12, spec))
        if hi > lo:
            o.append('<line class="hwrange" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % (x(lo), x(hi), cy, cy))
        o.append('<line class="hwmove %s" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % ("up" if ch > 0 else "down", x(lp), x(np_), cy, cy))
        o.append('<circle class="hwlaunch" cx="%.1f" cy="%.1f" r="5"><title>Launch %s: %s</title></circle>' % (x(lp), cy, h["launch"]["date"], money(lp)))
        o.append('<circle class="hwnow %s" cx="%.1f" cy="%.1f" r="6"><title>%s: %s (%s)</title></circle>'
                 % ("up" if ch > 0 else "down", x(np_), cy, h["now"]["date"], money(np_), esc(h["now"].get("basis", ""))))
        o.append('<text class="hwpct %s" x="%.1f" y="%.1f">%+.0f%%</text>' % ("up" if ch > 0 else "down", max(x(np_), x(hi)) + 10, cy + 4, ch))
        if h.get("mem_gb"):
            o.append('<text class="hwper" x="%d" y="%.1f" text-anchor="end">%s/GB</text>' % (W - 6, cy + 4, money(np_ / h["mem_gb"])))
    o.append('</svg></div>')
    return "".join(o)


def latest_buy(a):
    return sorted(a.get("buy", []), key=lambda b: b["date"])[-1] if a.get("buy") else None


def dc_table(accels, series, rates=None, limit_vendors=None):
    """Datacenter parts: memory, purchase estimate, live rent (where a rental market exists)."""
    rates = rates or hwdata.Rates()
    o = ['<div class="hwscroll"><table class="hwtable"><thead><tr><th>Accelerator</th><th>Vendor</th><th class="n">Memory</th>'
         '<th class="n">Bandwidth</th><th class="n">Buy (est.)</th><th class="n">Rent now</th><th class="n">vs a year ago</th>'
         '<th class="n">Break-even</th></tr></thead><tbody>']
    for g in accels:
        if limit_vendors and g["vendor"] not in limit_vendors:
            continue
        s = series.get(g.get("rental_slug") or "")
        rent = s["points"][-1][1] if s else None
        ch, _ = yoy(s["points"]) if s else (None, None)
        b = latest_buy(g)
        lo = hi = None
        if b:
            lo = rates.to_usd(b["low"], b["currency"], b["date"]) if b.get("low") is not None else None
            hi = rates.to_usd(b.get("high") or b["low"], b["currency"], b["date"]) if b.get("low") is not None else None
        buy = ("%s\u2013%s" % (money(lo), money(hi)) if lo and hi and abs(hi - lo) > 1 else money(lo)) if lo else "not published"
        be = "\u2248 %.0f months" % ((lo + hi) / 2 / rent / (24 * 30.4)) if (lo and rent and g["segment"] == "datacenter") else "\u2014"
        name = '<b>%s</b>%s%s' % (esc(g["name"]), (' <a class="src" href="%s">source</a>' % esc(b["src"])) if b and b.get("src") else "",
                                  ('<br><span>%s</span>' % esc(g["what"])) if g.get("what") else "")
        o.append('<tr class="%s"><td>%s</td><td>%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td>'
                 '<td class="n">%s</td><td class="n %s">%s</td><td class="n">%s</td></tr>' % (
                     "rack" if g["segment"] == "rack" else "", name, esc(g["vendor"]),
                     ("%d GB" % g["mem_gb"]) if g.get("mem_gb") else "", ("%.1f TB/s" % (g["bw_gbps"] / 1000)) if g.get("bw_gbps") else "",
                     buy, ("%s/hr" % money(rent)) if rent else "\u2014",
                     "up" if (ch or 0) > 0 else "down", ("%+.0f%%" % ch) if ch is not None else "\u2014", be))
    o.append('</tbody></table></div>')
    return "".join(o)


RECHECK_DAYS = 45      # the monthly agent proposes fresh prices; past this, say so on the page


def checked_note(hw, as_of):
    """'Checked by hand on …', plus a visible flag once the hand-checked prices are overdue."""
    checked = date.fromisoformat(hw["checked"])
    age = (as_of - checked).days
    txt = "Checked on %s." % checked.strftime("%-d %b %Y")
    if age > RECHECK_DAYS:
        txt += ' <b class="due">Due for re-check: these purchase prices are %d days old.</b>' % age
    return txt


def render(as_of=None):
    as_of = as_of or date.today()
    hw = json.loads((R / "build" / "hardware.json").read_text())
    rates = hwdata.Rates()
    rp = R / "data" / "gpu_rental.json"
    rental = json.loads(rp.read_text()) if rp.exists() else {"series": {}, "as_of": None}
    S = rental["series"]
    dc_slugs = ["nvidia-a100", "nvidia-h100", "nvidia-h200", "nvidia-b200", "nvidia-b300",
                "amd-mi300x", "amd-mi325x", "amd-mi355x", "intel-gaudi2"]
    home_slugs = ["nvidia-rtx-3090", "nvidia-rtx-4090", "nvidia-rtx-5090", "nvidia-rtx-pro-6000"]

    # the headline, computed: what renting the workhorse and the newest part cost now vs a year ago
    head = []
    for s in ("nvidia-h100", "nvidia-b200"):
        if s in S:
            ch, _ = yoy(S[s]["points"])
            if ch is not None:
                head.append("%s <b>%s/hr</b> (<b class=\"%s\">%+.0f%%</b>)" % (S[s]["name"], money(S[s]["points"][-1][1]), "up" if ch > 0 else "down", ch))
    home = home_rows(hw, featured_only=True)
    moves = [(((h["now"]["amount"] - h["launch"]["amount"]) / h["launch"]["amount"] * 100), h["name"]) for h in home]
    risen = [m for m in moves if m[0] > 0]
    cheaper = [n for c, n in moves if c <= 0]
    kicker = ("Renting a datacenter GPU costs more than a year ago: %s. " % ", ".join(head) if head else "")
    if moves:
        kicker += "<b>%d of %d</b> home-lab machines cost more today than at launch, up to <b class=\"up\">+%.0f%%</b>" % (
            len(risen), len(moves), max(m[0] for m in moves))
        kicker += ("; only %s is cheaper." % " and ".join(cheaper)) if cheaper else "."

    o = ['<section id="hardware"><div class="sechead"><span class="num">04</span><h2>What it costs to run it yourself</h2>'
         '<span class="sub">The hardware side of acceleration. Faster models need more memory and bandwidth, and in 2026 '
         'demand for both outran supply: prices went up, not down.</span></div>',
         '<div class="panel pad hw"><p class="kicker hwk">%s</p>' % kicker,
         '<p class="hwmore"><a href="hardware/">Open the full hardware tracker \u2192</a> NVIDIA, AMD, Intel, Apple and '
         'China\u2019s accelerators, and prices in the US, Europe, the UK, China and Japan over time.</p>',
         '<h3 class="hwh">Renting it, by the hour</h3><div class="hwgrid">',
         rental_chart(S, dc_slugs, "Datacenter GPUs · median on-demand $/GPU-hour",
                      "Weekly median on-demand rental price per GPU-hour for datacenter GPUs"),
         rental_chart(S, home_slugs, "Home-lab cards, rented in the cloud · median $/GPU-hour",
                      "Weekly median on-demand rental price per GPU-hour for consumer and workstation GPUs"),
         '</div><p class="note">Median on-demand price across every provider listing the GPU that week (spot and reserved '
         'excluded); dashed lines are AMD. The year-on-year change is shown only where at least '
         '3 providers list the GPU at both ends; with fewer, one listing moves the median. Updated weekly from the <a href="%s">GetDeploying open dataset</a>, CC BY 4.0, '
         'data through %s.</p>' % (esc(rental.get("url", "https://getdeploying.com/dataset")), esc(rental.get("as_of") or "—")),
         '<h3 class="hwh">Buying it for a home lab: launch price → today</h3>', dumbbell(home),
         '<p class="note">Memory is what decides which models fit; bandwidth decides how fast they answer. Today’s price '
         'is a street price with its range shown as a faint bar; sources: %s. %s</p>' % (
             ", ".join('<a href="%s">%s</a>' % (esc(h["src"]), esc(h["name"].split(" (")[0])) for h in home if h.get("src")), checked_note(hw, as_of)),
         '<h3 class="hwh">Buying it for a company</h3>', dc_table([a for a in hw["accelerators"] if a["vendor"] in ("NVIDIA", "AMD", "Intel")
                   and a["segment"] in ("datacenter", "rack") and (a.get("buy") or a.get("rental_slug"))
                   and a["id"] not in ("h20", "rtx-pro-6000d")], S, rates),
         '<p class="hwmore"><a href="hardware/#dc">China\u2019s accelerators and the cloud-only chips \u2192</a> Huawei Ascend, '
         'Cambricon, MetaX, Moore Threads and others, with prices from IPO filings and the China market; Google TPU and AWS '
         'Trainium by the hour.</p>',
         '<p class="note">NVIDIA and AMD publish no list prices: purchase figures are reported ranges and differ by up to 2× '
         'between quotes. Break-even is the purchase midpoint divided by today’s median rent, running 24/7, before power, '
         'hosting and staff, so the real figure is longer. %s</p>' % checked_note(hw, as_of),
         '</div></section>']
    return "".join(o)
