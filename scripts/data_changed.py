#!/usr/bin/env python3
"""Has the tracker's data actually changed?

Compares the *releases* in a previous snapshot against the working copy, so
timestamps that move on every run (generated_utc) cannot masquerade as news.
Prints "true" or "false" on stdout, which is what the workflow feeds to
$GITHUB_OUTPUT. Exit status is always 0 unless the files cannot be read.

    python3 scripts/data_changed.py /tmp/prev.json
"""
import json
import os
import sys


def rows(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("rows", [])
    except (OSError, ValueError):
        return []


def key(r):
    """The identity of a release. A re-scored index counts as a change."""
    return (r.get("lab"), r.get("release"), r.get("date"), r.get("ii"))


def main():
    prev_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not prev_path or not os.path.exists(prev_path):
        print("true")          # nothing to compare against: treat as new
        return
    before = {key(r) for r in rows(prev_path)}
    after = {key(r) for r in rows("data/releases.json")}
    if before == after:
        print("false")
        return
    added, dropped = after - before, before - after
    for lab, release, date, ii in sorted(added, key=lambda k: k[2] or ""):
        print(f"  + {date} {lab} {release} ({ii})", file=sys.stderr)
    for lab, release, date, ii in sorted(dropped, key=lambda k: k[2] or ""):
        print(f"  - {date} {lab} {release} ({ii})", file=sys.stderr)
    print("true")


if __name__ == "__main__":
    main()
