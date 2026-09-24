#!/usr/bin/env python3
"""The Acceleration Index: how frantic the last 30 days have been.

A composite on a 0-100 scale, in the spirit of the crypto Fear & Greed Index
(https://alternative.me/crypto/fear-and-greed-index/): one number, four inputs,
each normalised to the same scale, published with its own history so the reader
can see whether today is unusual or ordinary.

The four inputs, all measured over a trailing 30-day window:

  tempo    releases shipped in the window
  climb    how far the frontier moved: best index now minus best index 30 days ago
  breadth  how many distinct labs shipped in the window
  burst    the densest 7-day stretch inside the window

Each input is then scored as its percentile among **every** 30-day window since
the record began, sampled weekly. That keeps the scale honest: a busy month in a
quiet year cannot score like a busy month at the top of a boom. The index is the
mean of the four percentiles.

This is our own measure, built from this dataset. It is not an industry metric
and it is not investment advice; it describes release behaviour, nothing else.

    python3 scripts/acceleration_index.py            # human summary
    python3 scripts/acceleration_index.py --json     # the payload
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

WINDOW_DAYS = 30
BURST_DAYS = 7
STEP_DAYS = 7              # how densely the historical grid is sampled
PARTS = ("tempo", "climb", "breadth", "burst")

LEVELS = (
    (0, "Slow", "#4a7bd6"),
    (25, "Warming", "#2fb8a3"),
    (45, "Brisk", "#d8b13a"),
    (55, "Fast", "#e2843f"),
    (75, "Runaway", "#e04a4a"),
)

ROOT = Path(__file__).resolve().parent.parent


def level_for(value: int):
    label, colour = LEVELS[0][1], LEVELS[0][2]
    for floor, name, hexcode in LEVELS:
        if value >= floor:
            label, colour = name, hexcode
    return label, colour


def load_records(path: Path | None = None):
    data = json.loads((path or ROOT / "data" / "releases.json").read_text())
    out = []
    for r in data["rows"]:
        out.append((dt.date.fromisoformat(r["date"]), r["lab"], r.get("ii")))
    # None scores sort last rather than blowing up the comparison
    out.sort(key=lambda r: (r[0], r[1], r[2] is None, r[2] or 0))
    return out, dt.datetime.fromisoformat(data["generated_utc"]).date()


def metrics(recs, end: dt.date, window: int = WINDOW_DAYS) -> dict:
    lo = end - dt.timedelta(days=window)
    inside = [r for r in recs if lo < r[0] <= end]
    before = [r[2] for r in recs if r[0] <= lo and r[2] is not None]
    now = [r[2] for r in inside if r[2] is not None]
    climb = 0.0 if not before or not now else max(now) - max(before)
    burst = max((sum(1 for o in inside if 0 <= (o[0] - r[0]).days < BURST_DAYS) for r in inside),
                default=0)
    return {"tempo": len(inside), "climb": round(climb, 2),
            "breadth": len({r[1] for r in inside}), "burst": burst}


def percentile(series, value) -> float:
    """Mid-rank percentile, so a value tied with half the history lands on 50."""
    below = sum(1 for x in series if x < value)
    equal = sum(1 for x in series if x == value)
    return 100.0 * (below + 0.5 * equal) / len(series)


def build_index(recs, as_of: dt.date) -> dict:
    grid, day = [], recs[0][0] + dt.timedelta(days=WINDOW_DAYS)
    while day <= as_of:
        grid.append(day)
        day += dt.timedelta(days=STEP_DAYS)
    if not grid or grid[-1] != as_of:
        grid.append(as_of)

    by_date = {g: metrics(recs, g) for g in grid}
    history = {k: [by_date[g][k] for g in grid] for k in PARTS}

    def score(end: dt.date):
        m = by_date.get(end) or metrics(recs, end)
        parts = {k: round(percentile(history[k], m[k]), 1) for k in PARTS}
        return round(sum(parts.values()) / len(parts)), m, parts

    value, raw, parts = score(as_of)

    # One sample per month for the trace. A raw monthly percentile bounces hard
    # month to month, which reads as noise rather than trend, so each point is a
    # three-month mean. The final point is the real reading, so the head of the
    # trace and the number on the gauge always agree.
    monthly, seen = [], set()
    for g in grid:
        key = (g.year, g.month)
        if key in seen:
            continue
        seen.add(key)
        monthly.append((g.isoformat(), score(g)[0]))
    series = []
    for i, (day, _) in enumerate(monthly):
        lo, hi = max(0, i - 1), min(len(monthly), i + 2)
        window = [v for _, v in monthly[lo:hi]]
        series.append((day, round(sum(window) / len(window))))
    if series and series[-1][0] != as_of.isoformat():
        series.append((as_of.isoformat(), value))
    else:
        series[-1] = (as_of.isoformat(), value)
    label, colour = level_for(value)

    return {
        "value": value,
        "level": label,
        "colour": colour,
        "as_of": as_of.isoformat(),
        "window_days": WINDOW_DAYS,
        "parts": [{"key": k, "raw": raw[k], "pct": parts[k]} for k in PARTS],
        "week": score(as_of - dt.timedelta(days=7))[0],
        "month": score(as_of - dt.timedelta(days=30))[0],
        "series": series,
        "sampled": len(grid),
    }


def main():
    recs, as_of = load_records()
    idx = build_index(recs, as_of)
    if "--json" in sys.argv:
        print(json.dumps(idx, indent=1))
        return
    print(f"Acceleration Index: {idx['value']} ({idx['level']}) as of {idx['as_of']}")
    for p in idx["parts"]:
        print(f"   {p['key']:8s} raw={p['raw']:>7}  percentile={p['pct']}")
    print(f"   a week ago {idx['week']} · a month ago {idx['month']}"
          f" · {idx['sampled']} windows sampled · {len(idx['series'])} trace points")


if __name__ == "__main__":
    main()
