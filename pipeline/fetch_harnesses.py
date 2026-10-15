#!/usr/bin/env python3
"""
Harness data: adoption, release rhythm and benchmark results for the agent software listed in
build/harnesses.json. Once a day, from public, keyless sources (GITHUB_TOKEN raises the
GitHub rate limit when present):

  npm downloads      api.npmjs.org        daily downloads, summed per week
  PyPI downloads     pypistats.org        daily downloads, summed per week
  GitHub             api.github.com       stars, licence, archived flag, release dates
  VS Code installs   marketplace API      cumulative installs (snapshotted, so deltas show)
  Open VSX           open-vsx.org         cumulative downloads (the registry VSCodium and other forks use)
  Docker Hub         hub.docker.com       cumulative image pulls (self-hosted apps such as AnythingLLM)
  App downloads      api.github.com       download counts of release assets (desktop apps), per release
  OpenRouter         openrouter.ai/apps   tokens per app per day (traffic routed via OpenRouter)
  Terminal-Bench     tbench.ai            the current leaderboard: agent x model x score

npm keeps about 18 months of history and PyPI about 6, so everything is ARCHIVED here: each
run merges into data/harness_stats.json and old weeks are never dropped.
Any source can fail without failing the job; the previous values stay.
"""
import json, os, pathlib, re, sys, time, urllib.request
from collections import defaultdict
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST = ROOT / "build" / "harnesses.json"
OUT = ROOT / "data" / "harness_stats.json"
UA = "artificialacceleration.com data job (+https://artificialacceleration.com)"


def log(msg):
    print(f"harnesses: {msg}", flush=True)


def get(url, data=None, headers=None, timeout=40, limit=12_000_000):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit).decode("utf-8", "ignore")


def week_of(iso):
    d = date.fromisoformat(iso)
    return (d - timedelta(days=d.weekday())).isoformat()       # Monday of that week


def weekly(daily):
    """[(day, n)] -> {monday: sum}, dropping today (npm reports it as 0 while it is in progress)."""
    w = defaultdict(int)
    today = date.today().isoformat()
    for day, n in daily:
        if day < today:
            w[week_of(day)] += n
    return w


def merge_weeks(old, new):
    """Union of archived and fresh weeks; fresh values win (a week fills up as days arrive)."""
    m = {d: n for d, n in old}
    m.update(new)
    return sorted([d, n] for d, n in m.items())


def npm(pkg):
    end = (date.today() - timedelta(days=1)).isoformat()
    start = (date.today() - timedelta(days=540)).isoformat()
    d = json.loads(get(f"https://api.npmjs.org/downloads/range/{start}:{end}/{pkg}"))
    return weekly((x["day"], x["downloads"]) for x in d.get("downloads", []))


def pypi(pkg):
    d = json.loads(get(f"https://pypistats.org/api/packages/{pkg}/overall?mirrors=false"))
    return weekly((x["date"], x["downloads"]) for x in d.get("data", []) if x.get("category") == "without_mirrors")


def github(repo):
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    info = json.loads(get(f"https://api.github.com/repos/{repo}", headers=h))
    rel = None
    if tok:
        # GraphQL returns only the fields asked for; the REST list carries every attached
        # binary (Codex: ~0.3 MB per release, over 100 MB per page), which can fail to arrive whole
        owner, name = repo.split("/", 1)
        q = ('query($o:String!,$n:String!){repository(owner:$o,name:$n){releases(first:100,'
             'orderBy:{field:CREATED_AT,direction:DESC}){nodes{tagName publishedAt isPrerelease isDraft}}}}')
        try:
            d = json.loads(get("https://api.github.com/graphql", headers=h,
                               data=json.dumps({"query": q, "variables": {"o": owner, "n": name}}).encode()))
            rel = [{"tag_name": n["tagName"], "published_at": n["publishedAt"], "prerelease": n["isPrerelease"],
                    "draft": n["isDraft"]} for n in d["data"]["repository"]["releases"]["nodes"]]
        except Exception:
            rel = None
    if rel is None:
        rel = json.loads(get(f"https://api.github.com/repos/{repo}/releases?per_page=100", headers=h,
                             timeout=120, limit=120_000_000))
    stable = [r for r in rel if not r.get("prerelease") and not r.get("draft")]
    return {"stars": info.get("stargazers_count"), "created": (info.get("created_at") or "")[:10],
            "archived": bool(info.get("archived")), "license": (info.get("license") or {}).get("spdx_id"),
            "pushed": (info.get("pushed_at") or "")[:10],
            "releases": sorted((r.get("published_at") or "")[:10] for r in stable if r.get("published_at")),
            "latest": stable[0]["tag_name"] if stable else None}


