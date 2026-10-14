#!/usr/bin/env python3
"""
Everything published next to index.html, generated from the same dataset:

  site/m/<slug>/index.html   one permalink page per release (shareable, citable)
  site/feed.xml              Atom feed of notable releases
  site/sitemap.xml, robots.txt
  site/badge.svg             the Acceleration Index as a small embeddable badge
  site/embed/index.html      the same as an iframe widget
  site/og.png                the social preview card (rendered with headless Chrome
                             when one is installed; skipped quietly otherwise)

Called from build_page.py; nothing here reads the network.
"""
import html, json, re, shutil, subprocess, tempfile
from datetime import date, datetime, timezone
from pathlib import Path

BASE = "https://artificialacceleration.com"
TITLE = "Artificial Acceleration"


def esc(t):
    return html.escape(str(t), quote=True)


def day_label(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def price_label(v):
    if v is None:
        return "not priced"
    return f"${v:,.2f}" if v < 100 else f"${v:,.0f}"


def assign_slugs(rows):
    """The API slug, made unique: a few names were re-released under the same slug."""
    seen = {}
    for r in sorted(rows, key=lambda r: (r["date"], r["lab"], r["release"])):
        base = re.sub(r"[^a-z0-9-]+", "-", (r.get("slug") or r["release"]).lower()).strip("-") or "model"
        slug = base if base not in seen else f"{base}-{r['date']}"
        seen[slug] = True
        r["page"] = slug
    return rows


# ---------------------------------------------------------------- model pages

PAGE_CSS = """
:root{--bg:#0a0b12;--panel:#141725;--line:#2c3145;--line2:#222738;--ink:#f2f5fc;--dim:#b3bcd2;--faint:#7f89a3;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono","DejaVu Sans Mono",Menlo,Consolas,monospace;
  --sans:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
[data-theme="light"]{--bg:#f4f6fb;--panel:#fff;--line:#d3dae8;--line2:#e4e9f3;--ink:#131824;--dim:#46516b;--faint:#6b7793}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:22px 16px 40px}
a{color:inherit}
.crumb{font:12px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--faint);text-decoration:none}
.crumb:hover{color:var(--ink)}
.lab{display:flex;align-items:center;gap:10px;margin-top:22px;color:var(--dim);font-weight:600}
.lab .logo{width:24px;height:24px;display:inline-flex}.lab .logo svg,.lab .logo img{width:24px;height:24px}
.logo.backed{background:#fff;border-radius:5px;padding:2px}.logo.mono{color:var(--ink)}
h1{font-size:clamp(30px,6vw,46px);line-height:1.08;margin:6px 0 4px;letter-spacing:-.025em;text-wrap:balance}
.when{color:var(--dim);font-size:15px}
.when a{color:var(--ink)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:22px 0}
.stat{background:var(--panel);border:1px solid var(--line2);border-radius:10px;padding:12px 14px}
.stat .k{font:10.5px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--faint)}
.stat .v{font-size:24px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;margin-top:2px}
.stat .s{font-size:12.5px;color:var(--dim)}
.badge{display:inline-block;font:11px var(--mono);border:1px solid var(--c);color:var(--ink);border-radius:999px;padding:2px 9px;margin-right:6px}
.note{font-size:17px;border-left:3px solid var(--c);padding:4px 0 4px 14px;margin:18px 0;color:var(--ink)}
.panel{background:var(--panel);border:1px solid var(--line2);border-radius:12px;padding:14px 16px;margin-top:14px}
.panel h2{font-size:14px;margin:0 0 6px;color:var(--dim);font-weight:600}
.nav{display:flex;justify-content:space-between;gap:12px;margin-top:18px;font-size:14px}
.nav a{display:block;background:var(--panel);border:1px solid var(--line2);border-radius:10px;padding:10px 14px;text-decoration:none;flex:1}
.nav a:hover{border-color:var(--c)}
.nav .k{display:block;font:10.5px var(--mono);color:var(--faint);letter-spacing:.1em;text-transform:uppercase}
.nav .next{text-align:right}
footer{margin-top:28px;font-size:12.5px;color:var(--faint)}
svg text{font-family:var(--mono)}
"""

THEME_JS = """<script>try{var t=localStorage.getItem("aa-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}</script>"""


def lab_steps(rows_lab):
    """The lab's running best, as (date, score, row) steps, for the page's small chart."""
    best, out = None, []
    for r in sorted(rows_lab, key=lambda r: r["date"]):
        if r.get("ii") is None:
            continue
        if best is None or r["ii"] > best:
            best = r["ii"]
            out.append((r["date"], best, r))
    return out


def page_spark(rows_lab, me, hexc):
    """A small staircase of the lab's best score, with this release marked."""
    scored = sorted([r for r in rows_lab if r.get("ii") is not None], key=lambda r: r["date"])
    if len(scored) < 2:
        return ""
    W, H, P = 820, 150, 26
    t0, t1 = date.fromisoformat(scored[0]["date"]), date.fromisoformat(scored[-1]["date"])
    span = max(1, (t1 - t0).days)
    vmax = max(r["ii"] for r in scored) + 3
    x = lambda iso: P + (date.fromisoformat(iso) - t0).days / span * (W - 2 * P)
    y = lambda v: H - 18 - v / vmax * (H - 34)
    steps = lab_steps(rows_lab)
    d = ""
    for i, (iso, v, _) in enumerate(steps):
        d += (f"M{x(iso):.1f} {y(v):.1f}" if not i else f" H{x(iso):.1f} V{y(v):.1f}")
    d += f" H{x(scored[-1]['date']):.1f}"
    dots = "".join(
        f'<circle cx="{x(r["date"]):.1f}" cy="{y(r["ii"]):.1f}" r="2.6" fill="{hexc}" opacity=".45"/>' for r in scored)
    mark = ""
    if me.get("ii") is not None:
        mx, my = x(me["date"]), y(me["ii"])
        mark = (f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="7" fill="none" stroke="var(--ink)" stroke-width="1.6"/>'
                f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="3.6" fill="{hexc}"/>')
    axis = (f'<text x="{P}" y="{H - 2}" fill="var(--faint)" font-size="11">{day_label(scored[0]["date"])}</text>'
            f'<text x="{W - P}" y="{H - 2}" fill="var(--faint)" font-size="11" text-anchor="end">{day_label(scored[-1]["date"])}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="This lab\'s best intelligence score over time, with this release marked">'
            f'<path d="{d}" fill="none" stroke="{hexc}" stroke-width="2"/>{dots}{mark}{axis}</svg>')


def model_page(r, ctx):
    L = ctx["labmap"][r["lab"]]
    hexc = L["hex"]
    lab_rows = sorted([x for x in ctx["rows"] if x["lab"] == r["lab"]], key=lambda x: (x["date"], x["release"]))
    i = lab_rows.index(r)
    prev_r = lab_rows[i - 1] if i else None
    next_r = lab_rows[i + 1] if i + 1 < len(lab_rows) else None

    # standing on the day it shipped, against every tracked release up to then
    before = [x for x in ctx["rows"] if x["date"] <= r["date"] and x.get("ii") is not None and x is not r]
    rank_txt, record = "", ""
    if r.get("ii") is not None:
        above = sum(1 for x in before if x["ii"] > r["ii"])
        rank_txt = f"#{above + 1} of {len(before) + 1} scored releases to that date"
        if not any(x["ii"] >= r["ii"] for x in before):
            record = "a new all-time high across the nine labs"
        elif not any(x["ii"] >= r["ii"] for x in before if x["lab"] == r["lab"]):
            record = f"a new best for {L['name']}"

    gap = (f'{r["gap"]} days after <a href="../{prev_r["page"]}/">{esc(prev_r["release"])}</a>'
           if prev_r and r.get("gap") is not None else "the first release in our record for this lab")
    note = ctx["notes"].get(re.sub(r"[^a-z0-9]", "", r["release"].lower()), "")
    title = f'{r["release"]} — {L["name"]}, released {day_label(r["date"])}'
    desc = (f'{r["release"]} by {L["name"]}, released {day_label(r["date"])}'
            + (f', Intelligence Index {r["ii"]}' if r.get("ii") is not None else "")
            + (f', {r["gap"]} days after the lab\'s previous release' if r.get("gap") is not None else "")
            + ". Tracked by Artificial Acceleration.")
    url = f'{BASE}/m/{r["page"]}/'

    stats = [
        ("Intelligence", f'{r["ii"]}' if r.get("ii") is not None else "—",
         rank_txt or "no index score yet"),
        ("Price", price_label(r.get("price")),
         f'per 1M tokens, 3:1 in/out · ${r.get("price_in") or 0:g} in / ${r.get("price_out") or 0:g} out'
         if r.get("price") is not None else "no list price"),
        ("Speed", f'{r["tps"]:.0f}' if r.get("tps") else "—", "output tokens/s, median" if r.get("tps") else "not measured"),
        ("Weights", "Open" if r.get("open") else "Closed", f'{"US" if r.get("region") == "US" else "China"} lab'),
    ]
    stat_html = "".join(f'<div class="stat"><div class="k">{k}</div><div class="v">{esc(v)}</div><div class="s">{s}</div></div>'
                        for k, v, s in stats)
    badges = ""
    if record:
        badges += f'<span class="badge">{esc(record)}</span>'
    if r.get("notable"):
        badges += '<span class="badge">notable release</span>'
    nav = '<div class="nav">'
    nav += (f'<a href="../{prev_r["page"]}/"><span class="k">&larr; previous from {esc(L["short"])}</span>{esc(prev_r["release"])}</a>'
            if prev_r else "<span></span>")
    nav += (f'<a class="next" href="../{next_r["page"]}/"><span class="k">next from {esc(L["short"])} &rarr;</span>{esc(next_r["release"])}</a>'
            if next_r else "<span></span>")
    nav += "</div>"
    ld = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": r["release"],
          "applicationCategory": "AI model", "datePublished": r["date"],
          "creator": {"@type": "Organization", "name": L["name"]}, "url": url}
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2310a37f'/%3E%3Cpath d='M16 6l7 20h-4l-1.4-4.4h-5.2L11 26H7L14 6h2zm.9 6.6l-1.8 5.6h3.6l-1.8-5.6z' fill='%23fff'/%3E%3C/svg%3E">
<title>{esc(title)} · {TITLE}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="{TITLE}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{BASE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/atom+xml" title="{TITLE}: notable releases" href="{BASE}/feed.xml">
<script type="application/ld+json">{json.dumps(ld)}</script>
{THEME_JS}<style>{PAGE_CSS}</style></head>
<body style="--c:{hexc}"><div class="wrap">
<a class="crumb" href="../../">&larr; {TITLE}</a>
<div class="lab">{ctx["mark_html"](r["lab"])}{esc(L["name"])} · {esc(L["product"])}</div>
<h1>{esc(r["release"])}</h1>
<div class="when">Released <b>{day_label(r["date"])}</b> · {gap}</div>
<div style="margin-top:10px">{badges}</div>
{f'<p class="note">{esc(note)}</p>' if note else ""}
<div class="stats">{stat_html}</div>
<div class="panel"><h2>{esc(L["name"])}&rsquo;s best score over time</h2>{page_spark(lab_rows, r, hexc)}</div>
{nav}
<footer>Benchmark data: <a href="https://artificialanalysis.ai">Artificial Analysis</a> · Intelligence Index at max effort.
Open-weight status is our classification. Data as of {day_label(ctx["as_of"])}.
<a href="../../">See every release on the timeline &rarr;</a></footer>
</div></body></html>"""


# ---------------------------------------------------------------- feed + sitemap

def atom(ctx):
    notable = sorted([r for r in ctx["rows"] if r.get("notable")], key=lambda r: r["date"], reverse=True)[:60]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = []
    for r in notable:
        L = ctx["labmap"][r["lab"]]
        bits = [f"Released {day_label(r['date'])} by {L['name']}."]
        if r.get("ii") is not None:
            bits.append(f"Artificial Analysis Intelligence Index: {r['ii']}.")
        if r.get("gap") is not None:
            bits.append(f"{r['gap']} days after {L['short']}'s previous release.")
        if r.get("price") is not None:
            bits.append(f"{price_label(r['price'])} per 1M tokens (3:1 blend).")
        url = f"{BASE}/m/{r['page']}/"
        entries.append(f"""  <entry>
    <title>{esc(L['short'])}: {esc(r['release'])}</title>
    <link href="{url}"/>
    <id>tag:artificialacceleration.com,2026:m/{esc(r['page'])}</id>
    <updated>{r['date']}T00:00:00Z</updated>
    <author><name>{esc(L['name'])}</name></author>
    <summary>{esc(' '.join(bits))}</summary>
  </entry>""")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{TITLE}: notable frontier releases</title>
  <subtitle>Every notable release from nine frontier labs, dated, with its intelligence score.</subtitle>
  <link href="{BASE}/"/><link rel="self" href="{BASE}/feed.xml"/>
  <id>{BASE}/</id>
  <updated>{now}</updated>
{chr(10).join(entries)}
</feed>
"""


def sitemap(ctx):
    urls = [f"{BASE}/", f"{BASE}/hardware/"] + [f"{BASE}/m/{r['page']}/" for r in ctx["rows"]]
    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


# ---------------------------------------------------------------- badge + embed

def badge_svg(accel):
    v, lvl, col = accel["value"], accel["level"], accel["colour"]
    left, right = "Acceleration Index", f"{v} {lvl}"
    lw, rw = 128, 18 + 7.2 * len(right)
    w = lw + rw
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="22" role="img" aria-label="{left}: {right}">
<title>{left}: {right} (artificialacceleration.com)</title>
<rect width="{w:.0f}" height="22" rx="4" fill="#141725"/>
<rect x="{lw}" width="{rw:.0f}" height="22" rx="4" fill="{col}"/><rect x="{lw}" width="6" height="22" fill="{col}"/>
<g font-family="Verdana,DejaVu Sans,sans-serif" font-size="11.5" fill="#fff">
<text x="9" y="15">{left}</text><text x="{lw + 9}" y="15" font-weight="bold">{right}</text></g></svg>
"""


def embed_page(accel):
    v, lvl, col = accel["value"], accel["level"], accel["colour"]
    wk, mo = accel["week"], accel["month"]
    arrow = lambda a, b: ("&#9650;" if a > b else "&#9660;" if a < b else "=")
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acceleration Index · {TITLE}</title><meta name="robots" content="noindex">
<style>
body{{margin:0;font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;background:transparent}}
a{{display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:12px;background:#141725;color:#f2f5fc;text-decoration:none;border:1px solid #2c3145;max-width:340px}}
.v{{font-size:34px;font-weight:800;color:{col};font-variant-numeric:tabular-nums;line-height:1}}
.l{{font-weight:700;color:{col};text-transform:uppercase;letter-spacing:.08em;font-size:12px}}
.k{{color:#b3bcd2;font-size:12px}}
</style></head><body>
<a href="{BASE}/" target="_blank" rel="noopener">
 <span class="v">{v}</span>
 <span><span class="l">{lvl}</span><br><b>Acceleration Index</b><br>
 <span class="k">{arrow(v, wk)} {wk} a week ago &middot; {arrow(v, mo)} {mo} a month ago</span><br>
 <span class="k">artificialacceleration.com</span></span>
</a></body></html>
"""


# ---------------------------------------------------------------- social card

def card_html(ctx):
    accel, rows = ctx["accel"], ctx["rows"]
    latest = sorted([r for r in rows if r.get("notable")], key=lambda r: r["date"])[-3:][::-1]
    top = max((r for r in rows if r.get("ii") is not None), key=lambda r: r["ii"])
    li = "".join(f'<li><i style="background:{ctx["labmap"][r["lab"]]["hex"]}"></i><b>{esc(r["release"])}</b>'
                 f'<span>{day_label(r["date"])}</span></li>' for r in latest)
    col = accel["colour"]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
body{{background:radial-gradient(900px 500px at 0% 0%,rgba(16,163,127,.18),transparent 70%),radial-gradient(800px 500px at 100% 100%,rgba(217,119,87,.16),transparent 70%),#0a0b12;
  color:#f2f5fc;font-family:Inter,"DejaVu Sans",Roboto,Arial,sans-serif;padding:56px 64px;box-sizing:border-box}}
.eb{{font:600 18px "DejaVu Sans Mono",monospace;letter-spacing:.18em;color:#7f89a3;text-transform:uppercase}}
h1{{font-size:76px;line-height:1;margin:18px 0 10px;letter-spacing:-.03em}}
.sub{{font-size:30px;color:#b3bcd2}}
.row{{display:flex;justify-content:space-between;align-items:flex-end;margin-top:52px}}
.g .v{{font-size:132px;font-weight:800;color:{col};line-height:.9}}
.g .l{{font:700 24px "DejaVu Sans Mono",monospace;color:{col};letter-spacing:.14em}}
.g .k{{font-size:20px;color:#7f89a3;margin-top:6px}}
ul{{list-style:none;margin:0;padding:0;width:560px}}
li{{display:flex;align-items:center;gap:14px;font-size:26px;padding:10px 0;border-top:1px solid #2c3145}}
li i{{width:14px;height:14px;border-radius:50%;flex:0 0 auto}}
li b{{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
li span{{color:#7f89a3;font-size:20px}}
.cap{{font:600 15px "DejaVu Sans Mono",monospace;color:#7f89a3;letter-spacing:.12em;text-transform:uppercase;margin-bottom:4px}}
</style></head><body>
<div class="eb">artificialacceleration.com · data as of {day_label(ctx["as_of"])}</div>
<h1>Artificial Acceleration</h1>
<div class="sub">Nine frontier labs. Every release, dated. Frontier score {top["ii"]} ({esc(top["release"])}).</div>
<div class="row">
 <div class="g"><div class="v">{accel["value"]}</div><div class="l">{accel["level"].upper()}</div><div class="k">Acceleration Index · trailing 30 days</div></div>
 <div><div class="cap">Latest notable releases</div><ul>{li}</ul></div>
</div></body></html>"""


def render_card(ctx, site):
    """og.png via headless Chrome. Optional: the page works without it."""
    exe = next((shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
                if shutil.which(n)), None)
    if not exe:
        print("og card: no Chrome on PATH, skipped")
        return
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "card.html"
        src.write_text(card_html(ctx))
        out = site / "og.png"
        try:
            subprocess.run([exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=1200,630", f"--screenshot={out}", src.as_uri()],
                           check=True, capture_output=True, timeout=90)
            print(f"og card: {out.stat().st_size} bytes")
        except (subprocess.SubprocessError, OSError) as e:
            print(f"og card: render failed ({type(e).__name__}), skipped")


# ---------------------------------------------------------------- entry point

def write_all(site, rows, labs, mark_html, notes, accel, as_of):
    ctx = {"rows": rows, "labmap": {L["id"]: L for L in labs}, "mark_html": mark_html,
           "notes": notes, "accel": accel, "as_of": as_of}
    mdir = site / "m"
    if mdir.exists():
        shutil.rmtree(mdir)            # a renamed slug must not leave a stale page behind
    for r in rows:
        d = mdir / r["page"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(model_page(r, ctx))
    (site / "feed.xml").write_text(atom(ctx))
    (site / "sitemap.xml").write_text(sitemap(ctx))
    (site / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    (site / "badge.svg").write_text(badge_svg(accel))
    (site / "embed").mkdir(exist_ok=True)
    (site / "embed" / "index.html").write_text(embed_page(accel))
    render_card(ctx, site)
    print(f"extras: {len(rows)} release pages, feed, sitemap, badge, embed")
