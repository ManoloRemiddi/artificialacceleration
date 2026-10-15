#!/usr/bin/env python3
"""Verify researched buy-now offers against the live pages and write the verified ones into
build/hardware.json (and their pages into build/price_sources.json for the monthly check).

Usage: python3 pipeline/verify_offers.py offers1.json [offers2.json ...]
Each file: {"offers": [...], "unavailable": [...], "monitor_pages": [...]} as described in
ops/price-research-brief.md. Run by the weekly research agent; safe to re-run on the same day
(an offer already recorded for that product, market and date is not added twice).

An offer is accepted only if a fresh fetch shows: the price text (with that number and the
currency), the stock text, an in-stock marker, and no out-of-stock / pre-order / used marker.
Pages that need JavaScript are rendered in headless Chromium for the check."""
import json, pathlib, re, shutil, subprocess, sys, tempfile
from datetime import date

REPO = pathlib.Path(__file__).resolve().parent.parent
HERE = pathlib.Path(tempfile.gettempdir())
sys.path.insert(0, str(REPO / "pipeline"))
import price_agent as pa  # noqa: E402

RENDER = HERE / "render.js"
PLAYWRIGHT = "/home/manolo/jade-glade-v2/src/node_modules/playwright-core"   # optional: renders JavaScript-only shops
RENDER.write_text("""const { chromium } = require('""" + PLAYWRIGHT + """');
(async () => { const b = await chromium.launch({ executablePath: '/usr/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 artificialacceleration.com price check' });
  try { await p.goto(process.argv[2], { timeout: 45000, waitUntil: 'domcontentloaded' }); await p.waitForTimeout(5000);
        console.log(await p.evaluate(() => document.body.innerText)); } catch (e) { console.error(String(e)); }
  await b.close(); })();""")


def page(url, js):
    texts = []
    try:
        texts.append(pa.page_text(url))
    except Exception as e:
        texts.append("")
    if (js or not texts[0]) and shutil.which("node") and pathlib.Path(PLAYWRIGHT).exists():
        try:
            out = subprocess.run(["node", str(RENDER), url], capture_output=True, text=True, timeout=90).stdout
            texts.append(out)
        except Exception:
            pass
    return texts


def check(o):
    url = o["url"]
    if not pa.allowed(url):
        return "robots.txt or the blocklist forbids this site"
    pt, st = o.get("price_text") or "", o.get("stock_text") or ""
    for text in page(url, not o.get("verifiable_without_js", True)):
        if not text:
            continue
        n = pa.norm(text)
        if pa.norm(pt) not in n:
            continue
        if not any(abs(v - float(o["amount"])) <= max(1, 0.005 * float(o["amount"])) for v in pa.numbers(pt)):
            return "price text does not contain the amount"
        if not any(m in pa.norm(pt) for m in pa.CURRENCY_MARKS.get(o["currency"], ())) and o["currency"] not in ("CNY",):
            return "price text does not show the currency"
        if pa.norm(st) not in n:
            return "stock text not on the page"
        if pa.NOT_BUYABLE.search(st):
            return "stock text says not buyable"
        if not pa.IN_STOCK.search(st):
            return "stock text is not an in-stock marker"
        return None
    return "price text not found on the page (fetched and rendered)"


def main():
    hw = json.loads((REPO / "build" / "hardware.json").read_text())
    reg = json.loads((REPO / "build" / "price_sources.json").read_text())
    prods = {p["id"]: p for p in hw["products"]}
    today = date.today().isoformat()
    report = []
    best = {}
    files = [pathlib.Path(a) for a in sys.argv[1:]]
    if not files:
        sys.exit(__doc__)
    for f in files:
        d = json.loads(f.read_text())
        for o in d.get("offers", []):
            if o.get("product_id") not in prods or o.get("region") not in hw["regions"]:
                report.append((o.get("product_id"), o.get("region"), "skipped: unknown product or market"))
                continue
            if o.get("condition", "new") != "new":
                continue
            why = check(o)
            report.append((o["product_id"], o["region"], f"{o['amount']:,} {o['currency']} {o.get('seller')}: " + ("VERIFIED" if not why else "rejected: " + why)))
            if not why and o["currency"] == hw["regions"][o["region"]]["currency"]:
                k = (o["product_id"], o["region"])
                if k not in best or o["amount"] < best[k]["amount"]:
                    best[k] = o
        for u in d.get("unavailable", []):
            report.append((u.get("product_id"), u.get("region"), "unavailable: " + (u.get("evidence") or "")[:120]))
        for m in d.get("monitor_pages", []):
            if m.get("product_id") in prods and pa.allowed(m.get("url", "")):
                lst = reg.setdefault("products", {}).setdefault(m["product_id"], {}).setdefault(m["region"], [])
                if m["url"] not in lst:
                    lst.append(m["url"])
    added = 0
    for (pid, region), o in best.items():
        p = prods[pid]
        if any(x["region"] == region and x["date"] == today and x.get("stock") == "in" and x.get("src") == o["url"] for x in p["prices"]):
            continue
        p["prices"].append({"date": today, "region": region, "currency": o["currency"], "amount": float(o["amount"]),
                            "tax": "excl" if region == "US" else "incl", "basis": f"cheapest new in stock ({o.get('seller')})",
                            "stock": "in", "src": o["url"], "quote": (o.get("price_text") or "")[:200]})
        p.get("unavailable", {}).pop(region, None)
        added += 1
        lst = reg.setdefault("products", {}).setdefault(pid, {}).setdefault(region, [])
        if o["url"] not in lst and pa.allowed(o["url"]):
            lst.append(o["url"])
    # unavailable markets: only where nothing verified was found
    for f in files:
        for u in json.loads(f.read_text()).get("unavailable", []):
            pid, region = u.get("product_id"), u.get("region")
            if pid in prods and region in hw["regions"] and (pid, region) not in best:
                mb = [o for f2 in files for o in json.loads(f2.read_text()).get("offers", [])
                      if o.get("product_id") == pid + "-mainboard-only" and o.get("region") == region]
                if mb:
                    u = dict(u, evidence=(u.get("evidence") or "") + f" (the bare mainboard alone is in stock at {mb[0]['amount']:,} {mb[0]['currency']})")
                ev = u.get("evidence") or ""
                # "out": sellers checked, all out of stock. "unverifiable": the shops cannot be
                # checked (login walls, robots.txt), which is not the same as out of stock
                unver = region == "CN" or re.search(r"not verified|login|log in|sign in|robots|captcha|verification|验证|cannot be (checked|verified)|blocked|403", ev, re.I)
                prods[pid].setdefault("unavailable", {})[region] = {
                    "date": today, "src": (u.get("urls") or [None])[0], "kind": "unverifiable" if unver else "out",
                    "note": ("stock cannot be verified: China's main shop (JD.com) requires a login and Tmall forbids automated access"
                             if region == "CN" else ("cannot be verified: " if unver else "not in stock: ") + ev)[:200]}
    (REPO / "build" / "hardware.json").write_text(json.dumps(hw, indent=1, ensure_ascii=False) + "\n")
    (REPO / "build" / "price_sources.json").write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n")
    for r in sorted(report, key=lambda x: (str(x[0]), str(x[1]))):
        print(*r, sep=" | ")
    print(f"\n{added} verified buy-now prices written")


if __name__ == "__main__":
    main()
