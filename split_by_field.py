#!/usr/bin/env python3
"""
Split h2_by_institution_field.csv into one CSV per field, written to
h2_by_field/<field_name>.csv (sorted by h2 descending).

Usage:
  python3 split_by_field.py
"""

import csv
import os
import re

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h2_by_institution_field.csv")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h2_by_field")

COLUMNS = ["institution_id", "institution_name", "h2", "author_count"]


def safe_filename(field_name):
    return re.sub(r'[^\w\-]', '_', field_name).strip('_') + ".csv"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    by_field: dict[str, list] = {}
    with open(SRC, newline="") as f:
        for row in csv.DictReader(f):
            by_field.setdefault(row["field_name"], []).append(row)

    for field_name, rows in sorted(by_field.items()):
        rows.sort(key=lambda r: int(r["h2"]), reverse=True)
        path = os.path.join(OUT_DIR, safe_filename(field_name))
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow({k: row[k] for k in COLUMNS})

    print(f"Wrote {len(by_field)} files to {OUT_DIR}/")


if __name__ == "__main__":
    main()
