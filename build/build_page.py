#!/usr/bin/env python3
"""
Render the site from live data.

  data/releases.json  ->  index.html

Everything numeric (dates, scores, gaps, counts, charts, cadence bars) comes from the
live dataset. build/notes.json only supplies optional human-written colour for a few
releases; build/sections.py supplies the fixed editorial sections.
"""
import json, pathlib, sys, html, re
from datetime import date

R = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "build"))
import sections as SEC

def esc(t): return html.escape(str(t), quote=False)
def to_date(s):
    y, m, d = (int(x) for x in s.split("-")); return date(y, m, d)

LABS = json.loads((R / "build" / "labs.json").read_text())
LOGOS = json.loads((R / "build" / "logos.json").read_text())

def mark_html(lab_id):
    """Real brand mark from the provider's own logo asset, transparent background."""
    L = LOGOS.get(lab_id)
    if not L:
        return ""
    if L.get("img"):
        return (f'<span class="logo backed"><img src="{L["img"]}" alt="{esc(L["brand"])}" '
                f'width="20" height="20" loading="lazy" decoding="async"></span>')
    cls = "logo"
    # "backed" = the mark needs a light plate behind it. It must NOT be called
    # "chip": the lab filter chips are .chip, and their aria-pressed dimming was
    # leaking into these plates.
    if L.get("chip"): cls += " backed"
    if L.get("mono"): cls += " mono"
    return f'<span class="{cls}">{L["svg"]}</span>'

NOTES = json.loads((R / "build" / "notes.json").read_text())
DATA = json.loads((R / "data" / "releases.json").read_text())
rows = DATA["rows"]
labmap = {L["id"]: L for L in LABS}

# ---- rows for the page: notable releases only, in date order ----
page_rows = []
for r in rows:
    L = labmap.get(r["lab"])
    if not L or not r.get("notable"):
        continue
    page_rows.append({
        "d": r.get("date"), "lab": r["lab"], "m": r["release"],
        "ii": r.get("ii"), "gap": r.get("gap"),
        "note": NOTES.get(r["release"], ""),
        "est": 0,
    })
page_rows.sort(key=lambda r: (r["d"], r["lab"]))

if len(page_rows) < 20:
    sys.exit(f"only {len(page_rows)} notable rows — refusing to render a thin page")

# ---- sections, generated from the same data ----
def sections_html():
    return "".join([
      '<section id="cluster"><div class="sechead"><span class="num">03</span><h2>Three launches in 36 hours</h2>'
      '<span class="sub">Anthropic shipped <b>90 minutes before</b> OpenAI. Exactly one hour of that gap is public \u2014 xAI and Anthropic publish no release hour.</span></div>'
      '<div class="panel pad">%s</div></section>' % cluster_svg(),
      '<section id="streams"><div class="sechead"><span class="num">04</span><h2>Lab by lab: the release stream</h2>'
      '<span class="sub">Every notable release, in order, with the gap since that lab\u2019s previous one. Filled bars are faster than the lab\u2019s own median.</span></div>%s</section>' % stream_cards(),
      '<section id="evidence"><div class="sechead"><span class="num">05</span><h2>The words, and what came next</h2>'
      '<span class="sub">What each lab said about pacing, and what shipped immediately afterwards.</span></div>%s</section>' % evidence_cards(),
    ])


def svg_logo(lab_id, x, y, size=24):
    """Place a brand mark inside an SVG document (nested <svg> or <image>)."""
    L = LOGOS.get(lab_id)
    if not L:
        return ""
    if L.get("img"):
        return ('<image x="%d" y="%d" width="%d" height="%d" href="%s" preserveAspectRatio="xMidYMid meet"/>'
                % (x, y, size, size, L["img"]))
    svg = L["svg"]
    svg = re.sub(r'\swidth="[^"]*"', '', svg, count=1)
    svg = re.sub(r'\sheight="[^"]*"', '', svg, count=1)
    inner = ('<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="#ffffff"/>'
             % (x - 1, y - 1, size + 2, size + 2)) if L.get("chip") else ""
    svg = re.sub(r'<svg\b', '<svg x="%d" y="%d" width="%d" height="%d"' % (x, y, size, size), svg, count=1)
    return inner + svg

