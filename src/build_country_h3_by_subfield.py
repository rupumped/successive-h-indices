#!/usr/bin/env python3
"""
Compute H3 per (country, subfield), then write one CSV per subfield to
data/interim/h3_by_subfield/.

H3 = n means n institutions in that country have a subfield-specific H2 of at least n.

Reads:
  h2_by_institution_subfield.csv   (local, from build.py)
  institution_country_map.csv      (local, from fetch_country_codes.py)

Output: h3_by_subfield/<subfield_name>.csv
  country_code, h3, institution_count

Usage:
  python3 build_country_h3_by_subfield.py
"""

import csv
import duckdb
import os
import re

ROOT_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR     = os.path.join(ROOT_DIR, "data", "interim")
INST_SF_CSV     = os.path.join(INTERIM_DIR, "h2_by_institution_subfield.csv")
COUNTRY_MAP_CSV = os.path.join(INTERIM_DIR, "institution_country_map.csv")
OUT_SF_DIR      = os.path.join(INTERIM_DIR, "h3_by_subfield")


def safe_filename(subfield_name):
    return re.sub(r'[^\w\-]', '_', subfield_name).strip('_') + ".csv"


def main():
    if not os.path.exists(INST_SF_CSV):
        raise SystemExit(f"ERROR: {INST_SF_CSV} not found. Run build.py first.")
    if not os.path.exists(COUNTRY_MAP_CSV):
        raise SystemExit(f"ERROR: {COUNTRY_MAP_CSV} not found. Run fetch_country_codes.py first.")

    os.makedirs(OUT_SF_DIR, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET threads=4; SET enable_progress_bar=true;")

    print("Loading country codes...")
    con.execute(f"""
        CREATE TABLE country_map AS
        SELECT id, country_code
        FROM read_csv_auto('{COUNTRY_MAP_CSV}')
    """)
    print(f"  {con.execute('SELECT COUNT(*) FROM country_map').fetchone()[0]:,} institutions")

    print("Loading h2_by_institution_subfield.csv...")
    con.execute(f"""
        CREATE TABLE inst_subfield AS
        SELECT institution_id, subfield_name, h2
        FROM read_csv_auto('{INST_SF_CSV}')
    """)

    print("Computing H3 by (country, subfield)...")
    con.execute("""
        CREATE TABLE h3_by_country_subfield AS
        WITH joined AS (
            SELECT c.country_code, f.subfield_name, f.h2
            FROM inst_subfield f
            JOIN country_map c ON f.institution_id = c.id
        ),
        ranked AS (
            SELECT country_code, subfield_name, h2,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_code, subfield_name
                       ORDER BY h2 DESC
                   ) AS rank_desc
            FROM joined
        ),
        h3_candidates AS (
            SELECT country_code, subfield_name, MAX(rank_desc) AS h3
            FROM ranked
            WHERE h2 >= rank_desc
            GROUP BY country_code, subfield_name
        ),
        counts AS (
            SELECT country_code, subfield_name, COUNT(*) AS institution_count
            FROM joined
            GROUP BY country_code, subfield_name
        )
        SELECT h.country_code, h.subfield_name, h.h3, c.institution_count
        FROM h3_candidates h
        JOIN counts c USING (country_code, subfield_name)
        ORDER BY h.subfield_name, h.h3 DESC, h.country_code
    """)

    subfields = [r[0] for r in con.execute(
        "SELECT DISTINCT subfield_name FROM h3_by_country_subfield ORDER BY subfield_name"
    ).fetchall()]

    print(f"Writing {len(subfields)} files to {OUT_SF_DIR}/...")
    for subfield_name in subfields:
        rows = con.execute("""
            SELECT country_code, h3, institution_count
            FROM h3_by_country_subfield
            WHERE subfield_name = ?
            ORDER BY h3 DESC, country_code
        """, [subfield_name]).fetchall()

        path = os.path.join(OUT_SF_DIR, safe_filename(subfield_name))
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["country_code", "h3", "institution_count"])
            w.writerows(rows)

    print("Done.")

    print("\nSample — top 10 countries in Artificial Intelligence:")
    rows = con.execute("""
        SELECT country_code, h3, institution_count
        FROM h3_by_country_subfield
        WHERE subfield_name = 'Artificial Intelligence'
        ORDER BY h3 DESC
        LIMIT 10
    """).fetchall()
    if rows:
        print(f"  {'Country':>4}  {'H3':>4}  {'Institutions':>12}")
        print("  " + "-" * 24)
        for cc, h3, n in rows:
            print(f"  {cc:>4}  {h3:>4}  {n:>12,}")
    else:
        print("  (subfield not found in data)")


if __name__ == "__main__":
    main()
