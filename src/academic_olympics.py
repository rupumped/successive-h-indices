#!/usr/bin/env python3
"""
Academic Olympics: each field is a sport, each country competes for medals.

Gold/silver/bronze are awarded to the top three distinct H3 values in each
field. Ties at the same H3 share the same medal (and the next medal is skipped,
as in the real Olympics).

Usage:
  python3 academic_olympics.py
"""

import csv
import os
from collections import defaultdict

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H3_FIELD_DIR = os.path.join(ROOT_DIR, "data", "interim", "h3_by_field")
OUT_PNG = os.path.join(ROOT_DIR, "results", "academic_olympics.png")

# Shared with the other results/*.py plots (references/palette.md).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"

# Medal colors, tuned from the stock gold/silver/bronze hexes to clear the
# contrast check against SURFACE (validate_palette.js). Silver and bronze
# still read below the chroma floor -- that's inherent to the metaphor, not a
# bug -- so counts are always direct-labeled on the bar, never color-alone.
GOLD = "#B8860B"
SILVER = "#71797E"
BRONZE = "#8C4A2F"

COUNTRY_NAMES = {
    "US": "United States", "CN": "China", "GB": "United Kingdom", "DE": "Germany",
    "JP": "Japan", "IT": "Italy", "FR": "France", "ES": "Spain", "KR": "South Korea",
    "AU": "Australia", "SA": "Saudi Arabia", "CA": "Canada", "NL": "Netherlands",
    "CH": "Switzerland", "SE": "Sweden", "BE": "Belgium", "RU": "Russia",
    "IN": "India", "BR": "Brazil", "TW": "Taiwan", "IL": "Israel", "DK": "Denmark",
    "NO": "Norway", "FI": "Finland", "AT": "Austria", "PL": "Poland",
    "PT": "Portugal", "IE": "Ireland", "NZ": "New Zealand", "SG": "Singapore",
    "HK": "Hong Kong", "ZA": "South Africa", "MX": "Mexico", "TR": "Turkey",
    "ID": "Indonesia", "MY": "Malaysia", "TH": "Thailand", "VN": "Vietnam",
    "AR": "Argentina", "CL": "Chile", "CZ": "Czechia", "GR": "Greece",
    "HU": "Hungary", "RO": "Romania", "UA": "Ukraine", "EG": "Egypt",
    "IR": "Iran", "PK": "Pakistan", "NG": "Nigeria",
}


