#!/usr/bin/env python3
"""
H3 efficiency: H3 / log2(institution_count).

Raw H3 measures the depth of a national research system, but it rewards
having many institutions. A country with 10,000 universities and H3=60 is
less impressive than one with 100 universities and H3=50. Dividing by
log2(institution_count) adjusts for scale and surfaces countries whose
research excellence is concentrated.

Also shows the most efficient country per field.

Italy/Japan tie in the README at H3=43 with 221 vs 1,281 institutions —
this metric quantifies that gap.

Output: h3_efficiency.csv

Usage:
  python3 h3_efficiency.py
"""

import csv
import math
import os

ROOT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR  = os.path.join(ROOT_DIR, "data", "interim")
H3_CSV       = os.path.join(INTERIM_DIR, "h3_by_country.csv")
H3_FIELD_DIR = os.path.join(INTERIM_DIR, "h3_by_field")
OUT_CSV      = os.path.join(ROOT_DIR, "results", "h3_efficiency.csv")

TOP_N    = 30
MIN_INST = 5   # countries with fewer institutions produce unstable H3


def field_name_from_path(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace("__", ", ").replace("_", " ")


def main():
    if not os.path.exists(H3_CSV):
        raise SystemExit(f"ERROR: {H3_CSV} not found.")

    with open(H3_CSV, newline="") as f:
        raw = [(r["country_code"], int(r["h3"]), int(r["institution_count"]))
               for r in csv.DictReader(f)]

    raw.sort(key=lambda x: (-x[1], x[0]))
    h3_rank_of = {cc: i + 1 for i, (cc, _, _) in enumerate(raw)}

    results = []
    for cc, h3, ic in raw:
        if ic < MIN_INST:
            continue
        eff = h3 / math.log2(ic)
        results.append((cc, h3, ic, eff, h3_rank_of[cc]))

    results.sort(key=lambda x: (-x[3], x[0]))
    eff_rank_of = {cc: i + 1 for i, (cc, *_) in enumerate(results)}

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country_code", "h3", "institution_count", "efficiency",
                    "h3_rank", "efficiency_rank"])
        for i, (cc, h3, ic, eff, h3_rank) in enumerate(results, 1):
            w.writerow([cc, h3, ic, round(eff, 4), h3_rank, i])

    print(f"{len(results)} countries (institution_count ≥ {MIN_INST}) → {OUT_CSV}\n")

    hdr = f"  {'CC':>4} {'EffRk':>6} {'Eff':>6} {'H3':>4} {'H3Rk':>5} {'#Inst':>6} {'Δrank':>6}"
    sep = "  " + "-" * (len(hdr) - 2)

    print(f"Top {TOP_N} by H3 efficiency (H3 / log₂(institution_count)):")
    print(hdr); print(sep)
    for i, (cc, h3, ic, eff, h3_rank) in enumerate(results[:TOP_N], 1):
        delta = h3_rank - i
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {cc:>4} {i:>6} {eff:>6.2f} {h3:>4} {h3_rank:>5} {ic:>6,} {ds:>6}")

    print(f"\nTop {TOP_N} by raw H3 for comparison:")
    raw_eligible = [(cc, h3, ic, eff, h3_rank) for (cc, h3, ic, eff, h3_rank) in results]
    raw_eligible.sort(key=lambda x: (x[4], x[0]))
    print(hdr); print(sep)
    for i, (cc, h3, ic, eff, h3_rank) in enumerate(raw_eligible[:TOP_N], 1):
        er = eff_rank_of[cc]
        delta = h3_rank - er
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {cc:>4} {er:>6} {eff:>6.2f} {h3:>4} {h3_rank:>5} {ic:>6,} {ds:>6}")

    # Most efficient country per field
    if os.path.isdir(H3_FIELD_DIR):
        field_files = sorted(
            os.path.join(H3_FIELD_DIR, fn)
            for fn in os.listdir(H3_FIELD_DIR)
            if fn.endswith(".csv")
        )
        print(f"\nMost efficient country per field (institution_count ≥ {MIN_INST}):")
        print(f"  {'Field':<45} {'CC':>4} {'H3':>4} {'#Inst':>6} {'Eff':>6} {'H3Rk':>6}")
        print("  " + "-" * 79)
        for path in field_files:
            fname = field_name_from_path(path)
            with open(path, newline="") as f:
                rows = [(r["country_code"], int(r["h3"]), int(r["institution_count"]))
                        for r in csv.DictReader(f)
                        if int(r["institution_count"]) >= MIN_INST]
            if not rows:
                continue
            rows.sort(key=lambda x: (-x[1], x[0]))
            field_h3_rank = {cc: i + 1 for i, (cc, _, _) in enumerate(rows)}
            best = max(rows, key=lambda x: x[1] / math.log2(x[2]))
            cc, h3, ic = best
            eff = h3 / math.log2(ic)
            print(f"  {str(fname)[:44]:<45} {cc:>4} {h3:>4} {ic:>6,} {eff:>6.2f} {field_h3_rank[cc]:>6}")


if __name__ == "__main__":
    main()
