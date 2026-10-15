#!/usr/bin/env python3
"""
Graphics-card prices in 17 countries, from GPUPrix (https://gpuprix.com), once a day.

Every GPUPrix product page carries one fixed sentence:
    "<card> price history in Japan: current low ¥240,802, 12-month low ¥229,555,
     12-month median ¥265,071."
so the numbers are read by a pattern, not by a model: nothing to hallucinate. GPUPrix's
robots.txt allows crawling; we fetch one page a second, at most once a day, and credit it.

Writes data/gpu_world.json:
    countries   slug -> {iso, name, currency, vat}
    latest      product -> country -> {date, buy, buy_board, buy_median, in_stock, offers,
                                       listed_low, listed_median12}
                buy = the cheapest board IN STOCK (None when nothing can be bought);
                listed_* = GPUPrix's headline figures, which include out-of-stock offers
    history     product -> country -> [[date, buy, in_stock], ...]  (one point a week, or
                sooner when the price moves by more than 3% or stock appears or vanishes)

Never fails the job: on any error the committed file stays.
"""
import json, pathlib, re, sys, time, urllib.request
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "gpu_world.json"
UA = "artificialacceleration.com price check (+https://artificialacceleration.com)"

# gpuprix country slug -> ISO 3166 numeric (for the map), name, currency, VAT in shelf prices
COUNTRIES = {
    "us": ("840", "United States", "USD", 0.0), "germany": ("276", "Germany", "EUR", 0.19),
    "uk": ("826", "United Kingdom", "GBP", 0.20), "japan": ("392", "Japan", "JPY", 0.10),
    "france": ("250", "France", "EUR", 0.20), "italy": ("380", "Italy", "EUR", 0.22),
    "spain": ("724", "Spain", "EUR", 0.21), "netherlands": ("528", "Netherlands", "EUR", 0.21),
    "belgium": ("056", "Belgium", "EUR", 0.21), "ireland": ("372", "Ireland", "EUR", 0.23),
    "portugal": ("620", "Portugal", "EUR", 0.23), "sweden": ("752", "Sweden", "SEK", 0.25),
    "australia": ("036", "Australia", "AUD", 0.10), "india": ("356", "India", "INR", 0.18),
    "singapore": ("702", "Singapore", "SGD", 0.09), "uae": ("784", "United Arab Emirates", "AED", 0.05),
    "brazil": ("076", "Brazil", "BRL", None),      # several stacked taxes: no single rate to remove
}
# our product id -> gpuprix product slug
PRODUCTS = {
    "rtx-5090": "geforce-rtx-5090", "rtx-5080": "geforce-rtx-5080", "rtx-5070-ti": "geforce-rtx-5070-ti",
    "rtx-4090": "geforce-rtx-4090", "rtx-3090": "geforce-rtx-3090", "rtx-pro-6000": "rtx-pro-6000-blackwell",
    "amd-radeon-ai-pro-r9700": "radeon-ai-pro-r9700", "amd-rx-9070-xt": "radeon-rx-9070-xt",
    "arc-pro-b50": "arc-pro-b50", "arc-pro-b60": "arc-pro-b60", "arc-pro-b65": "arc-pro-b65",
    "arc-pro-b70": "arc-pro-b70", "arc-b580": "arc-b580",
}
NUM = r"[^\d\s,]{0,4}\s?(\d[\d.,]*\d|\d)\s?[A-Z]{0,3}"     # the number must end on a digit, not eat the comma
SENTENCE = re.compile(r"price history in [^:]{2,40}: current low " + NUM +
                      r"(?:, 12-month low " + NUM + r")?(?:, 12-month median " + NUM + r")?")


def amount(txt):
    """'240,802' / '6.766' (some locales) / '4,721' -> float."""
    if txt is None:
        return None
    t = txt.strip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):        # 6.766 with a dot as thousands separator
        t = t.replace(".", "")
    return float(t.replace(",", ""))


ROW = re.compile(r"(.*?)\s(?:OC|—)\s(?:\d+ mm|—)\s(.*?)\s(In stock|Out of stock)")


