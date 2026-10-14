#!/usr/bin/env python3
"""
Exchange rates for the hardware tracker: how many units of each currency one US dollar
bought on each date, from the European Central Bank's reference rates via Frankfurter
(https://frankfurter.dev, free, no key, open source).

Writes data/fx.json: {"base": "USD", "rates": {"EUR": [["2020-01-02", 0.893], ...], ...}}
Weekly samples (Mondays) keep the file small; a price is converted at the latest sample on
or before its own date. Never fails the job: on any error the committed file stays.
"""
import json, pathlib, sys, urllib.request
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fx.json"
CURRENCIES = ["EUR", "GBP", "CNY", "JPY", "INR", "KRW"]
START = "2020-01-01"


def main():
    url = (f"https://api.frankfurter.dev/v1/{START}..{date.today().isoformat()}"
           f"?base=USD&symbols={','.join(CURRENCIES)}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "artificialacceleration.com data job"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"fx: fetch failed ({type(e).__name__}); keeping {OUT.name}")
        return 0
    days = sorted(data.get("rates", {}))
    if len(days) < 100:
        print(f"fx: only {len(days)} days returned; keeping {OUT.name}")
        return 0
    # one sample per ISO week (its first business day), plus the latest day
    keep, seen = [], set()
    for d in days:
        wk = date.fromisoformat(d).isocalendar()[:2]
        if wk not in seen:
            seen.add(wk)
            keep.append(d)
    if keep[-1] != days[-1]:
        keep.append(days[-1])
    rates = {c: [[d, data["rates"][d][c]] for d in keep if c in data["rates"][d]] for c in CURRENCIES}
    OUT.write_text(json.dumps({"base": "USD", "source": "European Central Bank via frankfurter.dev",
                               "rates": rates}, separators=(",", ":")) + "\n")
    print(f"fx: {len(keep)} weekly samples, {keep[0]} to {keep[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
