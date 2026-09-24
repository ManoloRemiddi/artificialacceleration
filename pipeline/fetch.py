#!/usr/bin/env python3
"""
Frontier-model data fetcher.

Source A (preferred): Artificial Analysis Data API
    GET https://artificialanalysis.ai/api/v2/data/llms/models
    header: x-api-key: $AA_API_KEY
    Free tier, 1000 requests/day. Per their terms: keep the key server-side,
    cache and reuse responses, and attribute the data.

Source B (fallback, no key): parse the model ledger embedded in
    https://artificialanalysis.ai/models   — same fields, but markup-dependent.

Writes:
    data/snapshots/YYYY-MM-DD.json   raw normalised snapshot
    state/baseline.json              newest snapshot, used for the next diff
    state/changes.jsonl              append-only changelog of what changed
Exit codes: 0 = ok (changed or not), 1 = fetch failed, 2 = config error
"""
import json, os, re, sys, datetime, pathlib, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "snapshots"      # dated raw snapshots (committed: one per day)
STATE = ROOT / "data"                    # baseline.json + changelog.jsonl live here
LOGS = ROOT / "data"
for d in (SNAP, STATE, LOGS):
    d.mkdir(parents=True, exist_ok=True)

API_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
PAGE_URL = "https://artificialanalysis.ai/models"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"

# labs we track on the page
TRACKED = {
    "OpenAI", "Anthropic", "Google", "SpaceXAI", "xAI", "Meta",
    "DeepSeek", "Alibaba", "Kimi", "Moonshot", "Z AI", "Z.ai", "Zhipu",
}

def log(msg):
    line = f"[{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M:%SZ}] {msg}"
    print(line, flush=True)
    with open(LOGS / "fetch.log", "a") as fh:
        fh.write(line + "\n")

