# -*- coding: utf-8 -*-
"""The front page's frame: intelligence = models x hardware x harnesses.

cards()    three pillar cards under the masthead, each with a live number, the line that
           explains it, a sparkline and a link into that pillar
section()  the harness section of the front page (the other two pillars have theirs)

All numbers are computed from the same data files the pillar pages use, so the front page
can never disagree with them.
"""
import html, json, pathlib
from datetime import date, timedelta

import harness_page
import hardware_section as HS

R = pathlib.Path(__file__).resolve().parent.parent


def esc(t):
    return html.escape(str(t if t is not None else ""), quote=True)


def num(v):
    if v is None:
        return "—"
    a = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            q = v / div
            return ("%.1f" % q if q < 10 else "%.0f" % q) + suf
    return "%d" % round(v)


def spark(values, w=150, h=38, cls="spk"):
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    r = (hi - lo) or 1
    pts = ["%.1f,%.1f" % (i / (len(v) - 1) * (w - 4) + 2, h - 3 - (x - lo) / r * (h - 6)) for i, x in enumerate(v)]
    area = "M2,%d L%s L%.1f,%d Z" % (h, " L".join(pts), w - 2, h)
    lx, ly = pts[-1].split(",")
    return ('<svg class="%s" viewBox="0 0 %d %d" width="%d" height="%d" aria-hidden="true">'
            '<path d="%s" class="a"/><polyline points="%s" class="l"/><circle cx="%s" cy="%s" r="2.6" class="d"/></svg>'
            % (cls, w, h, w, h, area, " ".join(pts), lx, ly))


