#!/usr/bin/env python3
"""
Monthly price re-check for build/hardware.json (v2), run by scripts/price_check_local.sh.

For every product in every market (US, Euro area, UK, China, Japan), and every datacenter
part with a purchase estimate, it:
  1. goes first to the price-monitoring pages registered for that product and market in
     build/price_sources.json (gpuprix per country, kakaku for Japan, ZOL / nvidia.cn for
     China, official stores, amcompute for datacenter parts); only if none of them yields a
     verified price does it search, restricted to that market's monitor sites, and it
     registers any new page that works, so next month goes straight there
  2. fetches pages itself, honouring each site's robots.txt (sites that forbid automated
     access are never fetched, whatever a search returns)
  3. asks a language model to read them and return the current price AND the exact
     sentence on the page that states it
  4. verifies in code: the quote must appear on the fetched page and contain the price;
     implausible jumps are held back for a human
  5. APPENDS each verified price as a new dated point (nothing is overwritten, so the
     history grows month by month) and writes a markdown report for the PR

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
import math, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, urllib.robotparser
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "build" / "hardware.json"
SOURCES = ROOT / "build" / "price_sources.json"
UA = "artificialacceleration.com price check (+https://artificialacceleration.com)"

LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.minimax.io/v1").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("MINIMAX_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M3.1-Flash-Preview")
SEARCH = os.environ.get("SEARCH_BACKEND", "minimax")
MM_HOST = os.environ.get("MINIMAX_API_HOST", "https://api.minimax.io").rstrip("/")
SEARXNG = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888").rstrip("/")
REPORT = Path(os.environ.get("REPORT_PATH", ROOT / "price-report.md"))
EXTRA = json.loads(os.environ.get("LLM_EXTRA_BODY") or "{}")
ONLY = [x.strip().lower() for x in re.split(r"[|]" if "|" in os.environ.get("PRICE_AGENT_ONLY", "") else ",", os.environ.get("PRICE_AGENT_ONLY", "")) if x.strip()]

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
        cs = r.headers.get_content_charset()
    if not cs:
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:4000])
        cs = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        return raw.decode(cs, "ignore")
    except LookupError:
        return raw.decode("utf-8", "ignore")


# ------------------------------------------------------------------ search

def searxng(query):
    res = json.loads(http(f"{SEARXNG}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})))
    return [(r.get("title", ""), r.get("url", ""), r.get("content", "")) for r in res.get("results", [])[:8]]


def search(query):
    """[(title, url, snippet)] for a query."""
    if SEARCH == "searxng":
        return searxng(query)
    # MiniMax Token Plan search, as used by MiniMax's own MCP server (MiniMax-Coding-Plan-MCP)
    res = json.loads(http(f"{MM_HOST}/v1/coding_plan/search", {"q": query},
                          {"Authorization": f"Bearer {LLM_KEY}", "MM-API-Source": "artificialacceleration"}))
    status = (res.get("base_resp") or {}).get("status_code", 0)
    if status:
        # MiniMax's search refuses many shopping queries ("1027 output new_sensitive"): ask the
        # local SearXNG instead when one is running, and only fail if both are unavailable
        try:
            return searxng(query)
        except Exception:
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


_ROBOTS = {}


def robots_ok(url):
    """Honour the site's robots.txt for our user agent. Unreadable robots.txt = allowed."""
    u = urllib.parse.urlparse(url)
    host = f"{u.scheme}://{u.netloc}"
    if host not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        try:                                     # RobotFileParser.read() has no timeout; fetch it ourselves
            req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                rp.parse(r.read(500_000).decode("utf-8", "ignore").splitlines())
        except urllib.error.HTTPError as e:
            rp = None if e.code in (404, 410) else rp
            if rp is not None:
                rp.disallow_all = e.code in (401, 403)
        except Exception:
            rp = None
        _ROBOTS[host] = rp
    rp = _ROBOTS[host]
    return rp is None or rp.can_fetch(UA, url)


def blocked(host):
    """Whole-domain match: 'x.com' must block x.com and its subdomains, not gpuprix.com.
    Entries ending in '.' ('ebay.', 'amazon.') match that name under any country domain."""
    host = host.split(":")[0].lower()
    for b in NO_FETCH:
        if b.endswith("."):
            if host.startswith(b) or ("." + b) in host:
                return True
        elif host == b or host.endswith("." + b):
            return True
    return False