def api_key():
    k = os.environ.get("AA_API_KEY", "").strip()
    if k:
        return k
    # read silently, never print
    sec = pathlib.Path.home() / ".dsh" / "secrets.env"
    if sec.exists():
        for raw in sec.read_text(errors="ignore").splitlines():
            line = raw.strip().replace("export ", "")
            if line.startswith("AA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def http_get(url, headers=None, timeout=40):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

# ---------- source A: official API ----------
# NOTE: the API speaks snake_case and nests scores under "evaluations";
# the page's embedded JSON-LD uses camelCase. They are NOT interchangeable.
def fetch_api(key):
    body = http_get(API_URL, {"User-Agent": UA, "Accept": "application/json", "x-api-key": key})
    data = json.loads(body)
    models = data.get("data", [])
    out = []
    for m in models:
        creator = m.get("model_creator") or {}
        cname = creator.get("name") if isinstance(creator, dict) else str(creator)
        ev = m.get("evaluations") or {}
        pr = m.get("pricing") or {}
        out.append({
            "creator": cname,
            "release": m.get("name"),
            "slug": m.get("slug"),
            "date": m.get("release_date"),
            "ii": ev.get("artificial_analysis_intelligence_index"),
            "coding": ev.get("artificial_analysis_coding_index"),
            "hle": ev.get("hle"),
            "gpqa": ev.get("gpqa"),
            "swe": ev.get("scicode"),
            "price_in": pr.get("price_1m_input_tokens"),
            "price_out": pr.get("price_1m_output_tokens"),
            "tps": m.get("median_output_tokens_per_second"),
            "estimated": False,
            "effort": None,
            "open": None,
        })
    return out, "api"

# ---------- source B: embedded ledger in the page ----------
def fetch_scrape():
    page = http_get(PAGE_URL)
    u = page.replace('\\"', '"')
    pat = re.compile(r'"slug":"([^"]+)","name":"((?:[^"\\]|\\.)*)","deprecated":(?:true|false),'
                     r'"release":\{"slug":"([^"]*)","name":"((?:[^"\\]|\\.)*)"\},'
                     r'"releaseDate":"(\d{4}-\d{2}-\d{2})","creator":\{[^}]*?"name":"((?:[^"\\]|\\.)*)"')
    seen, out = set(), []
    for slug, name, rslug, rname, date, creator in pat.findall(u):
        if creator not in TRACKED:
            continue
        k = (creator, rname, date)
        if k in seen:
            continue
        seen.add(k)
        out.append({"creator": creator, "release": rname, "slug": rslug or slug,
                    "date": date, "ii": None, "estimated": False, "effort": None, "open": None})
    # enrich with any max-effort scores present on the page
    for m in re.finditer(r'"release":\{"slug":"([^"]+)","name":"(?:[^"\\]|\\.)*"\}[^{]*?"intelligenceIndex":([0-9.]+)', u):
        for rec in out:
            if rec["slug"] == m.group(1):
                v = float(m.group(2))
                if rec["ii"] is None or v > rec["ii"]:
                    rec["ii"] = round(v, 1)
    return out, "scrape"

# ---------- diff ----------
EFFORT_SUFFIX = re.compile(
    r"\s*\((?:[^()]*(?:Low|Medium|High|Xhigh|Max|Minimal|Adaptive|Reasoning|Effort|Fallback|Default|Preview|Thinking)[^()]*)\)\s*$",
    re.I)

def base_release(name):
    """'Claude Opus 5.5 (Adaptive Reasoning, Max Effort, Default Fallback)' -> 'Claude Opus 5.5'"""
    n = (name or "").strip()
    for _ in range(3):
        n2 = EFFORT_SUFFIX.sub("", n).strip()
        if n2 == n or not n2:
            break
        n = n2
    return n

def dedupe_variants(rows):
    """The API returns several effort variants per release. Keep the strongest,
    so a release is counted once and score comparisons stay apples-to-apples."""
    best = {}
    for r in rows:
        r["variant"] = r.get("release")
        r["release"] = base_release(r.get("release"))
        key = (r["creator"], r["release"], r.get("date"))
        cur = best.get(key)
        if cur is None:
            best[key] = r
        else:
            a = r.get("ii") if r.get("ii") is not None else -1
            b = cur.get("ii") if cur.get("ii") is not None else -1
            if a > b:
                best[key] = r
    return list(best.values())

def index_by(rows):
    return {f'{r["creator"]}|{r["release"]}|{r["date"]}': r for r in rows if r.get("date")}

def diff(prev, cur):
    p, c = index_by(prev), index_by(cur)
    new = [c[k] for k in c if k not in p]
    removed = [p[k] for k in p if k not in c]
    changed = []
    for k in c:
        if k in p and p[k].get("ii") != c[k].get("ii") and c[k].get("ii") is not None:
            changed.append({"key": k, "was": p[k].get("ii"), "now": c[k].get("ii")})
    return new, removed, changed

def main():
    today = datetime.date.today().isoformat()
    key = api_key()
    if key:
        try:
            rows, src = fetch_api(key)
            log(f"API ok: {len(rows)} tracked model rows")
        except urllib.error.HTTPError as e:
            log(f"API HTTP {e.code} — falling back to page parse")
            rows, src = fetch_scrape()
        except Exception as e:
            log(f"API failed ({type(e).__name__}) — falling back to page parse")
            rows, src = fetch_scrape()
    else:
        log("no AA_API_KEY configured — using page parse fallback")
        rows, src = fetch_scrape()

    if not rows:
        log("ERROR: no rows fetched; leaving state untouched")
        return 1

    before = len(rows)
    rows = dedupe_variants(rows)
    if before != len(rows):
        log(f"collapsed {before} variant rows to {len(rows)} releases")

    snap = {"fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": src, "count": len(rows), "rows": rows}
    base_f = STATE / "baseline.json"
    prev = json.loads(base_f.read_text())["rows"] if base_f.exists() else []
    new, removed, changed = diff(prev, rows)

    if new or removed or changed:
        with open(STATE / "changes.jsonl", "a") as fh:
            fh.write(json.dumps({"at": snap["fetched_utc"], "source": src,
                                 "new": new, "removed": removed, "score_changes": changed}) + "\n")
    base_f.write_text(json.dumps(snap, indent=1))
    log(f"source={src} rows={len(rows)} new={len(new)} removed={len(removed)} score_changes={len(changed)}")
    for n in new[:12]:
        log(f"  NEW  {n['date']}  {n['creator']:10s} {n['release']}")
    for ch in changed[:12]:
        log(f"  SCORE {ch['key']}: {ch['was']} -> {ch['now']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
