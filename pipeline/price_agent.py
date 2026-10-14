#!/usr/bin/env python3
"""
Monthly price re-check for build/hardware.json, run by .github/workflows/prices.yml.

For every hand-checked price it:
  1. searches the web            (MiniMax Token Plan search, or a SearXNG instance)
  2. fetches the candidate pages itself (skipping sites whose terms forbid scraping)
  3. asks a language model to read them and return the current price AND the exact
     sentence on the page that states it
  4. verifies in code: the quote must appear on the fetched page and contain the price;
     implausible jumps are held back for a human
  5. writes the verified changes into hardware.json and a markdown report for the PR

Nothing here publishes anything: the workflow opens a pull request, and a person merges.
Standard library only.

Configuration (environment):
  LLM_BASE_URL     OpenAI-compatible endpoint   default https://api.minimax.io/v1
  LLM_API_KEY      key for it                   default $MINIMAX_API_KEY
  LLM_MODEL        model name                   default MiniMax-M3.1-Flash-Preview, the one
                   model MiniMax's subscription keys (Token Plan / M Plan) include
  SEARCH_BACKEND   minimax | searxng            default minimax
  MINIMAX_API_HOST search host                  default https://api.minimax.io
  SEARXNG_URL      e.g. http://127.0.0.1:8888   (searxng backend only)
  REPORT_PATH      where the PR body is written default price-report.md
  LLM_EXTRA_BODY   JSON merged into each request, for provider-specific switches, e.g.
                   '{"chat_template_kwargs": {"enable_thinking": false}}' for a local llama.cpp
  PRICE_AGENT_ONLY comma-separated name fragments: check only matching items (for testing)

Exit codes: 0 = ran (even if nothing changed), 1 = could not run (config, model or search down).
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "build" / "hardware.json"
UA = "artificialacceleration.com price check (+https://artificialacceleration.com)"

LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.minimax.io/v1").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("MINIMAX_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M3.1-Flash-Preview")
SEARCH = os.environ.get("SEARCH_BACKEND", "minimax")
MM_HOST = os.environ.get("MINIMAX_API_HOST", "https://api.minimax.io").rstrip("/")
SEARXNG = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888").rstrip("/")
REPORT = Path(os.environ.get("REPORT_PATH", ROOT / "price-report.md"))
EXTRA = json.loads(os.environ.get("LLM_EXTRA_BODY") or "{}")
ONLY = [x.strip().lower() for x in os.environ.get("PRICE_AGENT_ONLY", "").split(",") if x.strip()]

# Sites whose terms forbid automated access. We never fetch them, whatever search returns.
NO_FETCH = ("apple.com", "vast.ai", "runpod.io", "ebay.", "amazon.", "keepa.com", "camelcamelcamel.com",
            "pcpartpicker.com", "reddit.com", "x.com", "twitter.com", "facebook.com")
MAX_PAGES = 5               # pages read per item
EXCERPT = 7000              # characters of each page handed to the model
SANE_UP, SANE_DOWN = 1.3, 0.7   # a move beyond +30% / -30% in a month waits for a human


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------------------------------------------------ http

def http(url, data=None, headers=None, timeout=40):
    h = {"User-Agent": UA}
    h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(2_000_000)
        return raw.decode(r.headers.get_content_charset() or "utf-8", "ignore")


# ------------------------------------------------------------------ search

def search(query):
    """[(title, url, snippet)] for a query."""
    if SEARCH == "searxng":
        res = json.loads(http(f"{SEARXNG}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})))
        return [(r.get("title", ""), r.get("url", ""), r.get("content", "")) for r in res.get("results", [])[:8]]
    # MiniMax Token Plan search, as used by MiniMax's own MCP server (MiniMax-Coding-Plan-MCP)
    res = json.loads(http(f"{MM_HOST}/v1/coding_plan/search", {"q": query},
                          {"Authorization": f"Bearer {LLM_KEY}", "MM-API-Source": "artificialacceleration"}))
    status = (res.get("base_resp") or {}).get("status_code", 0)
    if status:
        raise RuntimeError(f"MiniMax search error {status}: {(res.get('base_resp') or {}).get('status_msg')}")
    return [(r.get("title", ""), r.get("link", ""), r.get("snippet", "")) for r in res.get("organic", [])[:8]]


# ------------------------------------------------------------------ pages

class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}

    def __init__(self):
        super().__init__()
        self.out, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "div", "li", "tr", "br", "h1", "h2", "h3", "td", "th"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, d):
        if not self.depth:
            self.out.append(d)


def page_text(url):
    p = _Text()
    p.feed(http(url, timeout=25))
    t = html.unescape("".join(p.out))
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def allowed(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    return url.startswith("http") and not any(b in host for b in NO_FETCH)


def excerpt(text, name):
    """The parts of a page that can hold a price for this item: lines with a $ amount,
    preferring those near the item's name. Keeps the model's input small and on topic."""
    words = [w for w in re.split(r"\W+", name.lower()) if len(w) > 2]
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    scored = []
    for i, ln in enumerate(lines):
        if not re.search(r"(\$|USD)\s?\d", ln):
            continue
        ctx = " ".join(lines[max(0, i - 2): i + 3]).lower()
        scored.append((sum(w in ctx for w in words), i))
    keep = sorted({j for s, i in sorted(scored, reverse=True)[:40] for j in range(max(0, i - 1), min(len(lines), i + 2))})
    return "\n".join(lines[j] for j in keep)[:EXCERPT]


# ------------------------------------------------------------------ model

def ask_model(prompt, budget=12000):
    body = {"model": LLM_MODEL, "temperature": 1.0, "max_completion_tokens": budget,
            "messages": [{"role": "system", "content":
                          "You extract prices from web pages for a public price tracker. You only report a number "
                          "that is written on one of the pages given to you, and you copy the sentence that states "
                          "it exactly. If no page states a current price, you say so. Reply with JSON only."},
                         {"role": "user", "content": prompt}]}
    if "minimax" in LLM_BASE:
        body["reasoning_split"] = True          # keep the model's thinking out of the answer
        if "M3.1" in LLM_MODEL:
            body["reasoning_effort"] = "low"    # reading a price off a page needs little thought; spares the quota
    body.update(EXTRA)
    out = json.loads(http(f"{LLM_BASE}/chat/completions", body, {"Authorization": f"Bearer {LLM_KEY}"}, timeout=300))
    choice = out["choices"][0]
    msg = choice["message"].get("content") or ""
    msg = re.sub(r"<think>.*?</think>", "", msg, flags=re.S).strip()
    # thinking models can spend the whole budget thinking and answer nothing: one retry, bigger
    if not msg and choice.get("finish_reason") == "length" and budget < 30000:
        return ask_model(prompt, budget=30000)
    m = re.search(r"\{.*\}", msg, re.S)
    if not m:
        raise ValueError(f"no JSON in model reply: {msg[:200]!r}")
    return json.loads(m.group(0))


def norm(s):
    s = html.unescape(s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def amounts(text):
    """Every dollar amount written in a piece of text, as numbers ($4,950 / $4.9k / $3.7M / 4,950 USD)."""
    out = []
    for m in re.finditer(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand)?|(\d[\d,]*(?:\.\d+)?)\s?(?:usd|dollars)", text, re.I):
        num = float((m.group(1) or m.group(3)).replace(",", ""))
        mult = (m.group(2) or "").lower()
        num *= 1000 if mult in ("k", "thousand") else 1e6 if mult in ("m", "million") else 1
        out.append(num)
    return out


def verify(ans, pages, keys):
    """The model's answer is accepted only if it can be checked against the page it cites."""
    src = ans.get("source")
    if src not in pages:
        return "the cited page was not one we fetched"
    quote = norm(ans.get("quote"))
    if len(quote) < 12 or quote not in norm(pages[src]):
        return "the quoted sentence is not on the cited page"
    found = amounts(quote)
    for k in keys:
        v = ans.get(k)
        if v is None:
            continue
        if not any(abs(f - float(v)) <= max(1.0, 0.005 * float(v)) for f in found):
            return f"the quote does not contain {k} = {v}"
    return None


