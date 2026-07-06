#!/usr/bin/env python3
"""
Total number of authors in each field.

Output: authors_by_field.csv

Usage:
  python3 authors_by_field.py
"""

import csv
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHORS_CSV = os.path.join(ROOT_DIR, "data", "interim", "authors.csv")
OUT_CSV = os.path.join(ROOT_DIR, "results", "authors_by_field.csv")


def main():
    if not os.path.exists(AUTHORS_CSV):
        raise SystemExit(f"ERROR: {AUTHORS_CSV} not found. Run build.py first.")

    counts: dict[str, int] = {}
    with open(AUTHORS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            counts[row["field_name"]] = counts.get(row["field_name"], 0) + 1

    rows = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["field_name", "author_count"])
        w.writerows(rows)

    print(f"{len(rows)} fields → {OUT_CSV}\n")

    hdr = f"  {'Field':<45} {'Authors':>10}"
    sep = "  " + "-" * (len(hdr) - 2)
    print(hdr)
    print(sep)
    for field_name, count in rows:
        print(f"  {str(field_name)[:44]:<45} {count:>10,}")


if __name__ == "__main__":
    main()