def cluster_svg():
    """Compact swimlane: three releases on a shared 48-hour axis.
    Replaces a 470px card layout that was mostly empty space."""
    VW, VH = 1400, 196
    X0, X1 = 336, 1390               # label column ends at X0
    hours = 48
    xh = lambda h: X0 + (h / hours) * (X1 - X0)
    ROWS = [
        ("xai",       "Grok 4.7",         12.0, "21 Sep",            "#d8dee9"),
        ("anthropic", "Claude Opus 5.5",  33.0, "22 Sep",            "#d97757"),
        ("openai",    "GPT-6 Sol + Luna", 34.5, "22 Sep",              "#10a37f"),
    ]
    ROWY = [64, 112, 160]

    o = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="Three frontier releases across 21-22 September 2026">' % (VW, VH)]

    # day columns
    for h in (0, 24, 48):
        o.append('<line x1="%.1f" y1="26" x2="%.1f" y2="%d" stroke="var(--line2)" stroke-dasharray="3 5"/>' % (xh(h), xh(h), VH - 12))
    # axis
    o.append('<line x1="%.1f" y1="26" x2="%.1f" y2="26" stroke="var(--line)"/>' % (xh(0), xh(48)))
    for h, lb, anchor in [(0,"21 Sep","start"),(12,"12:00","middle"),(24,"22 Sep","middle"),(36,"12:00","middle"),(48,"23 Sep","end")]:
        x = xh(h)
        o.append('<line x1="%.1f" y1="22" x2="%.1f" y2="30" stroke="var(--line)"/>' % (x, x))
        o.append('<text x="%.1f" y="18" fill="var(--faint)" font-family="ui-monospace,monospace" font-size="11.5" text-anchor="%s">%s</text>' % (x, anchor, lb))

    # the 90-minute window, drawn as a soft band behind the two pins
    lo, hi = xh(33.0), xh(34.5)
    o.append('<rect x="%.1f" y="34" width="%.1f" height="%d" fill="var(--alert)" opacity="0.10"/>' % (lo - 6, (hi - lo) + 12, VH - 52))

    for (lab, name, h, when, _c), y in zip(ROWS, ROWY):
        L = labmap[lab]; x = xh(h)
        # guide from the label column to the pin
        o.append('<line x1="%d" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1" opacity="0.30"/>' % (X0, y, x, y, L["hex"]))
        # label side
        o.append(svg_logo(lab, 4, y - 12, 24))
        o.append('<text x="%d" y="%d" fill="var(--ink)" font-family="Inter,sans-serif" font-size="14" font-weight="700">%s</text>'
                 % (38, y - 1, esc(name)))
        o.append('<text x="%d" y="%d" fill="var(--faint)" font-family="ui-monospace,monospace" font-size="11.5">%s</text>'
                 % (38, y + 15, esc(L["short"])))
        o.append('<text x="%d" y="%d" fill="var(--dim)" font-family="ui-monospace,monospace" font-size="11.5" text-anchor="end">%s</text>'
                 % (X0 - 10, y + 4, esc(when)))
        # the pin
        o.append('<rect x="%.1f" y="%d" width="11" height="11" transform="translate(-5.5,-5.5) rotate(45 %.1f %d)" fill="%s"/>'
                 % (x, y, x, y, L["hex"]))

    # bracket the 90 minutes, labelled once, clear of everything
    yb = 104
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--alert)" stroke-width="1" opacity="0.9"/>' % (lo, yb - 8, lo, yb + 8))
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--alert)" stroke-width="1" opacity="0.9"/>' % (hi, yb - 8, hi, yb + 8))
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--alert)" stroke-dasharray="2 2" opacity="0.9"/>' % (lo, yb, hi, yb))
    o.append('<text x="%.1f" y="%d" fill="var(--alert)" font-family="ui-monospace,monospace" font-size="11" font-weight="700">90 min</text>' % (hi + 8, yb + 4))

    o.append('</svg>')
    return "".join(o)

