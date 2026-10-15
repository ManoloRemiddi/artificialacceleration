#!/usr/bin/env python3
"""
Copy buy-now graphics-card prices from data/gpu_world.json into build/hardware.json, daily.

data/gpu_world.json holds, per card and country, the cheapest board IN STOCK as read from
GPUPrix's offer tables (pipeline/fetch_gpuprix.py). For the four hardware markets GPUPrix
covers (US, Germany for the euro area, UK, Japan) that is a verified buy-now price, so it
goes straight into the price history:
  - a new dated point when there is none yet, when the price moved by more than 3%, or when
    the last point is a week old;
  - when boards are tracked but none is in stock, the market is marked "unavailable" with
    the date, so the page says "nothing in stock" instead of showing an old price as current.
Points carry stock="in": the page draws them as verified, and older points without it as
"availability not verified".
"""
import json, pathlib, sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
HW = ROOT / "build" / "hardware.json"
WORLD = ROOT / "data" / "gpu_world.json"
MARKETS = {"us": "US", "germany": "EU", "uk": "UK", "japan": "JP"}


def main():
    if not WORLD.exists():
        return 0
    g = json.loads(WORLD.read_text())
    if g.get("format") != 2:
        print("card prices: gpu_world.json has no stock data; nothing synced")
        return 0
    hw = json.loads(HW.read_text())
    products = {p["id"]: p for p in hw["products"]}
    added = marked = 0
    for pid, by_c in g.get("latest", {}).items():
        p = products.get(pid)
        if not p:
            continue
        for c, region in MARKETS.items():
            o = by_c.get(c)
            if not o or not o.get("stock_reported") or not o.get("date"):
                continue
            cur = hw["regions"][region]["currency"]
            if g["countries"][c]["currency"] != cur:
                continue
            src = f"https://gpuprix.com/{c}/gpus/{GPUPRIX_SLUG.get(pid, pid)}"
            un = p.setdefault("unavailable", {})
            if not o.get("buy"):
                if un.get(region, {}).get("date") != o["date"]:
                    un[region] = {"date": o["date"], "src": src,
                                  "note": f"none of the {o.get('offers', 0)} boards tracked is in stock"}
                    marked += 1
                continue
            un.pop(region, None)
            pts = sorted((x for x in p["prices"] if x["region"] == region and x.get("stock") == "in"), key=lambda x: x["date"])
            last = pts[-1] if pts else None
            if last and last["date"] == o["date"]:
                continue
            moved = not last or abs(o["buy"] - last["amount"]) / last["amount"] > 0.03
            stale = not last or (date.fromisoformat(o["date"]) - date.fromisoformat(last["date"])).days >= 7
            if moved or stale:
                p["prices"].append({"date": o["date"], "region": region, "currency": cur, "amount": o["buy"],
                                    "tax": "excl" if region == "US" else "incl",
                                    "basis": "cheapest new board in stock", "stock": "in", "src": src,
                                    "quote": f"{o.get('buy_board') or 'board'}: {o['buy']:,.0f} {cur}, In stock "
                                             f"({o.get('in_stock')} of {o.get('offers')} boards in stock)"})
                added += 1
        if not p.get("unavailable"):
            p.pop("unavailable", None)
    HW.write_text(json.dumps(hw, indent=1, ensure_ascii=False) + "\n")
    print(f"card prices: {added} buy-now points added, {marked} markets marked nothing-in-stock")
    return 0


# our product id -> GPUPrix page slug (same table as fetch_gpuprix.PRODUCTS)
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch_gpuprix import PRODUCTS as GPUPRIX_SLUG  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
