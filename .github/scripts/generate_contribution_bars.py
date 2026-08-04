#!/usr/bin/env python3
"""
Generate a weekly-aggregated contribution bar chart as an SVG.

Scrapes the public GitHub contribution calendar (no token required),
sums contributions per week (Sunday->Saturday, matching GitHub's own
columns), and renders red (#FF0000) bars on a transparent background.

Usage:
    python generate_contribution_bars.py <github_username> [output.svg]
"""

import sys
import re
import datetime as dt
from collections import defaultdict
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

# ---- Style knobs -----------------------------------------------------------
BAR_COLOR   = "FF0000"   # bar fill
TEXT_COLOR  = "8b949e"   # axis labels / caption (muted grey, readable on light+dark)
GRID_COLOR  = "8b949e"   # baseline
BAR_OPACITY = 1.0
CANVAS_W    = 840
CANVAS_H    = 220
PAD_L       = 8
PAD_R       = 8
PAD_TOP     = 22         # room for the max-value caption
PAD_BOTTOM  = 26         # room for month labels
BAR_GAP     = 2          # px gap between bars
# ---------------------------------------------------------------------------


def fetch_daily_counts(username: str) -> dict[dt.date, int]:
    url = f"https://github.com/users/{username}/contributions"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (contribution-graph-bot)"})
    with urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    # id -> count, parsed from the accessible tool-tip text
    counts_by_id: dict[str, int] = {}
    for tip in soup.select("tool-tip"):
        target = tip.get("for")
        if not target:
            continue
        text = tip.get_text(strip=True)
        if text.lower().startswith("no "):
            counts_by_id[target] = 0
        else:
            m = re.match(r"\s*([\d,]+)", text)
            counts_by_id[target] = int(m.group(1).replace(",", "")) if m else 0

    daily: dict[dt.date, int] = {}
    for cell in soup.select("td.ContributionCalendar-day"):
        date_str = cell.get("data-date")
        cell_id = cell.get("id")
        if not date_str:
            continue
        date = dt.date.fromisoformat(date_str)
        # Prefer the tooltip count; fall back to data-level heuristic if absent
        if cell_id in counts_by_id:
            daily[date] = counts_by_id[cell_id]
        else:
            daily.setdefault(date, 0)
    return daily


def aggregate_by_week(daily: dict[dt.date, int]) -> list[tuple[dt.date, int]]:
    """Group by week starting Sunday, to mirror GitHub's grid columns."""
    weekly: dict[dt.date, int] = defaultdict(int)
    for date, count in daily.items():
        # weekday(): Mon=0..Sun=6 -> shift so the week starts on Sunday
        sunday = date - dt.timedelta(days=(date.weekday() + 1) % 7)
        weekly[sunday] += count
    return sorted(weekly.items())


def render_svg(weeks: list[tuple[dt.date, int]]) -> str:
    if not weeks:
        weeks = [(dt.date.today(), 0)]

    n = len(weeks)
    plot_w = CANVAS_W - PAD_L - PAD_R
    plot_h = CANVAS_H - PAD_TOP - PAD_BOTTOM
    slot = plot_w / n
    bar_w = max(1.0, slot - BAR_GAP)
    max_count = max((c for _, c in weeks), default=0) or 1
    baseline_y = PAD_TOP + plot_h
    total = sum(c for _, c in weeks)

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" '
        f'height="{CANVAS_H}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Segoe UI, Ubuntu, sans-serif" role="img" '
        f'aria-label="Weekly GitHub contributions">'
    )

    # caption: total + peak
    peak = max(c for _, c in weeks)
    parts.append(
        f'<text x="{PAD_L}" y="14" font-size="12" fill="#{TEXT_COLOR}">'
        f'{total} contributions \u00b7 peak {peak}/week</text>'
    )

    # baseline
    parts.append(
        f'<line x1="{PAD_L}" y1="{baseline_y:.1f}" x2="{CANVAS_W - PAD_R}" '
        f'y2="{baseline_y:.1f}" stroke="#{GRID_COLOR}" stroke-width="1" '
        f'stroke-opacity="0.35"/>'
    )

    # bars + month labels
    seen_months: set[str] = set()
    for i, (week_start, count) in enumerate(weeks):
        x = PAD_L + i * slot
        h = (count / max_count) * plot_h
        y = baseline_y - h
        if count > 0:
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" '
                f'height="{h:.2f}" rx="1" fill="#{BAR_COLOR}" '
                f'fill-opacity="{BAR_OPACITY}"><title>Week of '
                f'{week_start.isoformat()}: {count}</title></rect>'
            )
        # one month tick per new month
        label = week_start.strftime("%b")
        key = week_start.strftime("%Y-%m")
        if key not in seen_months and week_start.day <= 7:
            seen_months.add(key)
            parts.append(
                f'<text x="{x:.2f}" y="{CANVAS_H - 8}" font-size="10" '
                f'fill="#{TEXT_COLOR}">{label}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: generate_contribution_bars.py <username> [output.svg]")
    username = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "weekly-contributions.svg"

    daily = fetch_daily_counts(username)
    weeks = aggregate_by_week(daily)
    svg = render_svg(weeks)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {out_path}: {len(weeks)} weeks, "
          f"{sum(c for _, c in weeks)} total contributions.")


if __name__ == "__main__":
    main()