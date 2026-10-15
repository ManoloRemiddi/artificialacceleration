# How the site's data stays up to date

Three kinds of data, three ways of keeping them fresh. The rule throughout: anything a
public source publishes as a number is fetched by script, never typed; anything that
needs judgement (is this a harness? what does its licence allow?) is proposed by an agent
with a quoted source and approved by a person before it goes live.

## 1. Fully automatic (GitHub Actions, every 6 hours, nobody involved)

| Data | Source | How often it changes | Job |
|---|---|---|---|
| Model releases, scores, prices | Artificial Analysis API | daily | `pipeline/fetch.py` |
| GPU rental prices | GetDeploying open dataset | weekly | `pipeline/fetch_hardware.py` |
| Exchange rates | ECB via frankfurter.dev | daily | `pipeline/fetch_fx.py` |
| Graphics-card prices, 17 countries | GPUPrix | daily | `pipeline/fetch_gpuprix.py` |
| Harness adoption: npm, PyPI, GitHub stars and releases, VS Code installs, Open VSX downloads, Docker pulls, desktop-app downloads | public APIs | daily | `pipeline/fetch_harnesses.py` |
| Harness benchmark (Terminal-Bench) and OpenRouter tokens | tbench.ai, openrouter.ai | daily | `pipeline/fetch_harnesses.py` |
| Licence and archived status of every open repository | GitHub API | daily | `pipeline/fetch_harnesses.py` |

Safety nets already in place: every fetcher keeps the last good file when its source
fails; the run opens one GitHub issue when it breaks and closes it when it recovers; the
page shows a banner once data is 24 hours old.

**Change alerts (built 15 Oct 2026, `pipeline/harness_watch.py`).** The daily job compares what it fetched with what the
page says, and keeps one GitHub issue, "Harness watch", up to date with:
- a licence that changed (e.g. MIT to a source-available licence) or a repository archived;
- a harness that stopped releasing for 90 days, or whose package was deprecated;
- **candidates**: apps entering the OpenRouter top 50, agents new on Terminal-Bench, and
  GitHub repositories tagged as agents that pass 15,000 stars (lists and tutorials skipped), none of which are on
  the list yet. (This is how DeepSeek Harness would have been caught in its first week.)

The issue is a to-do list, not an automatic edit: nothing is added to the site without a review.

## 2. Monthly, by an agent on the maintainer's machine (MiniMax, local fallback)

| Data | Why it needs an agent | Output |
|---|---|---|
| Purchase prices of home-lab and datacenter hardware in five markets | no keyless source publishes them | a pull request with every price quoted from its page |
| Harness facts (pricing, which models it works with, local-model support, telemetry, interfaces) | written on web pages, not in an API | a pull request that changes only facts it can quote, with the quote and the link. **Proposed, not built yet**: the first full check was done by hand-supervised research on 15 Oct 2026 (37 tools, every fact sourced) |

Both run on the systemd timer `aa-price-check.timer` (3rd of each month), which opens pull
requests for review. **Status on 15 Oct 2026: not running.** The key file is in place, but the
timer units are not installed on this machine, so no monthly check has happened yet.

## 3. Editorial (a person decides)

- which harnesses are followed (`build/harnesses.json`), using the "Harness watch" candidates;
- which model releases are "notable" and the labs' statements (`build/labs.json`, `statements.json`);
- approving the monthly pull requests.

Every harness fact carries the date it was last verified (`facts.checked` in `build/harnesses.json`) and its source link, and the page
shows a fact as "unverified" when the check is more than 120 days old, so stale facts are
visible instead of silently wrong.

## What it costs

GitHub Actions: free for public repositories. The monthly agent uses the existing MiniMax
subscription. No paid Claude plan and no logged-in session are needed.
