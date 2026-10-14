#!/usr/bin/env bash
# Monthly hardware price check, run on this machine by a systemd user timer
# (ops/systemd/aa-price-check.timer). No GitHub secret, no login session needed.
#
#   1. clones the repo fresh into a temp dir (your working copy is never touched)
#   2. runs pipeline/price_agent.py with MiniMax; if MiniMax is unreachable, with the
#      local llama.cpp model and SearXNG instead
#   3. if any price changed, pushes a prices/YYYY-MM branch and opens a pull request
#      from your own GitHub account; you review and merge
#   4. on failure: a GitHub issue and a desktop notification
#
# The MiniMax key stays on this machine, in (chmod 600):
#   ~/.config/artificialacceleration/price-agent.env   ->   MINIMAX_API_KEY=sk-cp-...
# Optional in the same file: LLM_MODEL, MINIMAX_API_HOST, LOCAL_LLM_URL, SEARXNG_URL.
#
# DRY_RUN=1 runs the check and prints the report, but pushes and opens nothing.
set -uo pipefail

REPO="ManoloRemiddi/artificialacceleration"
ENV_FILE="${PRICE_AGENT_ENV:-$HOME/.config/artificialacceleration/price-agent.env}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi
LOCAL_LLM_URL="${LOCAL_LLM_URL:-http://127.0.0.1:8080/v1}"
SEARXNG_URL="${SEARXNG_URL:-http://127.0.0.1:8888}"
MONTH="$(date +%Y-%m)"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
report="$work/price-report.md"

say() { echo "[$(date +%H:%M:%S)] $*"; }
notify() {
  say "$1: $2"
  command -v notify-send >/dev/null 2>&1 && notify-send -a "Artificial Acceleration" "$1" "$2" 2>/dev/null || true
}
fail() {
  notify "Price check failed" "$1"
  [ -n "${DRY_RUN:-}" ] && exit 1
  gh issue create --repo "$REPO" --title "Monthly price check failed $MONTH" \
    --body "The local price check on $(hostname) could not finish: $1. Purchase prices stay as they are; the page flags them as due for re-check after 45 days. Logs: \`journalctl --user -u aa-price-check\`." \
    >/dev/null 2>&1 || true
  exit 1
}
# git over HTTPS with the GitHub CLI's stored token: works with no agent or desktop session
gitgh() { git -c credential.helper= -c "credential.helper=!gh auth git-credential" "$@"; }

say "cloning $REPO"
# PRICE_CHECK_SOURCE lets a test run clone a local checkout instead of GitHub
gitgh clone -q --depth 1 "${PRICE_CHECK_SOURCE:-https://github.com/$REPO.git}" "$work/repo" || fail "could not clone the repository"
cd "$work/repo" || fail "clone vanished"

ran=""
if [ -n "${MINIMAX_API_KEY:-}" ]; then
  say "checking with MiniMax (${LLM_MODEL:-MiniMax-M3.1-Flash-Preview})"
  if REPORT_PATH="$report" python3 pipeline/price_agent.py; then
    ran="MiniMax"
  else
    say "MiniMax run did not complete; trying the local model"
  fi
else
  say "no MINIMAX_API_KEY in $ENV_FILE; trying the local model"
fi

if [ -z "$ran" ]; then
  if curl -sf -m 5 "$LOCAL_LLM_URL/models" >/dev/null && curl -sf -m 5 "$SEARXNG_URL/" >/dev/null; then
    git checkout -q -- build/hardware.json build/price_sources.json
    say "checking with the local model at $LOCAL_LLM_URL and SearXNG"
    if LLM_BASE_URL="$LOCAL_LLM_URL" LLM_API_KEY=local LLM_MODEL=local \
       SEARCH_BACKEND=searxng SEARXNG_URL="$SEARXNG_URL" \
       LLM_EXTRA_BODY='{"chat_template_kwargs": {"enable_thinking": false}}' \
       REPORT_PATH="$report" python3 pipeline/price_agent.py; then
      ran="local model"
    fi
  else
    say "local model or SearXNG not reachable"
  fi
fi
[ -n "$ran" ] || fail "neither MiniMax nor the local model could run the check"

if git diff --quiet -- build/hardware.json build/price_sources.json; then
  notify "Price check done ($ran)" "No verified price changes this month."
  [ -f "$report" ] && cat "$report"
  exit 0
fi

if [ -n "${DRY_RUN:-}" ]; then
  say "DRY_RUN: would push prices/$MONTH and open a pull request with this report:"
  cat "$report"
  git --no-pager diff --stat -- build/hardware.json build/price_sources.json
  exit 0
fi

branch="prices/$MONTH"
git checkout -q -B "$branch"
git -c user.name="acceleration-bot" -c user.email="bot@users.noreply.github.com" \
  commit -q -m "prices: monthly check $(date +%F) ($ran)" -- build/hardware.json build/price_sources.json || fail "could not commit"
gitgh push -q -f origin "$branch" || fail "could not push $branch"

if gh pr view "$branch" --repo "$REPO" --json state -q .state 2>/dev/null | grep -q OPEN; then
  gh pr edit "$branch" --repo "$REPO" --body-file "$report" >/dev/null || fail "could not update the pull request"
  url="$(gh pr view "$branch" --repo "$REPO" --json url -q .url)"
else
  url="$(gh pr create --repo "$REPO" --head "$branch" --base main \
          --title "Monthly price check $MONTH" --body-file "$report")" || fail "could not open the pull request"
fi
notify "Price check ready ($ran)" "Review and merge: $url"
