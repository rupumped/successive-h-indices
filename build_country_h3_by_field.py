#!/usr/bin/env python3
"""
Compute H3 per (country, field), then write one CSV per field to h3_by_field/.

H3 = n means n institutions in that country have a field-specific H2 of at least n.

Reads:
  h2_by_institution_field.csv     (local, from build.py)
  s3://openalex/.../institutions  (anonymous, for country_code lookup)

Output: h3_by_field/<field_name>.csv
  country_code, h3, institution_count

Usage:
  python3 build_country_h3_by_field.py
"""

import csv
import duckdb
import os
import re

OUT_DIR        = os.path.dirname(os.path.abspath(__file__))
INST_FIELD_CSV = os.path.join(OUT_DIR, "h2_by_institution_field.csv")
OUT_FIELD_DIR  = os.path.join(OUT_DIR, "h3_by_field")

S3_INSTITUTIONS = "s3://openalex/data/parquet/institutions/*/*.parquet"


def safe_filename(field_name):
    return re.sub(r'[^\w\-]', '_', field_name).strip('_') + ".csv"


def main():
    if not os.path.exists(INST_FIELD_CSV):
        raise SystemExit(f"ERROR: {INST_FIELD_CSV} not found. Run build.py first.")

    os.makedirs(OUT_FIELD_DIR, exist_ok=True)

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-east-1'; SET s3_access_key_id=''; SET s3_secret_access_key='';")
    con.execute("SET threads=4; SET enable_progress_bar=true;")

    print("Fetching country codes from S3...")
    con.execute(f"""
        CREATE TABLE country_map AS
        SELECT id, country_code
        FROM read_parquet('{S3_INSTITUTIONS}')
        WHERE country_code IS NOT NULL
    """)
    print(f"  {con.execute('SELECT COUNT(*) FROM country_map').fetchone()[0]:,} institutions")

    print("Loading h2_by_institution_field.csv...")
    con.execute(f"""
        CREATE TABLE inst_field AS
        SELECT institution_id, field_name, h2
        FROM read_csv_auto('{INST_FIELD_CSV}')
    """)

    print("Computing H3 by (country, field)...")
    con.execute("""
        CREATE TABLE h3_by_country_field AS
        WITH joined AS (
            SELECT c.country_code, f.field_name, f.h2
            FROM inst_field f
            JOIN country_map c ON f.institution_id = c.id
        ),
        ranked AS (
            SELECT country_code, field_name, h2,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_code, field_name
                       ORDER BY h2 DESC
                   ) AS rank_desc
            FROM joined
        ),
        h3_candidates AS (
            SELECT country_code, field_name, MAX(rank_desc) AS h3
            FROM ranked
            WHERE h2 >= rank_desc
            GROUP BY country_code, field_name
        ),
        counts AS (
            SELECT country_code, field_name, COUNT(*) AS institution_count
            FROM joined
            GROUP BY country_code, field_name
        )
        SELECT h.country_code, h.field_name, h.h3, c.institution_count
        FROM h3_candidates h
        JOIN counts c USING (country_code, field_name)
        ORDER BY h.field_name, h.h3 DESC, h.country_code
    """)

    fields = [r[0] for r in con.execute(
        "SELECT DISTINCT field_name FROM h3_by_country_field ORDER BY field_name"
    ).fetchall()]

    print(f"Writing {len(fields)} files to {OUT_FIELD_DIR}/...")
    for field_name in fields:
        rows = con.execute("""
            SELECT country_code, h3, institution_count
            FROM h3_by_country_field
            WHERE field_name = ?
            ORDER BY h3 DESC, country_code
        """, [field_name]).fetchall()

        path = os.path.join(OUT_FIELD_DIR, safe_filename(field_name))
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["country_code", "h3", "institution_count"])
            w.writerows(rows)

    print("Done.")

    print("\nSample — top 10 countries in Computer Science:")
    rows = con.execute("""
        SELECT country_code, h3, institution_count
        FROM h3_by_country_field
        WHERE field_name = 'Computer Science'
        ORDER BY h3 DESC
        LIMIT 10
    """).fetchall()
    print(f"  {'Country':>4}  {'H3':>4}  {'Institutions':>12}")
    print("  " + "-" * 24)
    for cc, h3, n in rows:
        print(f"  {cc:>4}  {h3:>4}  {n:>12,}")


if __name__ == "__main__":
    main()
