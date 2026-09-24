# -*- coding: utf-8 -*-
"""Bottom sections: the Sept cluster, per-lab streams, the evidence ledger.
Generated from the same dataset as the charts so nothing drifts."""

# ---- the 21-22 Sep cluster: three labs, three launches ----
ZSTART, ZHOURS = "2026-09-21T00:00:00Z", 48
CLUSTER = [
 dict(lab="xai", name="Grok 4.7", h=10, dir="up",       w=176, ox=-40,
      time="21 Sep · announced",
      note="Musk's promised three-week turnaround, delivered on time. $2/$6, 500K context."),
 dict(lab="anthropic", name="Claude Opus 5.5", h=28, dir="down", w=180, ox=86,
      time="22 Sep · morning",
      note="Fable-5.1 capability at 40% lower running cost. First of the Claude 5.5 family."),
 dict(lab="openai", name="GPT-6 Sol + Luna", h=29.5, dir="up", w=184, ox=-16, shift=1,
      time="22 Sep · 90 min later",
      note="Half of GPT-5.6 pricing, Astra-level reliability, and no Terra tier this generation."),
]

# ---- the deceleration ledger: what was said, and what shipped next ----
EVIDENCE = [
 dict(colour="anthropic", title="The strongest receipt", quotes=[
   ("Anthropic floats a worldwide <b>“temporary pause”</b> on AI development and says it will convene policymakers.",
    "5 June 2026 · Quartz / The Guardian"),
   ("Anthropic releases <b>Claude Fable 5 and Mythos 5</b> — a new tier above Opus, adding 1M context and a 2.1× jump on Terminal-Bench-Science within three months.",
    "9 June 2026 · four days later"),
 ], foot="Four days between proposing the brake and shipping the jump. Same company, same week."),
 dict(colour="openai", title="Slowing down, on a schedule", quotes=[
   ("OpenAI says it will <b>“slow down development on Astra”</b> to scale up security and testing first.",
    "7 August 2026 · Axios"),
   ("Astra ships as <b>GPT-6</b>, followed 19 days later by Sol and Luna.",
    "3 September 2026 · 22 September 2026"),
 ], foot="The delay was real. It lasted weeks, not quarters — and the stream behind it never stopped."),
 dict(colour="xai", title="Acceleration, announced in advance", quotes=[
   ("Musk promises Grok 4.7 <b>“within a minimum of 3 weeks”</b> of 4.6 — and xAI's roadmap lists seven models in training, with Grok 5 at <b>10 trillion parameters</b>.",
    "12 August 2026 · Wikipedia / roadmap coverage"),
 ], foot="A schedule, not a hedge. 4.7 landed on 21 September — 40 days later."),
 dict(colour="meta", title="The control group", paras=[
   "Meta ran the slowest lane on the board — roughly 41 days between Muse releases — shipped open weights, and did not join the slowdown chorus.",
   "It is also the lane the frontier treats as least threatening. Pacing correlates with being overtaken, not with safety.",
   "<b>If deceleration were the goal, this is what it would look like. Nobody is copying it.</b>",
 ]),
 dict(colour="google", title="The Chinese labs closed the gap", paras=[
   "On the Artificial Analysis index, <b>Qwen3.8 Max (45.4)</b>, <b>GLM-5.3 (44.8)</b> and <b>Kimi K3 (43.6)</b> now sit within four points of GPT-6 Sol (47.5) — and above Claude Sonnet 5, GPT-6 Luna and Grok 4.5.",
   "Three of the four are open-weight. The frontier is being commoditised from below while the top-end labs argue about pacing.",
 ]),
]

INSTITUTIONAL = [
 ("US pre-release review", "GPT-5.6 Sol previewed to trusted partners under a government process, 26 June 2026."),
 ("Export controls", "Fable 5 and Mythos 5 suspended for foreign nationals 12 June 2026, redeployed 1 July."),
 ("Trusted-access programmes", "Project Glasswing, Cyber Verification, Life Sciences Verification."),
 ("Purpose-built safety-gated models", "GPT-5.6 Cyber / Daybreak Red &amp; Blue, 7 August 2026."),
]

METHOD = [
 "<b>Unit of analysis:</b> releases per lab, not per model family. Counting Opus 5 → Opus 5.5 hides Fable 5.1, Sonnet 5 and Opus 5 in between.",
 "<b>Dates</b> come from the Artificial Analysis model ledger plus lab announcements, cross-checked against each other.",
 "<b>Scores</b> are the Artificial Analysis Intelligence Index v4.3.2 at that model's max-effort variant; historical values were re-measured on the current index and the estimated ones are flagged as (est.).",
 "<b>Confirmed:</b> GPT-6 Terra does not exist — the GPT-6 line is Astra, Sol and Luna only.",
 "<b>Changed by this data:</b> Muse Spark 1.3 (2 Sep) and Grok 4.3 (30 Apr) were missing from the first pass of this page.",
 "<b>Announced but undated:</b> Claude Sonnet 5.5 and Haiku 5.5 — “in the coming weeks” as of 22 September.",
]
