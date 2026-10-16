# -*- coding: utf-8 -*-
"""site/harnesses/index.html: the harness tracker (the third pillar, next to models and
hardware). Data: build/harnesses.json (editorial list) + data/harness_stats.json (collected
daily by pipeline/fetch_harnesses.py). Everything is computed here; the page only draws.
"""
import json, pathlib
from datetime import date, timedelta

R = pathlib.Path(__file__).resolve().parent.parent

# Terminal-Bench model organisations -> the lab ids used for colour across the site
ORG_LAB = {"anthropic": "anthropic", "openai": "openai", "google": "google", "google deepmind": "google",
           "xai": "xai", "spacexai": "xai", "meta": "meta", "deepseek": "deepseek", "alibaba": "qwen",
           "qwen": "qwen", "moonshot": "kimi", "moonshot ai": "kimi", "kimi": "kimi", "z.ai": "glm", "zhipu": "glm",
           "z ai": "glm"}


def lab_for(org, model):
    if isinstance(org, dict):
        org = org.get("label")
    o = (org or "").lower()
    for k, v in ORG_LAB.items():
        if k in o:
            return v
    m = (model or "").lower()
    for key, lab in (("claude", "anthropic"), ("opus", "anthropic"), ("sonnet", "anthropic"), ("gpt", "openai"),
                     ("gemini", "google"), ("grok", "xai"), ("muse", "meta"), ("deepseek", "deepseek"),
                     ("qwen", "qwen"), ("kimi", "kimi"), ("glm", "glm")):
        if key in m:
            return lab
    return None


