#!/usr/bin/env python3
"""Render a GitHub contribution calendar as a "signal trace" SVG.

Instead of the usual heatmap of squares, each day is a node whose radius and
colour scale with its contribution count, and every active day is wired to the
next one in chronological order -- producing a single signal path traced across
the year, with a pulse animating along it.

Usage:  signal_graph.py <contributions.json> <out-dir>

The input JSON is the raw response of the GitHub GraphQL contributionCalendar
query (see .github/workflows/contribution-graph.yml).
"""

import json
import sys
from datetime import date

# ---------------------------------------------------------------- geometry --

CELL = 18          # pitch between node centres
PAD_L = 42         # room for weekday labels
PAD_R = 26
PAD_T = 118        # room for the header block
PAD_B = 58         # room for the legend
MONTH_H = 22

THEMES = {
    "dark": {
        "bg": "#0D1117", "panel": "#11161D", "border": "#232B36",
        "text": "#E6EDF3", "muted": "#7D8590", "empty": "#1C2129",
        "trace": "#8E2DE2", "chip": "#161B22",
    },
    "light": {
        "bg": "#FFFFFF", "panel": "#FBFAFD", "border": "#E4E0EC",
        "text": "#1F2328", "muted": "#6E7781", "empty": "#EAE7F0",
        "trace": "#8E2DE2", "chip": "#F3F0F9",
    },
}