# ------------------------------------------------------------------ items

def tasks(hw):
    """One task per hand-checked number group, with what the model must return."""
    month = date.today().strftime("%B %Y")
    for h in hw["home"]:
        used = "used" in h["kind"].lower()
        yield {"kind": "home", "item": h, "name": h["name"],
               "queries": [f'{h["name"]} {"used " if used else ""}price {month}', f'{h["name"]} price'],
               "want": ("price", "low", "high"),
               "ask": (f'the current {"USED street" if used else "lowest NEW retail"} price in US dollars of: {h["name"]} '
                       f'({h["mem_gb"]} GB). Today it is recorded as ${h["now"]["price"]:,} (range ${h["now"].get("low", h["now"]["price"]):,}'
                       f'-${h["now"].get("high", h["now"]["price"]):,}). Return {{"price": number or null, "low": number or null, '
                       f'"high": number or null, "basis": "short note e.g. used median / list price", "source": "URL", '
                       f'"quote": "exact sentence from that page", "confidence": "high|medium|low"}}. '
                       f'price must be the typical current price; low/high only if the page gives a range.')}
    for g in hw["datacenter"]:
        if g.get("buy_low") is None:
            continue
        yield {"kind": "datacenter", "item": g, "name": g["name"],
               "queries": [f'NVIDIA {g["name"]} GPU price per unit {month}', f'{g["name"]} GPU cost'],
               "want": ("buy_low", "buy_high"),
               "ask": (f'the current purchase price range in US dollars of ONE {g["name"]} datacenter GPU (not a server, not '
                       f'rental per hour). Recorded now: ${g["buy_low"]:,}-${g["buy_high"]:,}. Return {{"buy_low": number or null, '
                       f'"buy_high": number or null, "source": "URL", "quote": "exact sentence from that page", '
                       f'"confidence": "high|medium|low"}}.')}
    for r in hw.get("racks", []):
        yield {"kind": "rack", "item": r, "name": r["name"],
               "queries": [f'{r["name"]} rack price {month}', f'{r["name"]} cost per rack'],
               "want": ("low", "high"),
               "ask": (f'the current price range in US dollars of one {r["name"]} rack ({r["what"]}). Recorded now: '
                       f'${r["low"]:,}-${r["high"]:,}. Return {{"low": number or null, "high": number or null, "source": "URL", '
                       f'"quote": "exact sentence from that page", "confidence": "high|medium|low"}}.')}


