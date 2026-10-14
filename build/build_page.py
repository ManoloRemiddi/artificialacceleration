#!/usr/bin/env python3
"""
Render the site from live data.

  data/releases.json  ->  index.html

Everything numeric (dates, scores, gaps, counts, charts, cadence bars) comes from the
live dataset. build/notes.json only supplies optional human-written colour for a few
releases; build/sections.py supplies the fixed editorial sections.
"""
import json, pathlib, sys, html, re
from datetime import date, timedelta
from statistics import median, mean

R = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "build"))
import sections as SEC
import extras
import hardware_section

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

sys.path.insert(0, str(R / "scripts"))
import acceleration_index as ACCEL      # noqa: E402

def norm(name):
    """Match release names however the API punctuates them: 'Max (0902)' == 'Max 0902'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())

NOTES = {norm(k): v for k, v in json.loads((R / "build" / "notes.json").read_text()).items()}
DATA = json.loads((R / "data" / "releases.json").read_text())
rows = extras.assign_slugs(DATA["rows"])
STATEMENTS = json.loads((R / "build" / "statements.json").read_text())
labmap = {L["id"]: L for L in LABS}

def lab_var(lab_id):
    """A lab's colour as a CSS variable, so the theme switch recolours everything."""
    return "var(--lab-%s)" % lab_id

def lab_css():
    """Each theme has its own validated steps: the dark ones vanish on white."""
    dark = ";".join("--lab-%s:%s" % (L["id"], L["hex"]) for L in LABS)
    light = ";".join("--lab-%s:%s" % (L["id"], L.get("hex_light", L["hex"])) for L in LABS)
    return ":root{%s}[data-theme=\"light\"]{%s}" % (dark, light)

# ---- rows for the page: notable releases only, in date order ----
page_rows = []
for r in rows:
    L = labmap.get(r["lab"])
    if not L or not r.get("notable"):
        continue
    page_rows.append({
        "d": r.get("date"), "lab": r["lab"], "m": r["release"],
        "ii": r.get("ii"), "gap": r.get("gap"),
        "open": bool(r.get("open")), "price": r.get("price"),
        "note": NOTES.get(norm(r["release"]), ""), "u": r["page"],
        "est": 0,
    })
page_rows.sort(key=lambda r: (r["d"], r["lab"]))

# ---- the whole release stream, for the longer windows ----
# The curated set above is a 12-month editorial artefact: its earliest entry is
# November 2025. Anything longer than a year has to draw on the full record, so
# the page carries both. Short keys keep the payload small.
def _stream_row(r):
    row = {"d": r["date"], "l": r["lab"], "m": r["release"], "u": r["page"],
           "i": (round(r["ii"], 1) if r.get("ii") is not None else None)}
    if r.get("estimated"):
        row["e"] = 1
    if r.get("open"):
        row["o"] = 1
    if r.get("price") is not None:
        row["p"] = r["price"]
    return row


stream_rows = [_stream_row(r) for r in rows]
stream_rows.sort(key=lambda r: (r["d"], r["l"]))

if len(page_rows) < 20:
    sys.exit(f"only {len(page_rows)} notable rows — refusing to render a thin page")

# ---- sections, generated from the same data ----
def sections_html():
    return "".join([
      '<section id="due"><div class="sechead"><span class="num">03</span><h2>Who\u2019s due</h2>'
      '<span class="sub">Each lab\u2019s typical gap between notable releases, against the days since its last one. '
      'A forecast, scored against its own history: the \u00b1 is how far it has missed on average.</span></div>%s</section>' % whos_due(),
      hardware_section.render(),
      '<section id="streams"><div class="sechead"><span class="num">05</span><h2>Lab by lab: the release stream</h2>'
      '<span class="sub">Every notable release, in order, with the gap since that lab\u2019s previous one. Filled bars are faster than the lab\u2019s own median.</span></div>%s</section>' % stream_cards(),
      '<section id="evidence"><div class="sechead"><span class="num">06</span><h2>The words, and what came next</h2>'
      '<span class="sub">What each lab said about pacing, and what shipped immediately afterwards.</span></div>%s</section>' % evidence_cards(),
    ])


def as_of_date():
    return date.fromisoformat((DATA.get("generated_utc") or date.today().isoformat())[:10])


