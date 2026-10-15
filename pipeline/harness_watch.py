#!/usr/bin/env python3
"""
Harness watch: what changed among the harnesses we follow, and what we are missing.

Reads build/harnesses.json (what the page says) and data/harness_stats.json (what the daily
fetch saw) and writes a Markdown checklist to stdout, or nothing when there is nothing to do.
The workflow keeps one GitHub issue, "Harness watch", set to that text. Nothing here edits
the site: every item is for a person to review.

  changed     licence on GitHub differs from the licence on the page; repository archived;
              no stable release for 90 days
  candidates  apps in the OpenRouter top 50, agents on Terminal-Bench, and GitHub repositories
              tagged as agents with 15,000+ stars (lists and tutorials skipped), that are not on the list and not ignored
"""
import json, pathlib, sys
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST = ROOT / "build" / "harnesses.json"
IGNORE = ROOT / "build" / "harness_watch_ignore.json"
STATS = ROOT / "data" / "harness_stats.json"


def norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def main():
    hs = json.loads(LIST.read_text())["harnesses"]
    st = json.loads(STATS.read_text()) if STATS.exists() else {}
    ign = json.loads(IGNORE.read_text()) if IGNORE.exists() else {"names": [], "repos": []}
    known = set()
    for h in hs:
        for n in [h["name"], h["name"].split(" (")[0], h["id"]] + h.get("aka", []):
            known.add(norm(n))
    known_repos = {(h.get("repo") or "").lower() for h in hs} | {(h.get("app_downloads") or "").lower() for h in hs}
    ignored = {norm(n) for n in ign.get("names", [])}
    ignored_repos = {r.lower() for r in ign.get("repos", [])}
    is_known = lambda name: norm(name) in known or any(norm(name).startswith(k) and len(k) > 3 for k in known)
    today = date.today()

    changed = []
    for h in hs:
        g = st.get("github", {}).get(h.get("repo") or "")
        if not g:
            continue
        page_lic = (h.get("facts") or {}).get("license")
        gh_lic = g.get("license")
        if page_lic and gh_lic and gh_lic not in ("NOASSERTION", "Other") and gh_lic != page_lic:
            changed.append(f"**{h['name']}**: licence on GitHub is now `{gh_lic}`, the page says `{page_lic}` ({h['repo']})")
        if g.get("archived") and h.get("status", "active") not in ("archived", "discontinued"):
            changed.append(f"**{h['name']}**: repository {h['repo']} is archived")
        rel = g.get("releases") or []
        # flag the slide into dormancy once (90-180 days); past 180 the page already shows "dormant"
        if (rel and (today - timedelta(days=180)).isoformat() <= rel[-1] < (today - timedelta(days=90)).isoformat()
                and not h.get("prerelease_only") and not g.get("archived")):
            changed.append(f"**{h['name']}**: no stable release since {rel[-1]}")

    cands = []
    for a in (st.get("openrouter", {}).get("apps") or [])[:50]:
        t = a.get("title") or ""
        if t and not is_known(t) and norm(t) not in ignored:
            cands.append(f"OpenRouter #{a.get('rank')}: **{t}** ({a.get('tokens', 0) / 1e9:.0f}B tokens/day) {a.get('url') or ''}")
    for agent in sorted({r.get("agent") for r in (st.get("tbench", {}).get("rows") or []) if r.get("agent")}):
        if not is_known(agent) and norm(agent) not in ignored:
            cands.append(f"Terminal-Bench agent: **{agent}**")
    noise = ("awesome", "learn", "book", "skills", "tutorial", "guide", "course", "prompts")
    for r in st.get("github_candidates", []):
        if r["stars"] < 15000 or any(w in r["repo"].lower() for w in noise):
            continue
        if r["repo"].lower() not in known_repos and r["repo"].lower() not in ignored_repos and not is_known(r["repo"].split("/")[1]):
            cands.append(f"GitHub: **{r['repo']}** ({r['stars']:,} stars, created {r['created']}) {r.get('description', '')[:90]}")

    if not changed and not cands:
        return 0
    out = ["Kept up to date by the daily refresh job: what changed among the harnesses we follow, and "
           "candidates we do not follow yet. Review each one; to silence a candidate that is not a harness, "
           "add it to `build/harness_watch_ignore.json`. Nothing here changes the site by itself.", ""]
    if changed:
        out += ["### Changed", ""] + [f"- [ ] {c}" for c in changed] + [""]
    if cands:
        out += ["### Candidates", ""] + [f"- [ ] {c}" for c in cands] + [""]
    out.append(f"_Last checked {today.isoformat()}._")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
