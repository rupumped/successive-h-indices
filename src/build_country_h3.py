#!/usr/bin/env python3
"""
Compute H3 index per country.

H3 = n means n institutions in that country have an H2 index of at least n.

Reads:
  h2_by_institution.csv           (local, from build_institution_h2.py)
  institution_country_map.csv     (local, from fetch_country_codes.py)

Output: h3_by_country.csv
  country_code, h3, institution_count

Usage:
  python3 build_country_h3.py
"""

import duckdb
import os

ROOT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR = os.path.join(ROOT_DIR, "data", "interim")
INST_CSV  = os.path.join(INTERIM_DIR, "h2_by_institution.csv")
COUNTRY_MAP_CSV = os.path.join(INTERIM_DIR, "institution_country_map.csv")
OUT_CSV   = os.path.join(INTERIM_DIR, "h3_by_country.csv")

TOP_N = 30


def main():
    if not os.path.exists(INST_CSV):
        raise SystemExit(f"ERROR: {INST_CSV} not found. Run build_institution_h2.py first.")
    if not os.path.exists(COUNTRY_MAP_CSV):
        raise SystemExit(f"ERROR: {COUNTRY_MAP_CSV} not found. Run fetch_country_codes.py first.")

    con = duckdb.connect()
    con.execute("SET threads=4; SET enable_progress_bar=true;")

    print("Loading country codes...")
    con.execute(f"""
        CREATE TABLE country_map AS
        SELECT id, country_code
        FROM read_csv_auto('{COUNTRY_MAP_CSV}')
    """)
    n_inst = con.execute("SELECT COUNT(*) FROM country_map").fetchone()[0]
    print(f"  {n_inst:,} institutions with country codes")

    print("Computing H3...")
    con.execute(f"""
        CREATE TABLE h2 AS
        SELECT institution_id, h2
        FROM read_csv_auto('{INST_CSV}')
    """)

    con.execute(f"""
        COPY (
            WITH joined AS (
                SELECT c.country_code, h.h2
                FROM h2 h
                JOIN country_map c ON h.institution_id = c.id
            ),
            ranked AS (
                SELECT country_code, h2,
                       ROW_NUMBER() OVER (
                           PARTITION BY country_code
                           ORDER BY h2 DESC
                       ) AS rank_desc
                FROM joined
            ),
            h3_candidates AS (
                SELECT country_code, MAX(rank_desc) AS h3
                FROM ranked
                WHERE h2 >= rank_desc
                GROUP BY country_code
            ),
            counts AS (
                SELECT country_code, COUNT(*) AS institution_count
                FROM joined
                GROUP BY country_code
            )
            SELECT h.country_code, h.h3, c.institution_count
            FROM h3_candidates h
            JOIN counts c USING (country_code)
            ORDER BY h3 DESC, country_code
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"  {n} countries → {OUT_CSV}\n")

    print(f"Top {TOP_N} countries by H3:")
    rows = con.execute(f"""
        SELECT country_code, h3, institution_count
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY h3 DESC
        LIMIT {TOP_N}
    """).fetchall()
    print(f"  {'Country':>4}  {'H3':>4}  {'Institutions':>12}")
    print("  " + "-" * 24)
    for cc, h3, n_i in rows:
        print(f"  {cc:>4}  {h3:>4}  {n_i:>12,}")


if __name__ == "__main__":
    main()