def whos_due():
    """Cadence forecast per lab, from notable releases only (the ones people wait for).
    Expected next = last release + the lab's median gap. Scored by backtest: every past
    release is 'predicted' from the median of the gaps before it, and the average miss
    is shown, so a lab with an erratic rhythm wears a wide error bar."""
    today = as_of_date()
    items = []
    for L in LABS:
        rel = sorted((r for r in rows if r["lab"] == L["id"] and r.get("notable")), key=lambda r: r["date"])
        if len(rel) < 3:
            continue
        ds = [to_date(r["date"]) for r in rel]
        gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
        med = int(round(median(gaps)))
        since = (today - ds[-1]).days
        errs = [abs(gaps[k] - median(gaps[:k])) for k in range(2, len(gaps))]
        items.append(dict(L=L, last=rel[-1], med=med, since=since, due=med - since,
                          eta=ds[-1] + timedelta(days=med), mae=round(mean(errs)) if errs else None, n=len(errs)))
    items.sort(key=lambda it: it["due"])
    scale = max(max(it["since"], it["med"]) for it in items) * 1.08
    o = ['<div class="panel pad due">']
    for it in items:
        L, last = it["L"], it["last"]
        if it["due"] < 0:
            status, cls = "overdue by %d day%s" % (-it["due"], "" if it["due"] == -1 else "s"), "late"
        elif it["due"] == 0:
            status, cls = "due today", "now"
        else:
            status, cls = "due in ~%d day%s" % (it["due"], "" if it["due"] == 1 else "s"), ""
        acc = ("\u00b1%dd over %d check%s" % (it["mae"], it["n"], "" if it["n"] == 1 else "s")) if it["mae"] is not None else "too few releases to score"
        o.append(
            '<div class="duerow %s" style="--c:%s">'
            '<div class="duelab">%s<span><b>%s</b><a href="m/%s/">%s</a> \u00b7 %s</span></div>'
            '<div class="duebar" role="img" aria-label="%d days since last release; typical gap %d days">'
            '<span class="fill" style="width:%.1f%%"></span><span class="med" style="left:%.1f%%"><i>median %dd</i></span></div>'
            '<div class="duestat"><b>%s</b><span>expected \u2248 %s \u00b7 %s</span></div></div>'
            % (cls, lab_var(L["id"]), mark_html(L["id"]), esc(L["short"]), last["page"], esc(last["release"]),
               ("today" if it["since"] == 0 else "1 day ago" if it["since"] == 1 else "%d days ago" % it["since"]),
               it["since"], it["med"], min(it["since"], scale) / scale * 100, it["med"] / scale * 100,
               it["med"], status, it["eta"].strftime("%-d %b"), acc))
    o.append('</div>')
    return "".join(o)


def said_then_shipped():
    """The promise ledger, computed: for each dated call to slow down, what that lab and
    the other eight shipped next, read off the live record."""
    o = ['<div class="card ledger"><h4>Said, then shipped \u2014 computed from the record</h4><table>'
         '<thead><tr><th>Said</th><th>That lab\u2019s next release</th><th>All nine labs, next 30 days</th></tr></thead><tbody>']
    for st in STATEMENTS:
        t0 = to_date(st["d"])
        mine = sorted((r for r in rows if r["lab"] == st["lab"] and to_date(r["date"]) > t0), key=lambda r: r["date"])
        nxt = mine[0] if mine else None
        win = [r for r in rows if t0 < to_date(r["date"]) <= t0 + timedelta(days=30)]
        o.append('<tr><td><span class="dt">%s</span>%s</td><td>%s</td><td><b>%d</b> releases, <b>%d</b> notable</td></tr>' % (
            dayl(st["d"]), esc(st["short"]),
            ('<a href="m/%s/">%s</a> <span class="delta">+%dd</span>' % (nxt["page"], esc(nxt["release"]), (to_date(nxt["date"]) - t0).days))
            if nxt else "nothing yet", len(win), sum(1 for r in win if r.get("notable"))))
    o.append('</tbody></table><p class="foot">Edit build/statements.json to add a statement; the rest is counted automatically.</p></div>')
    return "".join(o)


def dayl(iso):
    d = to_date(iso)
    return "%d %s %d" % (d.day, d.strftime("%b"), d.year)