def vscode(ids):
    body = json.dumps({"filters": [{"criteria": [{"filterType": 7, "value": i} for i in ids], "pageSize": 100}],
                       "flags": 769}).encode()
    d = json.loads(get("https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery", data=body,
                       headers={"Content-Type": "application/json", "Accept": "application/json;api-version=7.2-preview.1"}))
    out = {}
    for ext in d["results"][0]["extensions"]:
        key = f'{ext["publisher"]["publisherName"]}.{ext["extensionName"]}'
        stats = {s["statisticName"]: s["value"] for s in ext.get("statistics", [])}
        out[key.lower()] = int(stats.get("install", 0))
    return out


def openvsx(ident):
    ns, name = ident.split("/", 1)
    return int(json.loads(get(f"https://open-vsx.org/api/{ns}/{name}")).get("downloadCount") or 0)


def docker(repo):
    return int(json.loads(get(f"https://hub.docker.com/v2/repositories/{repo}/")).get("pull_count") or 0)


def release_downloads(repo):
    """{tag: downloads summed over that release's assets} for the latest 30 releases. Kept per
    release, so a week's downloads = the growth of the totals between two snapshots."""
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    if tok:
        owner, name = repo.split("/", 1)
        q = ('query($o:String!,$n:String!){repository(owner:$o,name:$n){releases(first:30,orderBy:{field:CREATED_AT,direction:DESC})'
             '{nodes{tagName releaseAssets(first:100){nodes{downloadCount}}}}}}')
        d = json.loads(get("https://api.github.com/graphql", headers=h,
                           data=json.dumps({"query": q, "variables": {"o": owner, "n": name}}).encode()))
        return {n["tagName"]: sum((a or {}).get("downloadCount") or 0 for a in n["releaseAssets"]["nodes"])
                for n in d["data"]["repository"]["releases"]["nodes"] if n}
    rel = json.loads(get(f"https://api.github.com/repos/{repo}/releases?per_page=30", headers=h,
                         timeout=120, limit=120_000_000))
    return {r["tag_name"]: sum(a.get("download_count", 0) for a in r.get("assets", [])) for r in rel}


def snapshot(store, key, today, value):
    s = store.setdefault(key, [])
    if s and s[-1][0] == today:
        s[-1] = [today, value]
    else:
        s.append([today, value])


def github_candidates():
    """Repositories tagged as agents with 5,000+ stars, created in the last two years: the
    harness watch compares them with our list (new harnesses tend to appear here first)."""
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    since = (date.today() - timedelta(days=730)).isoformat()
    seen = {}
    for topic in ("coding-agent", "ai-agent", "agent-harness", "ai-coding"):
        d = json.loads(get(f"https://api.github.com/search/repositories?q=topic:{topic}+stars:%3E5000+created:%3E{since}"
                           f"&sort=stars&per_page=50", headers=h))
        for r in d.get("items", []):
            seen[r["full_name"]] = {"repo": r["full_name"], "stars": r["stargazers_count"],
                                    "created": r["created_at"][:10], "description": r.get("description") or ""}
    return sorted(seen.values(), key=lambda r: -r["stars"])


def next_flight(html):
    """Next.js pages embed their data as self.__next_f.push([1,"..."]) string chunks."""
    parts = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    return "".join(json.loads('"' + p + '"') for p in parts)


def tbench():
    flight = next_flight(get("https://www.tbench.ai/"))
    i = flight.find('"rows":[')
    rows, _ = json.JSONDecoder().raw_decode(flight[i + 7:])
    title = re.search(r'"title":"(Terminal-Bench [^"]+)"', flight)
    upd = re.search(r'"updated_at":"([^"]+)"', flight)
    label = lambda o: (o or {}).get("label") if isinstance(o, dict) else o
    out = []
    for r in rows:
        md, mt = r.get("metadata", {}), r.get("metrics", {})
        out.append({"rank": r.get("rank"), "agent": (md.get("agent_display") or {}).get("label"), "agent_org": label(md.get("agent_org")),
                    "model": (md.get("model_display") or {}).get("label"), "model_org": label(md.get("model_org")),
                    "effort": md.get("reasoning_effort"), "date": (md.get("date") or "")[:10],
                    "accuracy": mt.get("accuracy"), "ci": mt.get("accuracy_ci95_half_width"),
                    "cost": mt.get("total_cost_usd"), "duration": mt.get("avg_trial_duration_sec")})
    return {"title": title.group(1) if title else "Terminal-Bench", "updated": (upd.group(1) if upd else "")[:10], "rows": out}


