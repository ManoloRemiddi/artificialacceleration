# artificialacceleration.com

Frontier-model release and capability tracker. Nine labs, one year, every release
dated — plus the release-cadence and intelligence charts.

**Self-sufficient:** the site rebuilds itself inside GitHub Actions on a schedule.
No home server, no cron on your machine, no manual step.

## How it works

```
Actions (every 6h + manual)            --> pipeline/fetch.py    pulls Artificial Analysis
                                       --> pipeline/diff.py     compares to data/baseline.json
                                       --> build/build_page.py  regenerates index.html
                                       --> git commit + push    GitHub Pages redeploys
```

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

## Layout

| Path | Purpose |
|---|---|
| `.github/workflows/update.yml` | the scheduler |
| `pipeline/fetch.py` | API client + variant grouping |
| `build/dataset.py` | which labs we track, colours, marks |
| `build/build_page.py` | renders `index.html` from the data |
| `data/releases.json` | current grouped dataset (committed) |
| `data/baseline.json` | previous snapshot, for diffing |
| `data/changelog.jsonl` | append-only record of what changed and when |

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
  those two files are yours.