def spikes(series):
    """Weeks more than 4x the median of the four weeks either side: a mirror or a bot
    re-downloading a package (Codex showed 130M in one week of April 2026, against ~5M
    before and after), not adoption. Returned so they can be left out and disclosed."""
    out = set()
    vals = [n for _, n in series]
    for i, (wk, n) in enumerate(series):
        around = sorted(vals[max(0, i - 4):i] + vals[i + 1:i + 5])
        if len(around) >= 4:
            med = around[len(around) // 2]
            if med > 1000 and n > 4 * med:
                out.add(wk)
    return out


def payload(as_of):
    hs = json.loads((R / "build" / "harnesses.json").read_text())["harnesses"]
    sp = R / "data" / "harness_stats.json"
    st = json.loads(sp.read_text()) if sp.exists() else {}
    labs = json.loads((R / "build" / "labs.json").read_text())
    this_monday = as_of - timedelta(days=as_of.weekday())
    last_full = (this_monday - timedelta(days=7)).isoformat()   # the latest complete week
    out = []
    for h in hs:
        weeks = {}
        names = lambda v: [v] if isinstance(v, str) else (v or [])
        since = h.get("downloads_since") or ""          # e.g. the npm name "cline" was another package until Oct 2025
        for src in ("npm", "pypi"):
            for pkg in names(h.get(src)):
                for wk, n in st.get(src, {}).get(pkg, []):
                    if since <= wk <= last_full:
                        weeks[wk] = weeks.get(wk, 0) + n
        series = sorted(weeks.items())
        bad = spikes(series)
        series = [(w, n) for w, n in series if w not in bad]
        last = weeks.get(last_full)
        prev = weeks.get((this_monday - timedelta(days=7 * 13)).isoformat())
        growth = ((last - prev) / prev * 100) if last and prev else None
        g = st.get("github", {}).get(h.get("repo") or "", {})
        rel = [d for d in g.get("releases", []) if d >= (as_of - timedelta(days=365)).isoformat()]
        last_rel = g.get("releases", [None])[-1] if g.get("releases") else None
        fstat = (h.get("facts") or {}).get("status") or ""
        status = h.get("status") if h.get("status") in ("discontinued", "archived") else \
            "discontinued" if fstat == "discontinued" else "archived" if g.get("archived") else (
            "dormant" if last_rel and last_rel < (as_of - timedelta(days=180)).isoformat() else "active")
        vs = st.get("vscode", {}).get(h.get("vscode") or "", [])
        ovsx = st.get("openvsx", {}).get(h.get("openvsx") or "", [])
        dock = st.get("docker", {}).get(h.get("docker") or "", [])
        appd = (st.get("app_downloads", {}).get(h.get("app_downloads") or "", {}) or {}).get("history", [])
        facts = h.get("facts") or {}
        f = {"category": facts.get("category") or ("cli-agent" if h["kind"] == "coding" else "general-agent"),
             "source": facts.get("source") or ("open-source" if h["open_source"] else "proprietary"),
             "license": facts.get("license") or g.get("license") or (None if h["open_source"] else "Proprietary"),
             "models": facts.get("models"), "local": facts.get("local_models"), "telemetry": facts.get("telemetry"),
             "interfaces": facts.get("interfaces") or [], "checked": facts.get("checked"),
             "sources": facts.get("sources") or {}, "verified": bool(facts)}
        orh = st.get("openrouter_history", {}).get(h["id"], [])
        out.append({
            "id": h["id"], "name": h["name"], "vendor": h["vendor"], "open": h["open_source"], "kind": h["kind"],
            "launch": h["launch"], "pricing": h["pricing"], "notes": h.get("notes", ""), "repo": h.get("repo"),
            "license": g.get("license"), "status": status,
            "weekly": series, "downloads": last, "growth": growth, "spikes": sorted(bad),
            "dl_source": h.get("dl_note") or ("npm" if h.get("npm") else ("PyPI" if h.get("pypi") else None)),
            "repo_note": h.get("repo_note"), "dl_partial": h.get("downloads_partial"),
            "stars": g.get("stars"),
            "installs": ((vs[-1][1] if vs else 0) + (ovsx[-1][1] if ovsx else 0)) or None,
            "inst_vscode": vs[-1][1] if vs else None, "inst_openvsx": ovsx[-1][1] if ovsx else None,
            "selfhost": ((appd[-1][1] if appd else 0) + (dock[-1][1] if dock else 0)) or None,
            "app_dl": appd[-1][1] if appd else None, "docker_pulls": dock[-1][1] if dock else None, "f": f,
            "or_tokens": orh[-1][1] if orh else None,
            "releases": rel, "r90": sum(1 for d in rel if d >= (as_of - timedelta(days=90)).isoformat()),
            "last_release": last_rel, "latest": g.get("latest"),
        })
    tb = st.get("tbench", {})
    flat = lambda o: o.get("label") if isinstance(o, dict) else o
    rows = [dict(r, agent_org=flat(r.get("agent_org")), model_org=flat(r.get("model_org")),
                 lab=lab_for(r.get("model_org"), r.get("model"))) for r in tb.get("rows", []) if r.get("accuracy") is not None]
    out = [h for h in out if (h["f"].get("category") != "not-a-harness")]
    return {"as_of": as_of.isoformat(), "fetched": st.get("fetched"), "week": last_full,
            "harnesses": out,
            "tbench": {"title": tb.get("title", "Terminal-Bench"), "updated": tb.get("updated"), "rows": rows},
            "openrouter": st.get("openrouter", {}),
            "labs": {L["id"]: {"name": L["name"], "short": L["short"]} for L in labs}}


def lab_css():
    labs = json.loads((R / "build" / "labs.json").read_text())
    dark = ";".join("--lab-%s:%s" % (L["id"], L["hex"]) for L in labs)
    light = ";".join("--lab-%s:%s" % (L["id"], L.get("hex_light", L["hex"])) for L in labs)
    return ":root{%s}[data-theme=\"light\"]{%s}" % (dark, light)


def write(site, as_of=None):
    as_of = as_of or date.today()
    tpl = (R / "build" / "harness_template.html").read_text()
    viz = (R / "build" / "assets" / "viz.js").read_text()
    out = (tpl.replace("/*__LABVARS__*/", lab_css()).replace("/*__VIZJS__*/", viz)
              .replace("__DATA__", json.dumps(payload(as_of), ensure_ascii=False, separators=(",", ":"))))
    d = site / "harnesses"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(out)
    print(f"harness page: {len(json.loads((R / 'build' / 'harnesses.json').read_text())['harnesses'])} harnesses")