def openrouter():
    flight = next_flight(get("https://openrouter.ai/apps"))
    i = flight.find('"globalRankingMap"')
    j = flight.find('"day":[', i)
    day, _ = json.JSONDecoder().raw_decode(flight[j + 6:])
    return [{"title": (a.get("app") or {}).get("title"), "url": (a.get("app") or {}).get("origin_url"),
             "tokens": int(a.get("total_tokens") or 0), "rank": a.get("rank")} for a in day[:60]]


def main(force=False):
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    today = date.today().isoformat()
    if old.get("fetched") == today and not force:
        log("already fetched today")
        return 0
    hs = json.loads(LIST.read_text())["harnesses"]
    st = dict(old)
    st.setdefault("npm", {}); st.setdefault("pypi", {}); st.setdefault("github", {}); st.setdefault("stars", {})
    st.setdefault("vscode", {}); st.setdefault("openrouter_history", {})
    st.setdefault("openvsx", {}); st.setdefault("docker", {}); st.setdefault("app_downloads", {})
    ok = 0
    for h in hs:
        names = lambda v: [v] if isinstance(v, str) else (v or [])      # a harness can have several package names
        for pkg in names(h.get("npm")):
            try:
                st["npm"][pkg] = merge_weeks(st["npm"].get(pkg, []), npm(pkg)); ok += 1
            except Exception as e:
                log(f"npm {pkg}: {type(e).__name__}")
        for pkg in names(h.get("pypi")):
            try:
                st["pypi"][pkg] = merge_weeks(st["pypi"].get(pkg, []), pypi(pkg)); ok += 1
            except Exception as e:
                log(f"pypi {pkg}: {type(e).__name__}")
            time.sleep(1)
        if h.get("repo"):
            try:
                g = github(h["repo"]); st["github"][h["repo"]] = g; ok += 1
                s = st["stars"].setdefault(h["repo"], [])
                if not s or s[-1][0] != today:
                    s.append([today, g["stars"]])
            except Exception as e:
                log(f"github {h['repo']}: {type(e).__name__} {getattr(e, 'code', '')}")
        for key, fn, store in (("openvsx", openvsx, "openvsx"), ("docker", docker, "docker")):
            if h.get(key):
                try:
                    snapshot(st[store], h[key], today, fn(h[key])); ok += 1
                except Exception as e:
                    log(f"{key} {h[key]}: {type(e).__name__}")
        if h.get("app_downloads"):
            try:
                per = release_downloads(h["app_downloads"]); ok += 1
                rec = st["app_downloads"].setdefault(h["app_downloads"], {"releases": {}, "history": []})
                rec["releases"].update(per)                       # old releases keep their last count
                tot = sum(rec["releases"].values())
                if not rec["history"] or rec["history"][-1][0] != today:
                    rec["history"].append([today, tot])
                else:
                    rec["history"][-1] = [today, tot]
            except Exception as e:
                log(f"app downloads {h['app_downloads']}: {type(e).__name__}")
    ids = [h["vscode"] for h in hs if h.get("vscode")]
    try:
        inst = vscode(ids)
        for i in ids:
            v = inst.get(i.lower())
            if v is not None:
                s = st["vscode"].setdefault(i, [])
                if not s or s[-1][0] != today:
                    s.append([today, v])
        ok += 1
    except Exception as e:
        log(f"vscode: {type(e).__name__}")
    try:
        st["github_candidates"] = github_candidates(); ok += 1
    except Exception as e:
        log(f"github candidates: {type(e).__name__}")
    try:
        st["tbench"] = tbench(); ok += 1
    except Exception as e:
        log(f"tbench: {type(e).__name__}")
    try:
        apps = openrouter(); st["openrouter"] = {"date": today, "apps": apps}; ok += 1
        for h in hs:                                   # tokens per day for the harnesses we follow
            names = [n.lower() for n in [h["name"].split(" (")[0]] + h.get("aka", [])]
            hit = next((a for a in apps if a["title"] and a["title"].lower() in names), None) or \
                  next((a for a in apps if a["title"] and any(a["title"].lower().startswith(n) for n in names)), None)
            if hit:
                s = st["openrouter_history"].setdefault(h["id"], [])
                if not s or s[-1][0] != today:
                    s.append([today, hit["tokens"]])
    except Exception as e:
        log(f"openrouter: {type(e).__name__}")
    if ok < 10:
        log(f"only {ok} sources answered; keeping {OUT.name}")
        return 0
    st["fetched"] = today
    OUT.write_text(json.dumps(st, separators=(",", ":")) + "\n")
    log(f"{ok} source reads; tbench rows {len(st.get('tbench', {}).get('rows', []))}, "
        f"openrouter apps {len(st.get('openrouter', {}).get('apps', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
