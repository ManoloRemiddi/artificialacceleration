#!/usr/bin/env python3
"""
Store a GitHub token so the agent can read Actions logs and finish the go-live.

Run:  python3 scripts/github_token.py
Input is hidden. Nothing is echoed, logged, or written to shell history.
The value goes into ~/.dsh/secrets.env (mode 600) as GITHUB_TOKEN and is never printed.
"""
import getpass, json, os, pathlib, re, stat, sys, urllib.error, urllib.request

SECRETS = pathlib.Path.home() / ".dsh" / "secrets.env"
NAME = "GITHUB_TOKEN"
API = "https://api.github.com"

def main():
    if not sys.stdin.isatty():
        print("Run this in a real terminal:  python3 scripts/github_token.py")
        return 2
    print("Where to create it:")
    print("  https://github.com/settings/tokens/new")
    print("  Scopes: tick 'repo'  and  'workflow'   (expiry: 7 days is plenty)")
    print()
    tok = getpass.getpass("Paste the token (hidden): ").strip()
    if len(tok) < 20:
        print("That looks too short for a GitHub token. Nothing written.")
        return 1

    req = urllib.request.Request(API + "/user", headers={
        "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
        "User-Agent": "aa-tracker"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            user = json.loads(r.read().decode()).get("login")
        print(f"  token valid, signed in as {user}")
    except urllib.error.HTTPError as e:
        print(f"  GitHub rejected it (HTTP {e.code}). Nothing written.")
        return 1
    except Exception as e:
        print(f"  could not verify ({type(e).__name__}). Nothing written.")
        return 1

    lines = SECRETS.read_text().splitlines() if SECRETS.exists() else []
    out, done = [], False
    for raw in lines:
        if re.match(rf"^\s*(export\s+)?{NAME}\s*=", raw):
            out.append(f"{NAME}={tok}"); done = True
        else:
            out.append(raw)
    if not done:
        if out and out[-1].strip(): out.append("")
        out.append("# GitHub API token (Actions logs + Pages admin)")
        out.append(f"{NAME}={tok}")
    tmp = SECRETS.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(SECRETS)
    os.chmod(SECRETS, stat.S_IRUSR | stat.S_IWUSR)
    print(f"  stored {NAME} in {SECRETS} (mode 600)")
    print("Tell the agent it is ready.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
