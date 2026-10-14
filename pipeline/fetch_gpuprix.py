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
    latest      product -> country -> {date, current, low12, median12}
    history     product -> country -> [[date, current, median12], ...]  (one point a week,
                or sooner when the price moves by more than 3%: the series builds itself)
The raw numbers are kept as published; the page decides what is plausible (a "current low"
far from the 12-month median is usually an accessory or a marketplace listing).

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


def read(country, slug):
    url = f"https://gpuprix.com/{country}/gpus/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read(2_000_000).decode("utf-8", "ignore")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    m = SENTENCE.search(text)
    if not m:
        return None
    cur, low, med = (amount(g) for g in m.groups())
    return {"current": cur, "low12": low, "median12": med}


def main(force=False):
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    today = date.today().isoformat()
    if old.get("fetched") == today and not force:
        print("gpu world: already fetched today")
        return 0
    latest, history = old.get("latest", {}), old.get("history", {})
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
            if not obs or not obs["current"]:
                fail += 1
                continue
            ok += 1
            obs["date"] = today
            latest.setdefault(pid, {})[c] = obs
            h = history.setdefault(pid, {}).setdefault(c, [])
            moved = h and h[-1][1] and abs(obs["current"] - h[-1][1]) / h[-1][1] > 0.03
            if not h or moved or (date.fromisoformat(today) - date.fromisoformat(h[-1][0])).days >= 7:
                h.append([today, obs["current"], obs["median12"]])
    if ok < 20:
        print(f"gpu world: only {ok} pages read ({fail} failed); keeping {OUT.name}")
        return 0
    OUT.write_text(json.dumps({
        "source": "GPUPrix", "url": "https://gpuprix.com", "fetched": today,
        "countries": {k: {"iso": v[0], "name": v[1], "currency": v[2], "vat": v[3]} for k, v in COUNTRIES.items()},
        "latest": latest, "history": history}, separators=(",", ":")) + "\n")
    print(f"gpu world: {ok} prices read, {fail} pages without data")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
