#!/usr/bin/env python3
"""
Split h2_by_institution_subfield.csv into one CSV per subfield, written to
results/h2_by_subfield/<subfield_name>.csv (sorted by h2 descending).

Usage:
  python3 split_by_subfield.py
"""

import csv
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT_DIR, "data", "interim", "h2_by_institution_subfield.csv")
OUT_DIR = os.path.join(ROOT_DIR, "results", "h2_by_subfield")

COLUMNS = ["institution_id", "institution_name", "h2", "author_count"]


def safe_filename(subfield_name):
    return re.sub(r'[^\w\-]', '_', subfield_name).strip('_') + ".csv"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    by_subfield: dict[str, list] = {}
    with open(SRC, newline="") as f:
        for row in csv.DictReader(f):
            by_subfield.setdefault(row["subfield_name"], []).append(row)

    for subfield_name, rows in sorted(by_subfield.items()):
        rows.sort(key=lambda r: int(r["h2"]), reverse=True)
        path = os.path.join(OUT_DIR, safe_filename(subfield_name))
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow({k: row[k] for k in COLUMNS})

    print(f"Wrote {len(by_subfield)} files to {OUT_DIR}/")


if __name__ == "__main__":
    main()
