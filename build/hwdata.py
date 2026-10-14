# -*- coding: utf-8 -*-
"""Hardware data model, shared by the page section, the hardware page and the price agent.

build/hardware.json (v2):
  regions       code -> {label, currency, vat}       vat = rate included in that market's
                                                      shelf prices (0 for the US, where prices
                                                      are quoted before sales tax)
  products      home-lab / workstation hardware, each with a list of dated price points:
                {date, region, currency, amount, tax: "incl"|"excl", basis, src, low?, high?}
  accelerators  datacenter parts across vendors and countries, with dated purchase
                estimates {date, low, high, currency, src} and optional rental notes

data/fx.json    weekly USD exchange rates (ECB via frankfurter.dev), so every price can be
                shown in dollars as of its own date, never at today's rate.
"""
import bisect, json, pathlib
from datetime import date

R = pathlib.Path(__file__).resolve().parent.parent
HW = R / "build" / "hardware.json"
FX = R / "data" / "fx.json"

REGION_ORDER = ["US", "EU", "UK", "CN", "JP"]


def load():
    return json.loads(HW.read_text())


def save(hw):
    HW.write_text(json.dumps(hw, indent=1, ensure_ascii=False) + "\n")


class Rates:
    """USD per unit of a currency on (or just before) a date."""

    def __init__(self):
        raw = json.loads(FX.read_text())["rates"] if FX.exists() else {}
        self.days = {c: [d for d, _ in v] for c, v in raw.items()}
        self.vals = {c: [x for _, x in v] for c, v in raw.items()}

    def per_usd(self, currency, iso):
        if currency == "USD":
            return 1.0
        if currency == "AED":                     # UAE dirham: pegged at 3.6725 per dollar since 1997
            return 3.6725
        days = self.days.get(currency)
        if not days:
            return None
        i = bisect.bisect_right(days, iso) - 1
        return self.vals[currency][max(i, 0)]

    def to_usd(self, amount, currency, iso):
        r = self.per_usd(currency, iso)
        return None if r is None or amount is None else amount / r


def usd(point, rates, regions, ex_tax=False):
    """A price point in US dollars at its own date; ex_tax strips the VAT a market includes."""
    v = rates.to_usd(point["amount"], point["currency"], point["date"][:10] if len(point["date"]) > 7 else point["date"] + "-15")
    if v is None:
        return None
    if ex_tax and point.get("tax") == "incl":
        v /= 1 + regions.get(point["region"], {}).get("vat", 0)
    return v


def series(product, region):
    return sorted((p for p in product.get("prices", []) if p["region"] == region), key=lambda p: p["date"])


def first_last(product, region="US"):
    s = series(product, region)
    return (s[0], s[-1]) if s else (None, None)


def to_date(iso):
    return date.fromisoformat(iso if len(iso) > 7 else iso + "-15")
