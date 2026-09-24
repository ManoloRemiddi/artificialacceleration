#!/usr/bin/env python3
"""
Turn the raw API snapshot into the page dataset.

  data/snapshots/raw.json  (or data/baseline.json)  ->  data/releases.json

- collapses effort variants to the strongest scoring one per release
- computes the gap (days) since that lab's previous release
- flags releases that count as "notable" for the timeline lanes
"""
import json, pathlib, re, sys
from datetime import date

R = pathlib.Path(__file__).resolve().parent.parent
LABS = json.loads((R / "build" / "labs.json").read_text())

def pick_source():
    p = R / "data" / "baseline.json"
    if not p.exists():
        sys.exit("no baseline found — run pipeline/fetch.py first")
    return p

EFFORT = re.compile(r"\s*\((?=[^()]*(?:effort|fallback|reasoning|default|preview|thinking|low|medium|high|xhigh|max|minimal))[^()]*\)\s*$", re.I)
def base(n):
    n = (n or "").strip()
    for _ in range(3):
        n2 = EFFORT.sub("", n).strip()
        if n2 == n or not n2: break
        n = n2
    return n

def main():
    src = pick_source()
    raw = json.loads(src.read_text())
    rows = raw.get("rows", raw if isinstance(raw, list) else [])

    by_lab = {L["aa_names"][0]: L for L in LABS}
    alias = {}
    for L in LABS:
        for n in L["aa_names"]:
            alias[n.lower()] = L

    best = {}
    for r in rows:
        L = alias.get(str(r.get("creator", "")).lower())
        if not L:
            continue
        r = dict(r)
        r["variant"] = r.get("release")
        r["release"] = base(r.get("release"))
        r["lab"] = L["id"]
        r["notable"] = bool(r.get("release") in set(L.get("notable", [])))
        k = (L["id"], r["release"], r.get("date"))
        cur = best.get(k)
        if cur is None or (r.get("ii") or -1) > (cur.get("ii") or -1):
            best[k] = r

    out = sorted(best.values(), key=lambda r: (r.get("date") or "", r["lab"]))
    # gap since the same lab's previous release
    prev = {}
    for r in out:
        lab = r["lab"]
        d = r.get("date")
        if d and lab in prev:
            r["gap"] = (date.fromisoformat(d) - date.fromisoformat(prev[lab])).days
        else:
            r["gap"] = None
        if d:
            prev[lab] = d

    payload = {
        "generated_utc": raw.get("fetched_utc"),
        "source": raw.get("source", "api"),
        "row_count": len(out),
        "rows": out,
    }
    (R / "data" / "releases.json").write_text(json.dumps(payload, indent=1))
    notab = [r for r in out if r["notable"]]
    scored = [r for r in out if r.get("ii") is not None]
    print(f"releases={len(out)} notable={len(notab)} scored={len(scored)}")
    labs = sorted({r['lab'] for r in out})
    print("labs:", ", ".join(labs))

if __name__ == "__main__":
    main()