def _models(rows, labs, as_of):
    d90 = (as_of - timedelta(days=90)).isoformat()
    recent = [r for r in rows if r.get("date") and r["date"] >= d90 and r["date"] <= as_of.isoformat()]
    # releases per month over the last two years
    months = []
    y, m = as_of.year, as_of.month
    for _ in range(24):
        months.append("%04d-%02d" % (y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months.reverse()
    per = [sum(1 for r in rows if (r.get("date") or "")[:7] == mo) for mo in months[:-1]]   # the current month is partial
    best = max((r for r in rows if r.get("ii") is not None), key=lambda r: r["ii"], default=None)
    labname = {L["id"]: L["short"] for L in labs}
    return {
        "k": "Models", "n": "01", "href": "#tlpanel", "cta": "The release record",
        "big": "%d" % len(recent), "unit": "releases in 90 days",
        "line": ("from %d labs. Smartest on the Intelligence Index: <b>%s</b> (%s, %.1f)."
                 % (len({r["lab"] for r in recent}), esc(best["release"]), esc(labname.get(best["lab"], best["lab"])), best["ii"])) if best else "",
        "spark": spark(per), "cap": "releases per month, two years",
    }


def _hardware(as_of):
    rp = R / "data" / "gpu_rental.json"
    S = (json.loads(rp.read_text()) if rp.exists() else {}).get("series", {})
    h = S.get("nvidia-h100")
    big, unit, sp, line = "—", "", "", ""
    if h:
        pts = h["points"]
        ch, _ = HS.yoy(pts)
        big, unit = HS.money(pts[-1][1]), "an hour to rent an H100"
        line = ("<b class=\"%s\">%+.0f%%</b> on a year ago." % ("up" if ch > 0 else "down", ch)) if ch is not None else ""
        sp = spark([p[1] for p in pts[-52:]])
    gw = R / "data" / "gpu_world.json"
    if gw.exists():
        g = json.loads(gw.read_text())
        us = g.get("latest", {}).get("rtx-5090", {}).get("us", {})
        if us.get("median12"):
            line += " An RTX 5090 typically sells for <b>%s</b> in the US; see 17 countries on the map." % HS.money(us["median12"])
    return {"k": "Hardware", "n": "02", "href": "hardware/", "cta": "Prices around the world",
            "big": big, "unit": unit, "line": line, "spark": sp, "cap": "H100 median $/GPU-hour, 12 months"}


def _harnesses(as_of):
    p = harness_page.payload(as_of)
    hs = p["harnesses"]
    total = sum(h["downloads"] or 0 for h in hs)
    series = {}
    for h in hs:
        for wk, n in h["weekly"]:
            series[wk] = series.get(wk, 0) + n
    weeks = sorted(series)[-52:]
    top = p["tbench"]["rows"][0] if p["tbench"]["rows"] else None
    ago = series.get(weeks[0]) if len(weeks) >= 50 else None
    line = ("<b class=\"up\">%.0f&times;</b> a year ago, across %d agents. " % (total / ago, len(hs))) if ago else ""
    if top:
        line += "Best agent on %s: <b>%s + %s</b>, %.1f%%." % (esc(p["tbench"]["title"]), esc(top["agent"]), esc(top["model"]), top["accuracy"])
    return {"k": "Harnesses", "n": "03", "href": "harnesses/", "cta": "The agent tracker",
            "big": num(total), "unit": "agent downloads last week", "line": line,
            "spark": spark([series[w] for w in weeks]), "cap": "weekly npm + PyPI downloads, 12 months"}


def cards(rows, labs, as_of):
    out = []
    for c in (_models(rows, labs, as_of), _hardware(as_of), _harnesses(as_of)):
        out.append(
            '<a class="pcard p-%s" href="%s"><span class="pk"><span class="pn">%s</span>%s</span>'
            '<span class="pv"><b>%s</b> <span>%s</span></span><span class="pl">%s</span>'
            '<span class="ps">%s<small>%s</small></span><span class="pc">%s &rarr;</span></a>'
            % (c["k"].lower(), c["href"], c["n"], c["k"], c["big"], esc(c["unit"]), c["line"], c["spark"], esc(c["cap"]), esc(c["cta"])))
    return ('<div class="pillarsec"><p class="pframe">Intelligence is <b>models</b> &times; <b>hardware</b> &times; <b>harnesses</b>: '
            'what the labs release, what it costs to run, and the agents that put it to work. This site tracks all three.</p>'
            '<div class="pcards">%s</div></div>' % "".join(out))


def section(as_of, num_label="05"):
    p = harness_page.payload(as_of)
    hs = [h for h in p["harnesses"] if h["downloads"]]
    hs.sort(key=lambda h: -h["downloads"])
    top = hs[:8]
    mx = max(h["downloads"] for h in top) if top else 1
    col = {"claude-code": "anthropic", "codex": "openai", "gemini-cli": "google", "qwen-code": "qwen", "kimi-code": "kimi", "deepseek-harness": "deepseek"}
    bars = "".join(
        '<div class="hb"><span class="hn">%s<small>%s</small></span><span class="ht"><i style="width:%.1f%%;background:%s"></i></span>'
        '<span class="hv">%s<small class="%s">%s</small></span></div>'
        % (esc(h["name"]), esc(h["vendor"]), max(1, h["downloads"] / mx * 100),
           "var(--lab-%s)" % col[h["id"]] if h["id"] in col else "var(--p-harnesses)", num(h["downloads"]),
           "up" if (h["growth"] or 0) >= 0 else "down", ("%+.0f%% in 12 wk" % h["growth"]) if h["growth"] is not None else "")
        for h in top)
    rows = p["tbench"]["rows"][:8]
    tmax = max((r["accuracy"] for r in rows), default=1)
    bench = "".join(
        '<div class="hb"><span class="hn">%s<small>%s</small></span><span class="ht"><i style="width:%.1f%%;background:%s"></i></span>'
        '<span class="hv">%.1f%%<small>&plusmn;%.1f</small></span></div>'
        % (esc(r["agent"]), esc(r["model"]), r["accuracy"] / tmax * 100,
           "var(--lab-%s)" % r["lab"] if r.get("lab") else "var(--faint)", r["accuracy"], r.get("ci") or 0)
        for r in rows)
    or_apps = [h for h in p["harnesses"] if h["or_tokens"]]
    or_apps.sort(key=lambda h: -h["or_tokens"])
    or_line = ", ".join("%s %s" % (esc(h["name"]), num(h["or_tokens"])) for h in or_apps[:3])
    return (
        '<section id="harnesses"><div class="sechead"><span class="num">%s</span><h2>The agents around the models</h2>'
        '<span class="sub">A harness turns a model into an agent: it reads the files, runs the tools, checks the work. Which ones '
        'people use, and how much each adds to the same model.</span></div>'
        '<div class="panel pad hz"><div class="hzgrid">'
        '<div><h3 class="hwh">Weekly downloads, latest full week</h3>%s'
        '<p class="note">npm and PyPI downloads: a proxy for use, inflated by continuous integration and blind to native installers. '
        'Tokens per day through OpenRouter tell a different story: %s.</p></div>'
        '<div><h3 class="hwh">%s: harness &times; model</h3>%s'
        '<p class="note">Share of terminal tasks solved, with the 95%% confidence interval; colour is the model&rsquo;s lab. '
        'The same harness with a different model, or the same model in a different harness, can move the score by ten points.</p></div>'
        '</div><p class="hwmore"><a href="harnesses/">Open the harness tracker &rarr;</a> %d agents ranked five ways, adoption '
        'since 2025, release rhythm and the full benchmark.</p></div></section>'
        % (num_label, bars, or_line, esc(p["tbench"]["title"]), bench, len(p["harnesses"])))