def current(t):
    i = t["item"]
    if t["kind"] == "home":
        return {"price": i["now"]["price"], "low": i["now"].get("low"), "high": i["now"].get("high")}
    if t["kind"] == "datacenter":
        return {"buy_low": i["buy_low"], "buy_high": i["buy_high"]}
    return {"low": i["low"], "high": i["high"]}


def apply(t, ans):
    i = t["item"]
    if t["kind"] == "home":
        p = float(ans["price"])
        i["now"] = {"price": round(p), "low": round(float(ans.get("low") or p)), "high": round(float(ans.get("high") or p)),
                    "basis": (ans.get("basis") or i["now"].get("basis", ""))[:60]}
    elif t["kind"] == "datacenter":
        i["buy_low"], i["buy_high"] = round(float(ans["buy_low"])), round(float(ans.get("buy_high") or ans["buy_low"]))
    else:
        i["low"], i["high"] = round(float(ans["low"])), round(float(ans.get("high") or ans["low"]))
    i["src"] = ans["source"]


def check(t):
    """Run one task. Returns a report row."""
    cands, seen = [], set()
    if t["item"].get("src"):
        cands.append(t["item"]["src"])
    for q in t["queries"]:
        try:
            for _, url, _ in search(q):
                if url and url not in seen:
                    seen.add(url)
                    cands.append(url)
        except Exception as e:
            log(f"  search failed for {q!r}: {e}")
    pages, blocks = {}, []
    for url in cands:
        if len(pages) >= MAX_PAGES:
            break
        if not allowed(url) or url in pages:
            continue
        try:
            text = page_text(url)
        except Exception as e:
            log(f"  skip {url[:70]}: {type(e).__name__}")
            continue
        ex = excerpt(text, t["name"])
        if not ex:
            continue
        pages[url] = text
        blocks.append(f"### PAGE {len(blocks) + 1}\nURL: {url}\n{ex}")
    row = {"name": t["name"], "old": current(t), "status": "no data", "new": None, "source": None, "quote": None, "why": ""}
    if not blocks:
        row["why"] = "no readable pages with prices"
        return row
    prompt = (f"Find {t['ask']}\nToday is {date.today():%d %B %Y}. Use only these pages; prefer the most recent "
              f"and most specific one. If none states a current price, return nulls.\n\n" + "\n\n".join(blocks))
    try:
        ans = ask_model(prompt)
    except Exception as e:
        row["why"] = f"model error: {e}"[:160]
        return row
    key = t["want"][0]
    if ans.get(key) in (None, "", 0):
        row["why"] = "no current price found on the pages read"
        return row
    # the headline number must be proven; a range bound the quote does not contain is
    # dropped rather than sinking an otherwise verified price
    bad = verify(ans, pages, [key])
    if not bad:
        for k in t["want"][1:]:
            if ans.get(k) is not None and verify(ans, pages, [k]):
                ans[k] = None
    row.update(new={k: ans.get(k) for k in t["want"]}, source=ans.get("source"), quote=ans.get("quote"))
    if bad:
        row.update(status="rejected", why=bad)
        return row
    old_v, new_v = float(row["old"][key]), float(ans[key])
    ratio = new_v / old_v if old_v else 1
    if ratio > SANE_UP or ratio < SANE_DOWN:
        row.update(status="held", why=f"{(ratio - 1) * 100:+.0f}% in a month; left unchanged for a human to confirm")
        return row
    before = current(t)
    apply(t, ans)
    after = current(t)
    moved = any(before.get(k) is not None and after.get(k) is not None
                and abs(float(after[k]) - float(before[k])) > 0.005 * float(before[k]) for k in t["want"])
    row["status"] = "updated" if moved else "confirmed"
    return row


