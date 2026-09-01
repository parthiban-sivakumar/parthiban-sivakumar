#!/usr/bin/env python3
"""Fetch a user's contribution calendar and normalise it for signal_graph.py.

Tries the GraphQL API first (richer, exact counts). If no token is available or
the call is rejected, falls back to scraping the public contributions fragment
at github.com/users/<login>/contributions, which needs no authentication.

Usage:  fetch_contributions.py <login> <out.json>
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "profile-contribution-signal (+https://github.com/%s)"

QUERY = """
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}
"""

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def _get(url, headers, data=None):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def via_graphql(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    raw = _get("https://api.github.com/graphql",
               {"Authorization": f"bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": UA % login},
               data=body)
    payload = json.loads(raw)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0].get("message", "graphql error"))
    cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    if not cal["weeks"]:
        raise RuntimeError("empty calendar")
    return cal


def via_scrape(login):
    html = _get(f"https://github.com/users/{login}/contributions",
                {"User-Agent": UA % login, "Accept": "text/html",
                 "X-Requested-With": "XMLHttpRequest"})

    # exact counts live in the sr-only tooltips, keyed by cell id
    counts = {}
    for cid, text in re.findall(
            r'<tool-tip[^>]*\bfor="(contribution-day-component-[\d-]+)"[^>]*>'
            r'([^<]*)</tool-tip>', html):
        m = re.match(r'\s*([\d,]+)\s+contribution', text)
        counts[cid] = int(m.group(1).replace(",", "")) if m else 0

    cells = []
    for attrs in re.findall(r'<td\b([^>]*class="[^"]*ContributionCalendar-day[^"]*"[^>]*)>', html):
        date = re.search(r'data-date="([\d-]{10})"', attrs)
        cid = re.search(r'id="(contribution-day-component-[\d-]+)"', attrs)
        if not date:
            continue
        ix = re.search(r'data-ix="(\d+)"', attrs)
        cells.append({
            "date": date.group(1),
            "count": counts.get(cid.group(1), 0) if cid else 0,
            "week": int(ix.group(1)) if ix else 0,
        })
    if not cells:
        raise RuntimeError("could not parse any calendar cells")

    # group into weeks, preserving GitHub's Sunday-first weekday indexing
    buckets = {}
    for c in cells:
        y, m, d = (int(p) for p in c["date"].split("-"))
        import datetime
        weekday = (datetime.date(y, m, d).weekday() + 1) % 7  # Mon=0 -> Sun=0
        buckets.setdefault(c["week"], []).append(
            {"date": c["date"], "contributionCount": c["count"],
             "weekday": weekday})

    weeks = [{"contributionDays": sorted(buckets[k], key=lambda d: d["date"])}
             for k in sorted(buckets)]
    total = sum(d["contributionCount"] for w in weeks
                for d in w["contributionDays"])
    return {"totalContributions": total, "weeks": weeks}


def main():
    login, out = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    cal = None
    if token:
        try:
            cal = via_graphql(login, token)
            print("source: graphql")
        except Exception as exc:            # noqa: BLE001 - fall back on anything
            print(f"graphql unavailable ({exc}); falling back to public page")
    if cal is None:
        cal = via_scrape(login)
        print("source: public contributions page")

    payload = {"login": login,
               "data": {"user": {"contributionsCollection":
                                 {"contributionCalendar": cal}}}}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    print(f"{cal['totalContributions']} contributions, {len(days)} days, "
          f"{sum(1 for d in days if d['contributionCount'] > 0)} active")


if __name__ == "__main__":
    main()
