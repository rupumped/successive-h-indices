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

H3_FIELD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h3_by_field")


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


def main():
    if not os.path.isdir(H3_FIELD_DIR):
        raise SystemExit(f"ERROR: {H3_FIELD_DIR} not found. Run build_country_h3_by_field.py first.")

    paths = sorted(f for f in (
        os.path.join(H3_FIELD_DIR, fn) for fn in os.listdir(H3_FIELD_DIR)
    ) if f.endswith(".csv"))

    # medals[country][medal] = [field, ...]
    medals = defaultdict(lambda: {"gold": [], "silver": [], "bronze": []})

    for path in paths:
        field = field_name_from_path(path)
        for cc, medal in award_medals(path).items():
            medals[cc][medal].append(field)

    # Sort: gold count desc, then silver, then bronze
    ranking = sorted(
        medals.items(),
        key=lambda x: (-len(x[1]["gold"]), -len(x[1]["silver"]), -len(x[1]["bronze"]))
    )

    print("=== Academic Olympics ===\n")
    for cc, m in ranking:
        gold   = m["gold"]
        silver = m["silver"]
        bronze = m["bronze"]

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


if __name__ == "__main__":
    main()