def stream_cards():
    MAXG = 92
    o = ['<div class="streams">']
    for L in LABS:
        rel = [r for r in page_rows if r["lab"] == L["id"]]
        if not rel: continue
        gaps = [r for r in rel if r.get("gap")]
        gv = sorted(g["gap"] for g in gaps); med = gv[len(gv)//2] if gv else 0
        o.append('<div class="labcard" style="--c:%s">' % L["hex"])
        o.append('<div class="labcard-top">%s<span><span class="nm">%s</span><br><span class="mod">%s</span></span></div>' % (mark_html(L["id"]), esc(L["name"]), esc(L["product"])))
        o.append('<div class="labcard-vals">'
                 '<div><span class="kk">Median gap</span><span class="vv" style="color:%s">%s<small> days</small></span></div>'
                 '<div><span class="kk">Releases</span><span class="vv">%d</span></div>'
                 '<div><span class="kk">Window</span><span class="vv small">%s \u2192 %s</span></div></div>'
                 % (L["hex"], med or "\u2014", len(rel), rel[0]["d"][5:], rel[-1]["d"][5:]))
        if gaps:
            o.append('<div class="cad"><div class="cad-h"><span>since</span><span>gap between releases \u00b7 100%% = %dd</span></div>' % MAXG)
            for g in gaps:
                o.append('<div class="cad-row"><span>%s</span><span class="cad-bar"><span class="cad-fill %s" style="width:%.1f%%;background:%s"></span></span><span class="vv">%dd</span></div>'
                         % (g["d"][5:], "acc" if med and g["gap"] <= med else "", min(g["gap"], MAXG)/MAXG*100, L["hex"], g["gap"]))
            o.append('</div>')
        o.append('<ul class="rel">')
        for r in rel:
            sc = ('<span class="sc" style="color:%s">%s</span>' % (L["hex"], r["ii"])) if r["ii"] else '<span class="sc dim">no score</span>'
            gap = ('<span class="delta %s">+%dd</span>' % ("acc" if med and r["gap"] and r["gap"] <= med else "", r["gap"])) if r.get("gap") else ""
            o.append('<li><span class="dt">%s</span><span><span class="rn">%s %s %s</span>%s</li>'
                     % (r["d"], esc(r["m"]), gap, sc, ('<span class="cap">%s</span>' % esc(r["note"])) if r["note"] else ""))
        o.append('</ul></div>')
    o.append('</div>')
    return "".join(o)

def evidence_cards():
    o = ['<div class="evgrid">']
    for e in SEC.EVIDENCE:
        o.append('<div class="card" style="--c:%s"><h4>%s</h4>' % (labmap[e["colour"]]["hex"], esc(e["title"])))
        for q, a in e.get("quotes", []):
            o.append('<div class="quote"><div class="q">%s</div><div class="a">%s</div></div>' % (q, esc(a)))
        for p in e.get("paras", []): o.append('<p>%s</p>' % p)
        if e.get("foot"): o.append('<p class="foot">%s</p>' % e["foot"])
        o.append('</div>')
    o.append('<div class="card"><h4>How they institutionalised instead of slowing</h4><ul>')
    for k, v in SEC.INSTITUTIONAL: o.append('<li><b>%s</b> \u2014 %s</li>' % (esc(k), v))
    o.append('</ul><p class="foot">Same velocity, more paperwork. Oversight became a feature of the release pipeline, not a brake on it.</p></div>')
    o.append('<div class="card"><h4>Method, and what to verify</h4><ul>')
    for m in SEC.METHOD: o.append('<li>%s</li>' % m)
    o.append('</ul></div></div>')
    return "".join(o)

def main():
    tpl = (R / "build" / "page_template.html").read_text()
    payload = {"labs": [dict(L) for L in LABS], "logos": LOGOS,
               "rows": page_rows,
               "sections": sections_html(),
               "meta": {"compiled": DATA.get("generated_utc", "")[:10],
                        "index_version": "Artificial Analysis Intelligence Index v4.3.2",
                        "source": "artificialanalysis.ai"}}
    out = tpl.replace("__PAYLOAD__", json.dumps(payload))
    if "__PAYLOAD__" in out:
        sys.exit("template placeholder not replaced")
    # publish ONLY the site: the pipeline, data and docs must not go live
    site = R / "site"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(out)
    print(f"index.html written: {len(out)} bytes, {len(page_rows)} release rows")

if __name__ == "__main__":
    main()