# ------------------------------------------------------------------ report

def money(v):
    return "—" if v is None else (f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v:,.0f}")


def report(rows, checked):
    icon = {"updated": "🟢 updated", "confirmed": "⚪ confirmed", "held": "🟠 held", "rejected": "🔴 rejected", "no data": "⚫ no data"}
    out = [f"## Monthly price check · {checked}\n",
           f"Model `{LLM_MODEL}` via `{urllib.parse.urlparse(LLM_BASE).netloc}`, search `{SEARCH}`. Every accepted price was "
           "checked in code: the quoted sentence is on the cited page and contains the number. Moves over "
           f"+{(SANE_UP - 1) * 100:.0f}% / -{(1 - SANE_DOWN) * 100:.0f}% are held for you.\n",
           "| Item | Was | Now | Status | Evidence |", "|---|---|---|---|---|"]
    for r in rows:
        k = list(r["old"])[0]
        was = money(r["old"][k]) + ((f" ({money(r['old'].get('low') or r['old'].get('buy_low'))}–"
                                     f"{money(r['old'].get('high') or r['old'].get('buy_high'))})") if len(r["old"]) > 1 else "")
        now = money(float(r["new"][k])) if r["new"] and r["new"].get(k) else "—"
        ev = (f'[source]({r["source"]}): “{(r["quote"] or "")[:160]}”' if r["source"] else "") + (f" — {r['why']}" if r["why"] else "")
        out.append(f"| {r['name']} | {was} | {now} | {icon[r['status']]} | {ev.replace('|', '/')} |")
    out.append("\nMerge to publish. Edit `build/hardware.json` in this branch first if anything looks wrong.")
    return "\n".join(out) + "\n"


def main():
    if not LLM_KEY:
        log("no LLM_API_KEY / MINIMAX_API_KEY set")
        return 1
    hw = json.loads(HW.read_text())
    try:                                            # fail fast, and loudly, if the model is unreachable
        ask_model('Reply with {"ok": true}')
    except Exception as e:
        log(f"model unreachable at {LLM_BASE} ({LLM_MODEL}): {e}")
        return 1
    rows = []
    for t in tasks(hw):
        if ONLY and not any(o in t["name"].lower() for o in ONLY):
            continue
        log(f"{t['kind']}: {t['name']}")
        rows.append(check(t))
        log(f"  -> {rows[-1]['status']} {rows[-1]['why']}")
        time.sleep(1)
    good = [r for r in rows if r["status"] in ("updated", "confirmed")]
    if not good and all(r["status"] == "no data" for r in rows):
        log("nothing could be checked; leaving hardware.json alone")
        REPORT.write_text(report(rows, date.today().isoformat()))
        return 1
    if good:
        hw["checked"] = date.today().isoformat()     # the date means "a human-reviewable check happened"
    HW.write_text(json.dumps(hw, indent=1, ensure_ascii=False) + "\n")
    REPORT.write_text(report(rows, date.today().isoformat()))
    log(f"done: {sum(r['status'] == 'updated' for r in rows)} updated, {sum(r['status'] == 'confirmed' for r in rows)} confirmed, "
        f"{sum(r['status'] in ('held', 'rejected') for r in rows)} for review, {sum(r['status'] == 'no data' for r in rows)} without data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