def stream_cards():
    MAXG = 92
    o = ['<div class="streams">']
    for L in LABS:
        rel = [r for r in page_rows if r["lab"] == L["id"]]
        if not rel: continue
        gaps = [r for r in rel if r.get("gap")]
        gv = sorted(g["gap"] for g in gaps); med = gv[len(gv)//2] if gv else 0
        o.append('<div class="labcard" style="--c:%s">' % lab_var(L["id"]))
        o.append('<div class="labcard-top">%s<span><span class="nm">%s</span><br><span class="mod">%s</span></span></div>' % (mark_html(L["id"]), esc(L["name"]), esc(L["product"])))
        o.append('<div class="labcard-vals">'
                 '<div><span class="kk">Median gap</span><span class="vv" style="color:%s">%s<small> days</small></span></div>'
                 '<div><span class="kk">Releases</span><span class="vv">%d</span></div>'
                 '<div><span class="kk">Window</span><span class="vv small">%s \u2192 %s</span></div></div>'
                 % (lab_var(L["id"]), med or "\u2014", len(rel), rel[0]["d"][5:], rel[-1]["d"][5:]))
        if gaps:
            o.append('<div class="cad"><div class="cad-h"><span>since</span><span>gap between releases \u00b7 100%% = %dd</span></div>' % MAXG)
            for g in gaps:
                o.append('<div class="cad-row"><span>%s</span><span class="cad-bar"><span class="cad-fill %s" style="width:%.1f%%;background:%s"></span></span><span class="vv">%dd</span></div>'
                         % (g["d"][5:], "acc" if med and g["gap"] <= med else "", min(g["gap"], MAXG)/MAXG*100, lab_var(L["id"]), g["gap"]))
            o.append('</div>')
        o.append('<ul class="rel">')
        for r in rel:
            sc = ('<span class="sc" style="color:%s">%s</span>' % (lab_var(L["id"]), r["ii"])) if r["ii"] else '<span class="sc dim">no score</span>'
            gap = ('<span class="delta %s">+%dd</span>' % ("acc" if med and r["gap"] and r["gap"] <= med else "", r["gap"])) if r.get("gap") else ""
            o.append('<li><span class="dt">%s</span><span><span class="rn">%s %s %s</span>%s</li>'
                     % (r["d"], esc(r["m"]), gap, sc, ('<span class="cap">%s</span>' % esc(r["note"])) if r["note"] else ""))
        o.append('</ul></div>')
    o.append('</div>')
    return "".join(o)

def evidence_cards():
    o = ['<div class="evgrid">', said_then_shipped()]
    for e in SEC.EVIDENCE:
        o.append('<div class="card" style="--c:%s"><h4>%s</h4>' % (lab_var(e["colour"]), esc(e["title"])))
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

ACCEL_IDX = None


def accel_payload():
    """The header gauge, computed here so the number is reproducible and logged."""
    recs, as_of = ACCEL.load_records(R / "data" / "releases.json")
    idx = ACCEL.build_index(recs, as_of)
    print(f"acceleration index {idx['value']} ({idx['level']}) as of {idx['as_of']}"
          f" · week {idx['week']} · month {idx['month']}")
    return idx


def main():
    global ACCEL_IDX
    ACCEL_IDX = accel_payload()
    tpl = (R / "build" / "page_template.html").read_text()
    payload = {"labs": [dict(L) for L in LABS], "logos": LOGOS,
               "rows": page_rows,
               "stream": stream_rows,
               "accel": ACCEL_IDX,
               "statements": STATEMENTS,
               "sections": sections_html(),
               "meta": {"compiled": DATA.get("generated_utc", "")[:10],
                        "generated": DATA.get("generated_utc", ""),
                        "index_version": "Artificial Analysis Intelligence Index v4.3.2",
                        "source": "artificialanalysis.ai"}}
    out = tpl.replace("/*__LABVARS__*/", lab_css()).replace("__PAYLOAD__", json.dumps(payload))
    if "__PAYLOAD__" in out or "__LABVARS__" in out:
        sys.exit("template placeholder not replaced")
    # publish ONLY the site: the pipeline, data and docs must not go live
    site = R / "site"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(out)
    extras.write_all(site, rows, LABS, mark_html, NOTES, ACCEL_IDX, (DATA.get("generated_utc") or "")[:10])
    print(f"index.html written: {len(out)} bytes, {len(page_rows)} curated rows, "
          f"{len(stream_rows)} stream rows")

if __name__ == "__main__":
    main()
