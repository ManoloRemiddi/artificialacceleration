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
        return (f'<span class="logo raster"><img src="{L["img"]}" alt="{esc(L["brand"])}" '
                f'width="20" height="20" loading="lazy" decoding="async"></span>')
    cls = "logo"
    if L.get("chip"): cls += " chip"
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
      '<section id="cluster"><div class="sechead"><span class="num">03</span><h2>The 21\u201322 September cluster</h2>'
      '<span class="sub">Three labs, three launches, roughly a day and a half. Anthropic went <b>90 minutes before</b> OpenAI \u2014 not cooperation, upstaging.</span></div>'
      '<div class="panel pad">%s</div></section>' % cluster_svg(),
      '<section id="streams"><div class="sechead"><span class="num">04</span><h2>Lab by lab: the release stream</h2>'
      '<span class="sub">Every notable release, in order, with the gap since that lab\u2019s previous one. Filled bars are faster than the lab\u2019s own median.</span></div>%s</section>' % stream_cards(),
      '<section id="evidence"><div class="sechead"><span class="num">05</span><h2>The words, and what came next</h2>'
      '<span class="sub">What each lab said about pacing, and what shipped immediately afterwards.</span></div>%s</section>' % evidence_cards(),
    ])

def cluster_svg():
    VW, VH, PADL, PADR, AX = 1400, 470, 140, 140, 300
    span = VW - PADL - PADR
    xh = lambda h: PADL + (h / 48) * span
    o = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="Release cluster 21 to 24 September 2026">' % (VW, VH)]
    for h in (0, 24, 48):
        o.append('<line x1="%.1f" y1="24" x2="%.1f" y2="446" stroke="var(--line2)" stroke-dasharray="3 5"/>' % (xh(h), xh(h)))
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--line)"/>' % (xh(0), AX, xh(48), AX))
    for h, lb in [(0,"21 Sep 00:00"),(8,"08:00"),(16,"16:00"),(24,"22 Sep 00:00"),(32,"08:00"),(40,"16:00"),(47.4,"23 Sep")]:
        x = xh(h)
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--line)"/>' % (x, AX-4, x, AX+4))
        o.append('<text x="%.1f" y="%d" fill="var(--faint)" font-family="ui-monospace,monospace" font-size="11" text-anchor="middle">%s</text>' % (x, AX+20, lb))
    for c in SEC.CLUSTER:
        L = labmap[c["lab"]]; x = xh(c["h"]); up = c["dir"] == "up"
        top = (AX - 14 - 118) if up else (AX + 14); ox = c.get("ox", 0); w = c["w"]; cx = x + ox
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" opacity="0.55"/>' % (x, AX, x, (top+118 if up else top), L["hex"]))
        o.append('<rect x="%.1f" y="%d" width="7" height="7" transform="translate(-3.5,-3.5) rotate(45 %.1f %d)" fill="%s"/>' % (x, AX, x, AX, L["hex"]))
        o.append('<foreignObject x="%.1f" y="%d" width="%d" height="118">' % (cx-w/2, top, w))
        o.append('<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Inter,sans-serif;background:var(--panel);border:1px solid var(--line);border-left:3px solid %s;border-radius:10px;padding:10px 12px;height:100%%;box-sizing:border-box">' % L["hex"])
        o.append('<div style="font-size:14px;font-weight:700;color:var(--ink)">%s</div>' % esc(c["name"]))
        o.append('<div style="font-family:ui-monospace,monospace;font-size:11.5px;color:%s;margin-top:4px">%s</div>' % (L["hex"], esc(c["time"])))
        o.append('<div style="font-size:12.5px;color:var(--dim);margin-top:6px;line-height:1.45">%s</div>' % esc(c["note"]))
        o.append('</div></foreignObject>')
    lo, hi = xh(28), xh(29.5)
    # bracket the two pins under the axis, then name the gap in the empty lower-left band
    yb = 442
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--alert)" stroke-dasharray="3 3" opacity="0.85"/>' % (lo, AX + 18, lo, yb))
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--alert)" stroke-dasharray="3 3" opacity="0.85"/>' % (hi, AX + 18, hi, yb))
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--alert)" stroke-dasharray="3 3" opacity="0.85"/>' % (lo, yb, 860, yb))
    o.append('<text x="854" y="%d" fill="var(--alert)" font-family="ui-monospace,monospace" font-size="12" font-weight="700" text-anchor="end">90 minutes apart</text>' % (yb + 4))
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
