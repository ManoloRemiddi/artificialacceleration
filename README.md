# artificialacceleration.com

Frontier-model release and capability tracker. Nine labs, one year, every release
dated — plus the release-cadence and intelligence charts.

**Self-sufficient:** the site rebuilds itself inside GitHub Actions on a schedule.
No home server, no cron on your machine, no manual step.

## How it works

```
Actions (every 6h + manual)  --> pipeline/fetch.py           pulls Artificial Analysis (models, scores, prices)
                             --> scripts/build_data.py       one row per release: lab, region, open weights, notable
                             --> pipeline/fetch_hardware.py  GPU rental prices (GetDeploying, CC BY 4.0, weekly)
                             --> build/build_page.py         index.html + release pages, feed, sitemap, badge, embed, og.png
                             --> git commit + push           only when releases or rental prices changed
                             --> deploy-pages                always, so the page's "now" moves forward
```

If a run fails, the job opens one GitHub issue ("Refresh job failing") and comments on it
for each further failure; the next good run closes it. The page itself shows a banner
once its data is more than 24 hours old (normally it is at most ~9: runs every 6 hours,
plus GitHub's scheduling delay), which also covers GitHub pausing the schedule entirely.

A commit only happens when the data actually changed, so the history doubles as the
changelog and idle checks cost nothing.

## Data

Artificial Analysis Data API, `GET /api/v2/data/llms/models`, key in `x-api-key`.
Free tier (1,000 requests/day). Key lives in the repo secret `AA_API_KEY` and is never
written to any committed file. Snapshot rows are normalised to one entry per release
(effort variants collapsed to the strongest).

Data by [Artificial Analysis](https://artificialanalysis.ai) — attribution required and
displayed on the page.

## Presentation

- **Brand** — titled *Artificial Acceleration*.
- **Themes** — dark by default, with a Dark/Light switch that remembers the choice.
- **Logos** — real brand marks fetched from the provider assets on artificialanalysis.ai,
  background tiles stripped so they are transparent, and single-colour marks set to
  `currentColor` so they stay legible whichever theme is active.
- **Naming** — companies on the lane labels (OpenAI, Anthropic, Google, xAI, Meta,
  DeepSeek, Alibaba, Moonshot, Z.ai) with the model family named underneath.

## Visual design notes

Applied from 2026 data-visualisation guidance:

- **Highlight-and-context** — with nine labs, a chart of all nine at once is unreadable
  (guidance: 1-3 lines ideal, 4-5 the maximum, 6+ becomes spaghetti). Hovering a lab — chip
  or lane — keeps that lab at full strength and fades the rest to 14%, in both the timeline
  and the charts. The dimmed series stay as context rather than disappearing.
- **Clean markers** — flat colour, 1.5px ring, no glow. Sizes encode hierarchy: releases
  with an index score are larger and ringed.
- **Cadence rails** — a hairline per lane connecting a lab's first and last release, so the
  rhythm between launches reads at a glance.
- **Motion with a job** — 140-160ms for hover and focus; charts animate on load (bars grow,
  lines draw) to signal that data changed. `prefers-reduced-motion` is honoured.
- **Typography** — larger body and label sizes, muted greys lightened for contrast.

## Layout

| Path | Purpose |
|---|---|
| `.github/workflows/update.yml` | the scheduler, failure issue, deploy |
| `pipeline/fetch.py` | API client + variant grouping |
| `pipeline/fetch_hardware.py` | GPU rental prices → `data/gpu_rental.json` |
| `scripts/build_data.py` | release rows, notable rule, region and open-weight rule |
| `build/labs.json` | labs, colours (dark + light), region, open-weight rule, notable names |
| `build/statements.json` | dated "we will slow down" statements (edit by hand; the rest is counted) |
| `build/hardware.json` | hand-checked purchase prices, one source per number, re-check monthly |
| `build/build_page.py` | renders `index.html` and the sections |
| `build/extras.py` | release pages (`/m/<slug>/`), Atom feed, sitemap, badge, embed widget, social card |
| `build/hardware_section.py` | section 04 on the main page: a summary of the hardware costs |
| `build/hardware_page.py`, `build/hardware_template.html` | the full hardware tracker at `/hardware/`: every vendor, five markets, datacenter parts |
| `build/hwdata.py` | the hardware data model (v2) and conversion to dollars at each price's own date |
| `pipeline/fetch_fx.py` | weekly exchange rates (ECB via frankfurter.dev) → `data/fx.json` |
| `data/releases.json` | current grouped dataset (committed) |
| `data/baseline.json` | previous snapshot, for diffing |
| `data/changes.jsonl` | append-only record of what changed and when |

### The monthly price agent

`build/hardware.json` (v2) holds home-lab products with dated price points in five markets
(US, Euro area, UK, China, Japan) and datacenter accelerators across vendors and countries,
each number with a source. These are prices no keyless source publishes. On the 3rd of
each month a systemd user timer on the maintainer's machine runs
`scripts/price_check_local.sh`, which:

1. clones the repo fresh into a temp dir (the working copy is never touched);
2. runs `pipeline/price_agent.py`, which goes **first to the price-monitoring pages registered
   in `build/price_sources.json`** for each product and market: gpuprix (US, Germany, UK,
   Japan), VideoCardPrices (US), Scan (UK), kakaku (Japan), nvidia.cn and ZOL (China),
   everymac (Apple's official prices in every country), the official Framework stores, and
   AMCompute / IntuitionLabs for datacenter parts. Only when no registered page yields a
   verified price does it search, restricted to that market's monitor sites, and any page
   that works is added to the registry so next month goes straight there. Every fetch honours
   the site's robots.txt: geizhals, idealo, ComputerBase, PriceSpy and bestvaluegpu forbid
   automated access and are never used;
3. asks a model for the current price **and the exact sentence that states it**, and accepts
   it only if, in code, that sentence is on the cited page, contains the number and shows
   the expected currency (a store that switches currency by visitor location cannot slip a
   euro price in as dollars); moves beyond ±30% in a month are held for a human;
4. opens a pull request from the maintainer's GitHub account with an evidence table (and any
   newly registered pages). Nothing is published until it is merged.

The model is MiniMax (`MiniMax-M3.1-Flash-Preview`, included in Token Plan / M Plan
subscription keys, with MiniMax's web search). If MiniMax is unreachable it falls back to
the local llama.cpp model and SearXNG. The key stays on the machine, never on GitHub:

    ~/.config/artificialacceleration/price-agent.env   (chmod 600)
    MINIMAX_API_KEY=sk-cp-...

Install once (the machine has lingering enabled, so it runs without anyone logged in):

    cp ops/systemd/aa-price-check.{service,timer} ~/.config/systemd/user/
    systemctl --user daemon-reload && systemctl --user enable --now aa-price-check.timer

Useful: `systemctl --user list-timers aa-price-check.timer` (next run),
`systemctl --user start aa-price-check.service` (run now),
`journalctl --user -u aa-price-check` (logs), `DRY_RUN=1 scripts/price_check_local.sh`
(check without pushing). The timer is `Persistent`: if the machine is off on the 3rd, the
check runs at the next boot.

If a run fails it opens a GitHub issue and shows a desktop notification, and the page
flags the purchase prices as due for re-check once they are over 45 days old, so they can
never go stale silently. `.github/workflows/prices.yml` is a manual cloud alternative
(needs a `MINIMAX_API_KEY` repository secret).

### What is automatic and what is editorial

Automatic: releases, scores, prices, the notable rule after 24 Sep 2026, every chart,
"who's due", the said-then-shipped counts, GPU rental prices, the Acceleration Index.
Editorial (yours): `labs.json` notable names and open-weight rules (the API publishes no
licences), `statements.json`, `notes.json`, `sections.py` text, and approving the monthly
`hardware.json` price proposals.

---

## One-time setup (about 5 minutes)

1. **Create the repo** — e.g. `artificialacceleration` (public, so Pages is free).
2. **Push this folder** as the repo root:
   ```
   cd ~/Desktop/artificialacceleration
   git init -b main
   git add .
   git commit -m "initial: frontier release tracker"
   git remote add origin git@github.com:<you>/artificialacceleration.git
   git push -u origin main
   ```
3. **Add the API key** — repo → *Settings → Secrets and variables → Actions →
   New repository secret*: name `AA_API_KEY`, value = your Artificial Analysis key.
   It lives in Actions secrets only and is never written to any committed file.
4. **Enable Pages** — *Settings → Pages → Source* = **GitHub Actions**.
5. **Run it once** — *Actions → update-tracker → Run workflow*. It commits data and
   publishes. First publish can take a minute.

## Point the domain at it

*Settings → Pages → Custom domain* → `artificialacceleration.com` → Save.
Then at your registrar add:

| Type | Name | Value |
|---|---|---|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| CNAME | `www` | `<you>.github.io` |

Wait for the DNS check to pass, then tick **Enforce HTTPS**.
(The A records commit a `CNAME` file to the repo automatically.)

## Day-to-day

Nothing. Every 6 hours Actions fetches, rebuilds and — **only if something changed** —
commits and republishes. On a quiet cycle it exits without a commit, so the history stays
readable and you can scroll it to see exactly when each model landed.

To force a refresh: *Actions → update-tracker → Run workflow*.

## Notes and limits

- **Polling, not webhooks.** Artificial Analysis publishes a read-only API with no
  webhook/notification channel, so "instant" here means "within the schedule". Change
  `cron` to `0 * * * *` for hourly. GitHub can delay scheduled runs at peak times.
- **Rate limit** is 1,000 requests/day per key; this design uses ~4/day.
- **Scores move.** The index is versioned (currently v4.3.2). When Artificial Analysis
  re-runs a model the score changes and this page will pick the change up automatically.
- **Editorial vs data.** `build/labs.json` decides which labs and which releases are
  "notable"; `build/notes.json` holds the hand-written lines. Data is automatic;
  those two files are yours. Releases after the lists were compiled (24 Sep 2026) are
  judged by rule in `scripts/build_data.py`: within 3 index points of that lab's best
  so far and not named like a variant (Codex, mini, Flash-Lite, 27B...). Add a name to
  a lab's `notable` list to force one in, or to `not_notable` to keep one out.
- **The page's "now"** is the moment the data was fetched, so every axis ends at the
  latest run and the header's "data as of" date shows when that was.
