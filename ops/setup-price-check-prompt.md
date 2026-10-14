# Task: switch on the monthly hardware-price check for artificialacceleration.com

You are working on my Linux desktop, as my user, in a terminal. Please do everything below
yourself, step by step, check each step worked, and only stop to ask me if something fails
in a way these instructions do not cover. I am not technical: explain results to me in
plain words at the end, not in jargon.

## Background (what this is)

- Project folder: `/home/manolo/AI-Projects/artificialacceleration` (a git repository for
  the website artificialacceleration.com, hosted on GitHub as
  `ManoloRemiddi/artificialacceleration`).
- Everything is already written and committed locally. Your job is only to set it up and
  switch it on. Do NOT edit any code in the project.
- What it does: once a month a script (`scripts/price_check_local.sh`) asks an AI model
  (MiniMax) to look up current prices of AI hardware, double-checks every price against
  the web page it came from, and opens a pull request on GitHub for me to approve. If
  MiniMax does not work it falls back to my local model (llama.cpp on port 8080) and my
  local search engine (SearXNG on port 8888), which are already running.
- I will give you my MiniMax API key (it starts with `sk-cp-`). It is a subscription key.

## Rules about the key (very important)

- Never print the key, never echo it, never show it in your output or logs, never put it
  in any file inside the project folder, never commit or push it, never send it anywhere
  except to MiniMax's API (`https://api.minimax.io`).
- The only place it may be stored is the file
  `~/.config/artificialacceleration/price-agent.env`, readable only by me (permissions 600).
- When you need it in a command, read it from that file (for example with
  `set -a; . ~/.config/artificialacceleration/price-agent.env; set +a`), never type it inline.

## Steps

### 1. Store the key safely
Create the folder `~/.config/artificialacceleration` if missing, write the file
`~/.config/artificialacceleration/price-agent.env` with exactly one line:

    MINIMAX_API_KEY=<the key I gave you>

Then run `chmod 600` on it. Check: `ls -l` shows `-rw-------`, and the file is NOT inside
the project folder.

### 2. Check the key actually works with MiniMax (without showing it)
Load the key from the file, then:

a) Chat model test. It should return HTTP 200 and a short answer:

    curl -s -o /tmp/mm-chat.json -w '%{http_code}\n' https://api.minimax.io/v1/chat/completions \
      -H "Authorization: Bearer $MINIMAX_API_KEY" -H "Content-Type: application/json" \
      -d '{"model":"MiniMax-M3.1-Flash-Preview","messages":[{"role":"user","content":"Reply with the word ok"}],"max_completion_tokens":800,"reasoning_split":true}'

b) Search test. It should return HTTP 200, and the JSON should contain `"organic"` results
   and `base_resp.status_code` 0:

    curl -s -o /tmp/mm-search.json -w '%{http_code}\n' https://api.minimax.io/v1/coding_plan/search \
      -H "Authorization: Bearer $MINIMAX_API_KEY" -H "Content-Type: application/json" \
      -d '{"q":"RTX 5090 price"}'

Look inside the two JSON files to judge success, then delete them
(`rm /tmp/mm-chat.json /tmp/mm-search.json`).

If either fails:
- "invalid api key" or status 1004: the key may be from MiniMax's China site. Retry both
  tests with `https://api.minimaxi.com` instead of `https://api.minimax.io`. If that
  works, add a second line to the env file: `MINIMAX_API_HOST=https://api.minimaxi.com`.
- Model not available: try `MiniMax-M3` instead. If that works, add the line
  `LLM_MODEL=MiniMax-M3` to the env file.
- Still failing: stop and tell me the HTTP code and the error message (not the key).

### 3. Push the project's latest commits to GitHub
In the project folder:

    cd /home/manolo/AI-Projects/artificialacceleration
    git status --short        # only an untracked .claude/ folder is expected; leave it alone
    git pull --rebase origin main
    git push origin main

If the pull reports conflicts, run `git rebase --abort` and stop and tell me. Do not force-push.
Pushing triggers the website's own automatic rebuild on GitHub. That is expected and fine.

### 4. Dry run (checks everything, changes nothing online)

    DRY_RUN=1 /home/manolo/AI-Projects/artificialacceleration/scripts/price_check_local.sh

It takes a few minutes. Success looks like a line saying "checking with MiniMax", then
one line per item, then a table titled "Monthly price check". If it says it fell back to
the local model, MiniMax did not work: look at the messages above that line, fix per
step 2, and run the dry run again.

### 5. Switch on the monthly timer

    cp /home/manolo/AI-Projects/artificialacceleration/ops/systemd/aa-price-check.service ~/.config/systemd/user/
    cp /home/manolo/AI-Projects/artificialacceleration/ops/systemd/aa-price-check.timer   ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now aa-price-check.timer
    systemctl --user list-timers aa-price-check.timer

The last command must show the timer with a next run on the 3rd of next month at about 09:23.
Also confirm `loginctl show-user "$USER" -p Linger` says `Linger=yes` (it already should;
that is what lets it run without me being logged in). Do not change any other services.

### 6. First real run now (opens a pull request on GitHub for me to review)

    systemctl --user start aa-price-check.service
    journalctl --user -u aa-price-check -n 60 --no-pager

The log should end with "Price check ready" and a GitHub pull-request link, or "Price
check done: No verified price changes this month". Either is a success.

## What to tell me at the end (in plain words)

1. Whether MiniMax worked, or whether it had to use my local model.
2. The link to the pull request, if one was opened, and a one-line summary of what it
   proposes. Tell me it is waiting for me to approve ("merge") on GitHub, and that nothing
   on the website changes until I do.
3. The date of the next automatic check.
4. Confirm the key is stored only in `~/.config/artificialacceleration/price-agent.env`
   with permissions 600, and nowhere else.

If anything went wrong, tell me what happened and what you think I should do, in plain words.
