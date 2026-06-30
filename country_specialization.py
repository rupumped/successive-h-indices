#!/usr/bin/env python3
"""
Country specialization index: overall H3 rank minus best-field H3 rank.

Mirrors specialization_index.py but at the country level. A high index means
the country is much more elite in its best field than it is overall — a signal
of concentrated national research investment rather than broad research power.

Brazil/Dentistry is the anticipated poster child; this reveals the full table.

Output: country_specialization.csv

Usage:
  python3 country_specialization.py
"""

import csv
import os

OUT_DIR      = os.path.dirname(os.path.abspath(__file__))
H3_OVERALL   = os.path.join(OUT_DIR, "h3_by_country.csv")
H3_FIELD_DIR = os.path.join(OUT_DIR, "h3_by_field")
OUT_CSV      = os.path.join(OUT_DIR, "country_specialization.csv")

TOP_N    = 30
MIN_H3   = 5   # ignore countries too small for meaningful H3 in the printed tables
MIN_INST = 10


def field_name_from_path(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace("__", ", ").replace("_", " ")


def load_overall():
    with open(H3_OVERALL, newline="") as f:
        rows = [(r["country_code"], int(r["h3"]), int(r["institution_count"]))
                for r in csv.DictReader(f)]
    rows.sort(key=lambda x: (-x[1], x[0]))
    return {cc: (h3, ic, rank + 1) for rank, (cc, h3, ic) in enumerate(rows)}


def load_best_field_ranks():
    """For each country, find its best (lowest-numbered) rank across all fields."""
    field_files = sorted(
        os.path.join(H3_FIELD_DIR, fn)
        for fn in os.listdir(H3_FIELD_DIR)
        if fn.endswith(".csv")
    )
    best = {}  # cc -> (rank, field_name, h3)
    for path in field_files:
        fname = field_name_from_path(path)
        with open(path, newline="") as f:
            rows = [(r["country_code"], int(r["h3"])) for r in csv.DictReader(f)]
        rows.sort(key=lambda x: (-x[1], x[0]))
        for rank, (cc, h3) in enumerate(rows, 1):
            if cc not in best or rank < best[cc][0]:
                best[cc] = (rank, fname, h3)
    return best


def main():
    if not os.path.exists(H3_OVERALL):
        raise SystemExit(f"ERROR: {H3_OVERALL} not found.")
    if not os.path.isdir(H3_FIELD_DIR):
        raise SystemExit(f"ERROR: {H3_FIELD_DIR} not found. Run build_country_h3_by_field.py first.")

    overall = load_overall()
    field_ranks = load_best_field_ranks()

    results = []
    for cc, (ov_h3, ic, ov_rank) in overall.items():
        if cc not in field_ranks:
            continue
        bf_rank, bf_name, bf_h3 = field_ranks[cc]
        spec = ov_rank - bf_rank
        results.append((cc, ov_rank, ov_h3, ic, bf_rank, bf_name, bf_h3, spec))

    results.sort(key=lambda x: (-x[7], x[0]))

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country_code", "overall_rank", "overall_h3", "institution_count",
                    "best_field_rank", "best_field_name", "best_field_h3", "specialization_index"])
        w.writerows(results)

    print(f"{len(results)} countries → {OUT_CSV}\n")

    hdr = (f"  {'CC':>4} {'OvRk':>5} {'OvH3':>5} {'#Inst':>6}  "
           f"{'FldRk':>5} {'FldH3':>5}  {'Best Field':<38} {'Spec':>5}")
    sep = "  " + "-" * (len(hdr) - 2)

    def print_table(rows):
        print(hdr); print(sep)
        for cc, ov_rk, ov_h3, ic, bf_rk, bf_name, bf_h3, spec in rows:
            print(f"  {cc:>4} {ov_rk:>5} {ov_h3:>5} {ic:>6,}  "
                  f"{bf_rk:>5} {bf_h3:>5}  {str(bf_name)[:37]:<38} {spec:>5}")

    filtered = [r for r in results if r[2] >= MIN_H3 and r[3] >= MIN_INST]

    print(f"Top {TOP_N} most specialized countries (overall_h3 ≥ {MIN_H3}, inst ≥ {MIN_INST}):")
    print_table(filtered[:TOP_N])

    print(f"\nTop {TOP_N} broadest countries (overall_h3 ≥ {MIN_H3}, inst ≥ {MIN_INST}):")
    print_table(sorted(filtered, key=lambda x: (x[7], x[0]))[:TOP_N])


if __name__ == "__main__":
    main()