# purple -> magenta -> cyan, matching the profile banner
RAMP = ["#3B1E78", "#5B21B6", "#8E2DE2", "#C13BFF", "#22D3EE"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAY_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ------------------------------------------------------------------ levels --

def build_levels(counts):
    """Map counts onto 0-4 using quartiles of the *active* days only.

    A fixed threshold washes out sparse calendars (every active day lands in
    the top bucket); quartiles keep the ramp meaningful whatever the volume.
    """
    active = sorted(c for c in counts if c > 0)
    if not active:
        return lambda c: 0
    def q(f):
        return active[min(len(active) - 1, int(len(active) * f))]
    t1, t2, t3 = q(0.25), q(0.50), q(0.80)

    def level(c):
        if c <= 0:
            return 0
        if c <= t1:
            return 1
        if c <= t2:
            return 2
        if c <= t3:
            return 3
        return 4
    return level


def streaks(days):
    """Return (current, longest) daily streaks, ignoring a quiet today."""
    longest = cur = 0
    for d in days:
        if d["contributionCount"] > 0:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    trailing = 0
    for d in reversed(days):
        if d["contributionCount"] > 0:
            trailing += 1
        elif trailing == 0:
            continue          # today may simply not have happened yet
        else:
            break
    return trailing, longest


# ------------------------------------------------------------------- render --

def render(cal, theme_name, login):
    T = THEMES[theme_name]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]
    level_of = build_levels(counts)

    n_weeks = len(weeks)
    W = PAD_L + n_weeks * CELL + PAD_R
    H = PAD_T + MONTH_H + 7 * CELL + PAD_B

    total = cal["totalContributions"]
    active = sum(1 for c in counts if c > 0)
    peak = max(counts) if counts else 0
    peak_day = days[counts.index(peak)]["date"] if peak else "-"
    cur_streak, max_streak = streaks(days)

    def cx(wi):
        return PAD_L + wi * CELL + CELL / 2

    def cy(wd):
        return PAD_T + MONTH_H + wd * CELL + CELL / 2

    out = []
    A = out.append

    A(f'<svg xmlns="http://www.w3.org/2000/svg" '
      f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" '
      f'viewBox="0 0 {W} {H}" role="img" '
      f'aria-label="Contribution signal trace for {esc(login)}: '
      f'{total} contributions across {active} active days">')

    # ---- defs
    A("<defs>")
    A('<linearGradient id="hdr" x1="0" y1="0" x2="1" y2="0">'
      '<stop offset="0%" stop-color="#8E2DE2"/>'
      '<stop offset="55%" stop-color="#C13BFF"/>'
      '<stop offset="100%" stop-color="#22D3EE"/></linearGradient>')
    A('<linearGradient id="trace" x1="0" y1="0" x2="1" y2="0">'
      '<stop offset="0%" stop-color="#5B21B6"/>'
      '<stop offset="50%" stop-color="#8E2DE2"/>'
      '<stop offset="100%" stop-color="#22D3EE"/></linearGradient>')
    A('<filter id="glow" x="-120%" y="-120%" width="340%" height="340%">'
      '<feGaussianBlur stdDeviation="2.4" result="b"/>'
      '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/>'
      '</feMerge></filter>')
    A('<filter id="softglow" x="-150%" y="-150%" width="400%" height="400%">'
      '<feGaussianBlur stdDeviation="4" result="b"/>'
      '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/>'
      '</feMerge></filter>')
    A("</defs>")

    # ---- panel
    A(f'<rect width="{W}" height="{H}" rx="14" fill="{T["bg"]}"/>')
    A(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" '
      f'fill="{T["panel"]}" stroke="{T["border"]}"/>')
    A(f'<rect x="0" y="0" width="{W}" height="3" rx="1.5" fill="url(#hdr)"/>')

    # ---- header
    fam = ("font-family=\"'Segoe UI',Ubuntu,Helvetica,Arial,sans-serif\"")
    A(f'<text x="{PAD_L-16}" y="46" {fam} font-size="19" font-weight="600" '
      f'fill="{T["text"]}">Contribution Signal</text>')
    A(f'<text x="{PAD_L-16}" y="68" {fam} font-size="12" '
      f'fill="{T["muted"]}">Every active day, wired in sequence \u00b7 '
      f'@{esc(login)}</text>')

    # ---- stat chips (right aligned)
    chips = [("CONTRIBUTIONS", f"{total:,}"), ("ACTIVE DAYS", str(active)),
             ("PEAK DAY", str(peak)), ("LONGEST STREAK", f"{max_streak}d")]
    cw, ch, gap = 118, 46, 10
    x = W - PAD_R - (len(chips) * cw + (len(chips) - 1) * gap)
    for label, value in chips:
        A(f'<rect x="{x}" y="30" width="{cw}" height="{ch}" rx="9" '
          f'fill="{T["chip"]}" stroke="{T["border"]}"/>')
        A(f'<text x="{x+cw/2}" y="48" {fam} font-size="8.5" letter-spacing="0.9" '
          f'text-anchor="middle" fill="{T["muted"]}">{label}</text>')
        A(f'<text x="{x+cw/2}" y="66" {fam} font-size="15" font-weight="600" '
          f'text-anchor="middle" fill="{T["text"]}">{esc(value)}</text>')
        x += cw + gap

    # ---- month labels
    seen = set()
    for wi, wk in enumerate(weeks):
        d0 = wk["contributionDays"][0]["date"]
        y, m, _ = (int(p) for p in d0.split("-"))
        key = (y, m)
        if key in seen:
            continue
        # only label a month once its first full week starts
        if int(d0.split("-")[2]) > 7:
            continue
        seen.add(key)
        A(f'<text x="{cx(wi)-CELL/2}" y="{PAD_T+13}" {fam} font-size="10.5" '
          f'fill="{T["muted"]}">{MONTHS[m-1]}</text>')

    # ---- weekday labels
    for wd, lbl in DAY_LABELS.items():
        A(f'<text x="{PAD_L-12}" y="{cy(wd)+3.5}" {fam} font-size="10" '
          f'text-anchor="end" fill="{T["muted"]}">{lbl}</text>')

    # ---- the trace: connect active days in chronological order
    pts = []
    for wi, wk in enumerate(weeks):
        for d in wk["contributionDays"]:
            if d["contributionCount"] > 0:
                pts.append((cx(wi), cy(d["weekday"])))
    if len(pts) > 1:
        path = "M " + " L ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        A(f'<path id="signal" d="{path}" fill="none" stroke="url(#trace)" '
          f'stroke-width="1.15" stroke-opacity="0.24" '
          f'stroke-linejoin="round" stroke-linecap="round"/>')

    # ---- inactive days: faint dots, so the grid still reads as a calendar
    for wi, wk in enumerate(weeks):
        for d in wk["contributionDays"]:
            if d["contributionCount"] == 0:
                A(f'<circle cx="{cx(wi):.1f}" cy="{cy(d["weekday"]):.1f}" '
                  f'r="1.5" fill="{T["empty"]}"/>')

    # ---- active days: glowing nodes
    radii = {1: 2.8, 2: 3.7, 3: 4.6, 4: 5.6}
    for wi, wk in enumerate(weeks):
        for d in wk["contributionDays"]:
            c = d["contributionCount"]
            if c <= 0:
                continue
            lv = level_of(c)
            col = RAMP[lv]
            r = radii.get(lv, 2.8)
            filt = ' filter="url(#glow)"' if lv >= 3 else ""
            A(f'<circle cx="{cx(wi):.1f}" cy="{cy(d["weekday"]):.1f}" r="{r}" '
              f'fill="{col}"{filt}><title>{d["date"]}: {c} '
              f'contribution{"s" if c != 1 else ""}</title></circle>')

    # ---- pulse travelling along the trace
    if len(pts) > 1:
        dur = max(9, min(26, len(pts) * 0.28))
        A(f'<circle r="4.2" fill="#22D3EE" filter="url(#softglow)" opacity="0.9">'
          f'<animateMotion dur="{dur:.1f}s" repeatCount="indefinite" '
          f'calcMode="linear"><mpath xlink:href="#signal" href="#signal"/>'
          f'</animateMotion>'
          f'<animate attributeName="opacity" values="0;0.95;0.95;0" '
          f'keyTimes="0;0.06;0.94;1" dur="{dur:.1f}s" '
          f'repeatCount="indefinite"/></circle>')

    # ---- legend
    ly = PAD_T + MONTH_H + 7 * CELL + 26
    A(f'<text x="{PAD_L-16}" y="{ly+4}" {fam} font-size="10.5" '
      f'fill="{T["muted"]}">Quiet</text>')
    lx = PAD_L + 26
    A(f'<circle cx="{lx}" cy="{ly}" r="1.5" fill="{T["empty"]}"/>')
    lx += 15
    for lv in (1, 2, 3, 4):
        A(f'<circle cx="{lx}" cy="{ly}" r="{radii[lv]}" fill="{RAMP[lv]}"/>')
        lx += 15
    A(f'<text x="{lx+2}" y="{ly+4}" {fam} font-size="10.5" '
      f'fill="{T["muted"]}">Intense</text>')

    note = esc(f"Peak {peak} on {peak_day}") if peak else "No activity yet"
    if cur_streak:
        note += f" \u00b7 {cur_streak}d current streak"
    A(f'<text x="{W-PAD_R}" y="{ly+4}" {fam} font-size="10.5" '
      f'text-anchor="end" fill="{T["muted"]}">{note}</text>')

    A("</svg>")
    return "\n".join(out)


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    with open(src) as fh:
        payload = json.load(fh)
    user = payload["data"]["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    login = payload.get("login") or "parthiban-sivakumar"
    for theme in ("dark", "light"):
        svg = render(cal, theme, login)
        with open(f"{outdir}/contribution-signal-{theme}.svg", "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"wrote {outdir}/contribution-signal-{theme}.svg ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