def field_name_from_path(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace('__', ', ').replace('_', ' ')


def award_medals(path):
    """Return {country_code: medal} for the top three distinct H3 tiers."""
    with open(path, newline="") as f:
        rows = [(r["country_code"], int(r["h3"])) for r in csv.DictReader(f)]

    rows.sort(key=lambda x: -x[1])

    medals = {}
    tier = 0
    last_h3 = None
    medal_names = ["gold", "silver", "bronze"]

    for cc, h3 in rows:
        if h3 != last_h3:
            tier += 1
            last_h3 = h3
        if tier > 3:
            break
        medals[cc] = medal_names[tier - 1]

    return medals


def build_medals(paths):
    """Return (medals, tied_golds): medals[cc][medal] = [field, ...], and
    tied_golds[field] = [cc, ...] for fields where >1 country shares gold."""
    medals = defaultdict(lambda: {"gold": [], "silver": [], "bronze": []})
    tied_golds = {}

    for path in paths:
        field = field_name_from_path(path)
        field_medals = award_medals(path)

        golds = [cc for cc, medal in field_medals.items() if medal == "gold"]
        if len(golds) > 1:
            tied_golds[field] = golds

        for cc, medal in field_medals.items():
            medals[cc][medal].append(field)

    return medals, tied_golds


def rank_countries(medals):
    """Sort by gold count desc, then silver, then bronze (IOC ordering)."""
    return sorted(
        medals.items(),
        key=lambda x: (-len(x[1]["gold"]), -len(x[1]["silver"]), -len(x[1]["bronze"]))
    )


def plot_medal_table(ranking, tied_golds, out_path=OUT_PNG, top_n=15):
    """Horizontal stacked bar: one row per country, segments = medal counts."""
    ranking = [(cc, m) for cc, m in ranking if m["gold"] or m["silver"] or m["bronze"]][:top_n]
    if not ranking:
        print("No medal data to plot.")
        return

    countries = [COUNTRY_NAMES.get(cc, cc) for cc, _ in ranking]
    n = len(ranking)
    y = np.arange(n)[::-1]  # rank 1 at the top

    # Fixed-inch header/footer so title+subtitle+legend spacing stays constant
    # regardless of how many countries (n) are plotted -- fractional
    # (axes/figure-relative) coordinates fight each other as n changes.
    header_in = 1.35
    footer_in = 0.35 if tied_golds else 0.15
    row_in = 0.42
    fig_h = row_in * n + header_in + footer_in
    top_frac = (fig_h - header_in) / fig_h
    bottom_frac = footer_in / fig_h

    def y_from_top(inches):
        return 1 - inches / fig_h

    fig, ax = plt.subplots(figsize=(9, fig_h))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    fig.subplots_adjust(left=0.20, right=0.97, top=top_frac, bottom=bottom_frac)

    segments = [
        ("Gold", [len(m["gold"]) for _, m in ranking], GOLD),
        ("Silver", [len(m["silver"]) for _, m in ranking], SILVER),
        ("Bronze", [len(m["bronze"]) for _, m in ranking], BRONZE),
    ]

    left = np.zeros(n)
    for label, counts, color in segments:
        counts = np.array(counts, dtype=float)
        # 2px surface-colored stroke between adjacent segments (marks-and-anatomy.md).
        ax.barh(y, counts, left=left, height=0.68, color=color,
                edgecolor=SURFACE, linewidth=2, label=label)
        for yi, c, l in zip(y, counts, left):
            if c > 0:
                ax.text(l + c / 2, yi, str(int(c)), ha="center", va="center",
                        fontsize=10, fontweight="bold", color="white",
                        path_effects=[pe.withStroke(linewidth=2, foreground=color)])
        left += counts

    ax.set_yticks(y)
    ax.set_yticklabels(countries, fontsize=11, color=INK)
    ax.set_xticks([])
    ax.set_xlim(0, left.max() * 1.08)
    ax.set_ylim(-0.7, n - 0.3)
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.text(0.5, y_from_top(0.42), "Academic Olympics: Medal Table by Country",
              fontsize=16, fontweight="bold", color=INK, ha="center", va="center")
    fig.text(0.5, y_from_top(0.78), "Top-3 H3 rank per field, across 26 academic fields",
              fontsize=10, color=MUTED, ha="center", va="center")

    legend_handles = [Patch(facecolor=color, label=label) for label, _, color in segments]
    fig.legend(handles=legend_handles, loc="center", bbox_to_anchor=(0.5, y_from_top(1.12)),
               ncol=3, frameon=False, fontsize=10, labelcolor=INK,
               handlelength=1.2, handleheight=1.2)

    if tied_golds:
        note = "; ".join(
            f"gold tied in {field} ({', '.join(COUNTRY_NAMES.get(cc, cc) for cc in ccs)})"
            for field, ccs in tied_golds.items()
        )
        fig.text(0.02, footer_in / fig_h * 0.4, f"* {note}", fontsize=8, color=MUTED,
                  ha="left", va="bottom")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(f"Saved chart -> {out_path}")


def main():
    if not os.path.isdir(H3_FIELD_DIR):
        raise SystemExit(f"ERROR: {H3_FIELD_DIR} not found. Run build_country_h3_by_field.py first.")

    paths = sorted(f for f in (
        os.path.join(H3_FIELD_DIR, fn) for fn in os.listdir(H3_FIELD_DIR)
    ) if f.endswith(".csv"))

    medals, tied_golds = build_medals(paths)
    ranking = rank_countries(medals)

    print("=== Academic Olympics ===\n")
    for cc, m in ranking:
        gold, silver, bronze = m["gold"], m["silver"], m["bronze"]

        if not gold and not silver and not bronze:
            continue

        parts = []
        if gold:
            parts.append(f"{len(gold)} gold{'s' if len(gold)>1 else ''} ({', '.join(gold)})")
        if silver:
            parts.append(f"{len(silver)} silver{'s' if len(silver)>1 else ''} ({', '.join(silver)})")
        if bronze:
            parts.append(f"{len(bronze)} bronze{'s' if len(bronze)>1 else ''} ({', '.join(bronze)})")

        print(f"{cc}: {'; '.join(parts)}")

    plot_medal_table(ranking, tied_golds)


if __name__ == "__main__":
    main()