def allowed(url):
    host = urllib.parse.urlparse(url).netloc
    return url.startswith("http") and not blocked(host) and robots_ok(url)


def excerpt(text, name):
    """The parts of a page that can hold a price for this item: lines with a $ amount,
    preferring those near the item's name. Keeps the model's input small and on topic."""
    words = [w for w in re.split(r"[^\w+]+", name.lower()) if len(w) > 2 or (len(w) > 1 and any(c.isdigit() for c in w))]
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    scored = []
    for i, ln in enumerate(lines):
        if not re.search(r"(\$|€|£|¥|￥|USD|EUR|GBP|CNY|RMB|JPY)\s?\d|\d\s?(€|元|円|万|EUR|GBP|USD)", ln):
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


def numbers(text):
    """Every number written in a piece of text, read every way it could be meant:
    $4,950 / 4.950 € (German) / £1,299.99 / ¥16,499 / 1.65万 / 398,800円 / $3.7M / $27K."""
    out = set()
    pat = r"(\d{1,3}(?:[.,\s  ']\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)\s*(万|k|K|m|M|million|thousand|bn|billion)?"
    for m in re.finditer(pat, text):
        raw, mult = m.group(1), (m.group(2) or "").lower()
        f = {"万": 1e4, "k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}.get(mult, 1)
        compact = re.sub(r"[\s  ']", "", raw)
        for cand in (compact.replace(",", ""),                              # 4,950.00
                     compact.replace(".", "").replace(",", ".")):           # 4.950,00
            try:
                out.add(float(cand) * f)
            except ValueError:
                pass
    return out


# A price only counts when the item can be bought at it now. Advertised lows for boards that are
# out of stock are lures (Oct 2026: RTX 5090 "from $2,869" in the US, nothing under $7,200 in
# stock). The model must quote the page's own words showing availability; the code checks them.
IN_STOCK = re.compile(r"in stock|add to (cart|basket)|buy now|available to order|ships (in|within|today)|in den warenkorb|auf lager|"
                      r"sofort lieferbar|lieferbar|sofort verfügbar|verfügbar|en stock|有货|现货|在售|加入购物车|立即购买|在庫あり|在庫有|カートに入れる|即納|"
                      r"以内に出荷|営業日で出荷|出荷予定|お取り寄せ", re.I)
NOT_BUYABLE = re.compile(r"out of stock|sold out|pre-?order|notify me|coming soon|currently unavailable|not available|backorder|"
                         r"nicht (auf lager|lieferbar|verfügbar)|ausverkauft|vorbestell|缺货|无货|售罄|到货通知|预售|預約|"
                         r"在庫切れ|在庫なし|売り切れ|完売|予約|入荷待ち|refurbished|renewed|used|gebraucht|中古", re.I)
GPUPRIX = "gpuprix.com"


def gpuprix_offer(url, text):
    """A GPUPrix page read without the model: the cheapest new board marked In stock.
    (ans, why); (None, None) when the page has no offer table (then it is not used at all)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fetch_gpuprix import offers
    rows = offers(re.sub(r"\s+", " ", text))
    if not rows:
        return None, None
    stocked = sorted((r for r in rows if r[2] and r[1]), key=lambda r: r[1])
    if not stocked:
        return None, f"nothing in stock at {url} ({len(rows)} boards tracked, all out of stock)"
    board, amount, _, raw = stocked[0]
    return {"amount": amount, "basis": "lowest in stock", "source": url, "quote": raw, "stock": "In stock",
            "confidence": "high"}, None


CURRENCY_MARKS = {"USD": ("$", "usd", "us$"), "EUR": ("€", "eur", "euro"), "GBP": ("£", "gbp"),
                  "CNY": ("¥", "￥", "元", "cny", "rmb", "yuan"), "JPY": ("¥", "￥", "円", "jpy", "yen")}


def verify(ans, pages, keys, currency=None):
    """The model's answer is accepted only if it can be checked against the page it cites."""
    src = ans.get("source")
    if src not in pages:
        return "the cited page was not one we fetched"
    quote = norm(ans.get("quote"))
    if len(quote) < 12 or quote not in norm(pages[src]):
        return "the quoted sentence is not on the cited page"
    found = numbers(quote)
    for k in keys:
        v = ans.get(k)
        if v is None:
            continue
        if not any(abs(f - float(v)) <= max(1.0, 0.005 * float(v)) for f in found):
            return f"the quote does not contain {k} = {v}"
    if currency and not any(m in quote for m in CURRENCY_MARKS.get(currency, ())):
        return f"the quote does not show the price in {currency}"
    if "stock" in ans:                                   # products: proof that it can be bought now
        stock = norm(ans.get("stock"))
        if not stock or stock not in norm(pages[src]):
            return "no proof on the page that it is in stock"
        if NOT_BUYABLE.search(stock) or NOT_BUYABLE.search(quote):
            return "the page shows it is not buyable now (out of stock, pre-order or used)"
        if not IN_STOCK.search(stock):
            return f"'{ans.get('stock')[:40]}' does not show that it is in stock"
    return None


# ------------------------------------------------------------------ items

MARKETS = {   # how to search each market, and what its shelf prices include
    "US": {"words": "price USD", "lang": "", "tax": "excl"},
    "EU": {"words": "Preis Euro", "lang": "German retail price in EUR, including VAT, from a German or EU shop or news source", "tax": "incl"},
    "UK": {"words": "price UK £", "lang": "UK retail price in GBP including VAT", "tax": "incl"},
    "CN": {"words": "价格 元", "lang": "mainland China retail price in CNY (yuan/RMB), e.g. JD.com or Chinese tech news", "tax": "incl"},
    "JP": {"words": "価格 円", "lang": "Japan retail price in JPY including consumption tax, e.g. Japanese shops or kakaku coverage", "tax": "incl"},
}
FIRST_POINT_BAND = (0.6, 2.2)   # a market's first-ever price must sit within this band of the US price


def tasks(hw):
    month = date.today().strftime("%B %Y")
    regions = list(MARKETS)
    for n, pr in enumerate(hw["products"]):
        if pr.get("status") == "discontinued":
            continue                                   # no longer sold: its history is complete
        # markets it already has, plus the US, plus one new market a month in rotation: the
        # coverage keeps growing while the number of searches stays bounded
        have = {p["region"] for p in pr.get("prices", [])} | {"US"}
        missing = [r for r in regions if r not in have]
        if missing:
            have.add(missing[(date.today().month + n) % len(missing)])
        for reg, mk in ((r, MARKETS[r]) for r in regions if r in have):
            cur = hw["regions"][reg]["currency"]
            yield {"kind": "product", "id": pr["id"], "item": pr, "region": reg, "currency": cur, "name": f"{pr['name']} · {reg}",
                   "search_name": pr["name"],
                   "queries": [f'{pr["name"]} {mk["words"]} {month}', f'{pr["name"]} {mk["words"]}'],
                   "want": ("amount",),
                   "ask": (f'the current price of {pr["name"]} ({pr["mem_gb"]} GB) in market {reg}: '
                           f'{mk["lang"] or "US retail price in USD before sales tax (official store or lowest new retail)"}. '
                           f'ONLY a price at which a NEW unit can be bought right now counts: the page must show it in stock or '
                           f'available to order (add to cart, in stock, ships in...). Ignore out-of-stock, sold-out, pre-order and '
                           f'"notify me" offers, "from" prices, used or refurbished units and price-comparison headline lows. '
                           f'Return {{"amount": number in {cur} or null, "basis": "official store | lowest in stock", '
                           f'"source": "URL", "quote": "exact sentence from that page that states the price", '
                           f'"stock": "the exact words on that page showing it is in stock / can be ordered now", '
                           f'"confidence": "high|medium|low"}}. The amount must be in {cur}, as written on the page.')}
    for a in hw["accelerators"]:
        if not a.get("buy"):
            continue
        last = sorted(a["buy"], key=lambda b: b["date"])[-1]
        what = "one rack" if a["segment"] == "rack" else "ONE accelerator (not a server, not per-hour rental)"
        yield {"kind": "accel", "id": a["id"], "item": a, "region": "US" if a.get("country") != "CN" else "CN",
               "currency": last["currency"], "name": a["name"],
               "search_name": a["name"],
               "queries": [f'{a["name"]} price {month}', f'{a["name"]} cost per unit'],
               "want": ("low", "high"),
               "ask": (f'the current purchase price range of {what}: {a["name"]} ({a["vendor"]}). Recorded now: '
                       f'{last["low"]:,}-{(last.get("high") or last["low"]):,} {last["currency"]}. Return {{"low": number or null, '
                       f'"high": number or null, "currency": "USD|CNY", "source": "URL", "quote": "exact sentence from that page", '
                       f'"confidence": "high|medium|low"}}.')}


def last_point(t):
    if t["kind"] == "product":
        pts = sorted((p for p in t["item"]["prices"] if p["region"] == t["region"]), key=lambda p: p["date"])
        return pts[-1] if pts else None
    return sorted(t["item"]["buy"], key=lambda b: b["date"])[-1]


def us_reference(t, rates):
    """The latest US price in this product's currency for the market, to sanity-check a first point."""
    us = sorted((p for p in t["item"]["prices"] if p["region"] == "US"), key=lambda p: p["date"])
    if not us:
        return None
    per = rates.per_usd(t["currency"], date.today().isoformat()) if rates else None
    return us[-1]["amount"] * per if per else None


def registered(t, reg):
    """Pages registered for this product (or accelerator) and market."""
    if t["kind"] == "product":
        return list(reg.get("products", {}).get(t["id"], {}).get(t["region"], []))
    return list(reg.get("accelerators", {}).get(t["id"], []))


def read_pages(t, urls):
    pages, blocks = {}, []
    for url in urls:
        if len(pages) >= MAX_PAGES:
            break
        if url in pages or not allowed(url):
            continue
        try:
            text = page_text(url)
        except Exception as e:
            log(f"  skip {url[:70]}: {type(e).__name__}")
            continue
        ex = excerpt(text, t["search_name"])
        if ex:
            pages[url] = text
            blocks.append(f"### PAGE {len(blocks) + 1}\nURL: {url}\n{ex}")
    return pages, blocks


def judge(t, pages, blocks):
    """Ask the model, verify the answer. Returns (ans, reason): reason None = verified."""
    if t["kind"] == "product":
        nothing = None
        for url in list(pages):
            if GPUPRIX in url:
                ans, why = gpuprix_offer(url, pages[url])
                if ans:
                    bad = verify(ans, pages, ["amount"], t["currency"])
                    if not bad:
                        ans["_currency"] = t["currency"]
                        return ans, None
                nothing = why or nothing
                # a GPUPrix page is never handed to the model: its headline "current low"
                # includes out-of-stock offers
                pages.pop(url)
                blocks = [b for b in blocks if f"URL: {url}\n" not in b]
        if not blocks:
            return None, nothing or "no readable pages with prices"
    if not blocks:
        return None, "no readable pages with prices"
    prompt = (f"Find {t['ask']}\nToday is {date.today():%d %B %Y}. Use only these pages; prefer the most recent "
              f"and most specific one. If none states a current price for exactly this product and market, return nulls.\n\n"
              + "\n\n".join(blocks))
    try:
        ans = ask_model(prompt)
    except Exception as e:
        return None, f"model error: {e}"[:160]
    key = "amount" if t["kind"] == "product" else "low"
    if ans.get(key) in (None, "", 0):
        return ans, "no current price found on the pages read"
    cur = t["currency"]
    if t["kind"] == "accel" and ans.get("currency") in ("USD", "CNY"):
        cur = ans["currency"]
    bad = verify(ans, pages, [key], cur)
    if not bad and t["kind"] == "accel" and ans.get("high") is not None and verify(ans, pages, ["high"], cur):
        ans["high"] = None
    ans["_currency"] = cur
    return ans, bad


def check(t, rates, reg):
    """Run one task. Returns a report row; appends a point to the item if verified."""
    last = last_point(t)
    was = (last.get("amount") if t["kind"] == "product" else last.get("low")) if last else None
    row = {"name": t["name"], "region": t["region"], "currency": t["currency"], "was": was, "status": "no data",
           "now": None, "source": None, "quote": None, "why": "", "via": ""}
    # stage 1: the registered monitor pages (plus the page the last price came from)
    monitors = [urllib.parse.urlparse(x.get("url", "")).netloc.replace("www.", "") for x in reg.get("sites", {}).values()]
    on_monitor = lambda u: any(urllib.parse.urlparse(u).netloc.replace("www.", "").endswith(m) for m in monitors if m)
    # the page the last price came from is re-read only if it is a monitor page: re-reading an old
    # news article would record a weeks-old price as today's observation
    first = registered(t, reg) + ([last["src"]] if last and last.get("src") and on_monitor(last["src"]) else [])
    pages, blocks = read_pages(t, first)
    ans, why = judge(t, pages, blocks) if blocks else (None, "no registered page")
    via = "registered page"
    # stage 2: search, restricted to the monitor sites listed for this market
    if why:
        sites = reg.get("search_sites", {}).get(t["region"], [])
        found = []
        for site in sites[:3]:
            dom = site.split("/")[0]
            try:
                # keep only results that really are on the site asked for: some engines ignore site:
                found += [u for _, u, _ in search(f'site:{site} {t["search_name"]}')
                          if u and urllib.parse.urlparse(u).netloc.replace("www.", "").endswith(dom)]
            except Exception as e:
                log(f"  search failed for site:{site}: {e}")
        if not found and t["kind"] == "accel":          # datacenter prices come from news: open search, robots-checked
            for q in t["queries"][:1]:
                try:
                    found += [u for _, u, _ in search(q) if u]
                except Exception as e:
                    log(f"  search failed for {q!r}: {e}")
        p2, b2 = read_pages(t, [u for u in dict.fromkeys(found) if u not in pages])
        if b2:
            first_why = why
            ans, why = judge(t, p2, b2)
            via = "search"
            if why and first_why and first_why.startswith("nothing in stock"):
                why = first_why                 # the more useful finding: a monitor says nothing can be bought
    if ans and ans.get("source"):
        row.update(now=float(ans.get("amount") if t["kind"] == "product" else ans.get("low") or 0) or None,
                   source=ans.get("source"), quote=ans.get("quote"), via=via)
    if why:
        row.update(status="rejected" if ans and ans.get("source") and "no current price" not in why else "no data", why=why)
        return row
    new = row["now"]
    # GPUPrix quotes give the country's 12-month median too. The site's world map only trusts a
    # "current low" within 0.6-1.6x of that median (outside it, usually a bundle or a prebuilt
    # PC); the agent applies the same rule, so the two never disagree about the same number.
    med = re.search(r"12-month median\D{0,4}([\d][\d.,\s]*\d)", row.get("quote") or "")
    if med and new:
        readings = [v for v in numbers(med.group(1)) if v > 0]      # "3,436" could be read as 3.436 or 3436
        mv = min(readings, key=lambda v: abs(math.log(new / v))) if readings else None
        if mv and not (0.6 <= new / mv <= 1.6):
            row.update(status="held", why=f"{new / mv:.1f}x that country's 12-month median ({med.group(1).strip()}): "
                                         f"probably a bundle or a prebuilt PC; left out for a human to confirm")
            return row
    ref = was if was else (us_reference(t, rates) if t["kind"] == "product" else None)
    if ref:
        ratio = new / float(ref)
        band = (SANE_DOWN, SANE_UP) if was else FIRST_POINT_BAND
        if ratio < band[0] or ratio > band[1]:
            row.update(status="held", why=f"{(ratio - 1) * 100:+.0f}% against {'the last point' if was else 'the US price'}; "
                                         f"left out for a human to confirm")
            return row
    today = date.today().isoformat()
    if t["kind"] == "product":
        t["item"]["prices"].append({"date": today, "region": t["region"], "currency": t["currency"], "amount": round(new, 2),
                                    "tax": MARKETS[t["region"]]["tax"], "basis": (ans.get("basis") or "retail")[:40],
                                    "src": ans["source"]})
    else:
        t["item"]["buy"].append({"date": today, "low": round(new), "high": round(float(ans.get("high") or new)),
                                 "currency": ans["_currency"], "src": ans["source"]})
    # remember a page that worked, so next month goes straight there
    src = ans["source"]
    if via == "search" and robots_ok(src):
        if t["kind"] == "product":
            lst = reg.setdefault("products", {}).setdefault(t["id"], {}).setdefault(t["region"], [])
        else:
            lst = reg.setdefault("accelerators", {}).setdefault(t["id"], [])
        if src not in lst:
            lst.append(src)
            row["why"] = "new page registered"
    row["status"] = "new market" if was is None else ("updated" if abs(new - float(was)) > 0.005 * float(was) else "confirmed")
    return row


# ------------------------------------------------------------------ report

SYM = {"USD": "$", "EUR": "€", "GBP": "£", "CNY": "¥", "JPY": "¥"}


def money(v, cur="USD"):
    if v is None:
        return "—"
    s = SYM.get(cur, cur + " ")
    return f"{s}{v / 1e6:.1f}M" if v >= 1e6 else f"{s}{v:,.0f}" + ("" if cur in ("USD", "EUR", "GBP") else f" {cur}")


def report(rows, checked):
    icon = {"updated": "🟢 updated", "new market": "🔵 new market", "confirmed": "⚪ confirmed", "held": "🟠 held",
            "rejected": "🔴 rejected", "no data": "⚫ no data"}
    n = {k: sum(r["status"] == k for r in rows) for k in icon}
    out = [f"## Monthly price check · {checked}\n",
           f"Model `{LLM_MODEL}` via `{urllib.parse.urlparse(LLM_BASE).netloc}`, search `{SEARCH}`. "
           f"**{n['updated']} updated, {n['new market']} new markets, {n['confirmed']} confirmed**, "
           f"{n['held'] + n['rejected']} for review, {n['no data']} without data.\n",
           "Every accepted price was checked in code: the quoted sentence is on the cited page and contains the number, and the page shows the item IN STOCK (advertised prices for out-of-stock, pre-order or used units are refused). "
           "Each one is added as a new dated point, so the history grows; nothing is overwritten. Moves beyond ±30% "
           "against the last point, and first prices far from the US price, are held for you.\n",
           "| Item | Market | Last | Found | Status | Evidence |", "|---|---|---|---|---|---|"]
    order = list(icon)
    for r in sorted(rows, key=lambda r: (order.index(r["status"]), r["name"])):
        ev = (f'[{r.get("via") or "source"}]({r["source"]}): “{(r["quote"] or "")[:150]}”' if r["source"] else "") + (f" — {r['why']}" if r["why"] else "")
        out.append(f"| {r['name'].split(' · ')[0]} | {r['region']} | {money(r['was'], r['currency'])} | "
                   f"{money(r['now'], r['currency'])} | {icon[r['status']]} | {ev.replace('|', '/')} |")
    out.append("\nMerge to publish. Edit `build/hardware.json` in this branch first if anything looks wrong.")
    return "\n".join(out) + "\n"


def main():
    if not LLM_KEY:
        log("no LLM_API_KEY / MINIMAX_API_KEY set")
        return 1
    sys.path.insert(0, str(ROOT / "build"))
    import hwdata                                   # exchange rates, for first-point sanity checks
    rates = hwdata.Rates()
    hw = json.loads(HW.read_text())
    reg = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    if hw.get("version") != 2:
        log("hardware.json is not version 2; refusing to guess its layout")
        return 1
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
        rows.append(check(t, rates, reg))
        log(f"  -> {rows[-1]['status']} {rows[-1]['why']}")
        time.sleep(1)
    good = [r for r in rows if r["status"] in ("updated", "confirmed", "new market")]
    if not good and all(r["status"] == "no data" for r in rows):
        log("nothing could be checked; leaving hardware.json alone")
        REPORT.write_text(report(rows, date.today().isoformat()))
        return 1
    if good:
        hw["checked"] = date.today().isoformat()
    HW.write_text(json.dumps(hw, indent=1, ensure_ascii=False) + "\n")
    SOURCES.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n")
    REPORT.write_text(report(rows, date.today().isoformat()))
    log("done: " + ", ".join(f"{sum(r['status'] == k for r in rows)} {k}" for k in
                             ("updated", "new market", "confirmed", "held", "rejected", "no data")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