def offers(text):
    """Every board offer in a GPUPrix page's table: [(board, amount or None, in_stock, row text)].
    The table ("Board Series OC Length Price Stock") lists each board with its cheapest
    in-region price and whether it can be bought now."""
    i = text.find("Board Series OC Length Price Stock")
    if i < 0:
        return []
    table = text[i + len("Board Series OC Length Price Stock"):]
    end = re.search(r" (How does|Recommended CPUs|Compare GPU Prices|Local LLMs|Related Reading)", table)
    table = table[:end.start()] if end else table[:6000]
    out = []
    for m in ROW.finditer(table):
        board, price, stock = m.group(1).strip(), m.group(2).strip(), m.group(3)
        num = re.search(r"\d[\d.,\s]*\d|\d", price) if price != "—" else None
        out.append((board, amount(num.group(0).replace(" ", "").replace("\u00a0", "")) if num else None, stock == "In stock",
                    m.group(0).strip()))
    return out


def read(country, slug):
    url = f"https://gpuprix.com/{country}/gpus/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read(2_000_000).decode("utf-8", "ignore")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    # The price that counts is one you can pay now: the cheapest board IN STOCK. The page's
    # headline "current low" and 12-month median mix in out-of-stock offers (lures: an RTX
    # 5090 "from $2,869" when nothing under $7,200 can be bought), so they are kept only as
    # "listed" figures and never used as the price.
    rows = offers(text)
    stocked = sorted((a, b) for b, a, s, _ in rows if s and a)
    m = SENTENCE.search(text)
    listed = [amount(g) for g in m.groups()] if m else [None, None, None]
    if not rows and not m:
        return None
    mid = stocked[len(stocked) // 2][0] if stocked else None
    # Workstation cards have no board table, only shop links without a stock label; an
    # unlabelled link is not proof of stock (the RTX 5090's "$2,869" link is one), so those
    # pages give no buy-now price: stock_reported is False
    return {"buy": stocked[0][0] if stocked else None, "buy_board": stocked[0][1] if stocked else None,
            "buy_median": mid, "in_stock": len(stocked), "offers": len(rows), "stock_reported": bool(rows),
            "listed_low": listed[0], "listed_median12": listed[2]}


def main(force=False):
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    today = date.today().isoformat()
    if old.get("fetched") == today and not force:
        print("gpu world: already fetched today")
        return 0
    latest = old.get("latest", {})
    # format 2 (Oct 2026) records buy-now prices; history from format 1 recorded advertised
    # lows, which are not prices, so it is not carried over
    history = old.get("history", {}) if old.get("format") == 2 else {}
    ok = fail = 0
    last = 0.0
    for pid, slug in PRODUCTS.items():
        for c in COUNTRIES:
            wait = 1.0 - (time.monotonic() - last)         # at most one request a second: a polite guest
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            try:
                obs = read(c, slug)
            except Exception:
                obs = None
            if not obs:
                fail += 1
                continue
            ok += 1
            obs["date"] = today
            latest.setdefault(pid, {})[c] = obs
            # history of the buy-now price ([date, cheapest in stock or None, boards in stock]):
            # a point a week, or sooner when the price moves by more than 3% or stock appears/vanishes
            h = history.setdefault(pid, {}).setdefault(c, [])
            prev = h[-1] if h else None
            moved = prev and ((prev[1] is None) != (obs["buy"] is None) or
                              (prev[1] and obs["buy"] and abs(obs["buy"] - prev[1]) / prev[1] > 0.03))
            if not h or moved or (date.fromisoformat(today) - date.fromisoformat(prev[0])).days >= 7:
                h.append([today, obs["buy"], obs["in_stock"]])
    if ok < 20:
        print(f"gpu world: only {ok} pages read ({fail} failed); keeping {OUT.name}")
        return 0
    OUT.write_text(json.dumps({
        "source": "GPUPrix", "url": "https://gpuprix.com", "fetched": today, "format": 2,
        "countries": {k: {"iso": v[0], "name": v[1], "currency": v[2], "vat": v[3]} for k, v in COUNTRIES.items()},
        "latest": latest, "history": history}, separators=(",", ":")) + "\n")
    print(f"gpu world: {ok} prices read, {fail} pages without data")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
