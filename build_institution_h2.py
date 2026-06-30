#!/usr/bin/env python3
"""
Compute institution-level H2 from authors.csv, ignoring field.

H2 = n means n authors at that institution have h-index >= n.
This is the h-index algorithm applied to the sorted list of author
h-indices within each institution.

Output: h2_by_institution.csv
  institution_id, institution_name, h2, author_count

Usage:
  python3 build_institution_h2.py
"""

import duckdb
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTHORS_CSV = os.path.join(OUT_DIR, "authors.csv")
OUT_CSV = os.path.join(OUT_DIR, "h2_by_institution.csv")


def main():
    if not os.path.exists(AUTHORS_CSV):
        raise SystemExit(f"ERROR: {AUTHORS_CSV} not found. Run build.py first.")

    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='4GB'; SET enable_progress_bar=true;")

    print(f"Reading {AUTHORS_CSV}...")
    con.execute(f"""
        CREATE TABLE authors AS
        SELECT author_id, h_index, institution_id, institution_name
        FROM read_csv_auto('{AUTHORS_CSV}')
    """)
    n = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    print(f"  {n:,} authors")

    print("Computing institution H2...")
    con.execute(f"""
        COPY (
            WITH ranked AS (
                SELECT institution_id, institution_name, h_index,
                       ROW_NUMBER() OVER (
                           PARTITION BY institution_id
                           ORDER BY h_index DESC
                       ) AS rank_desc
                FROM authors
            ),
            h2_candidates AS (
                SELECT institution_id, institution_name,
                       MAX(rank_desc) AS h2
                FROM ranked
                WHERE h_index >= rank_desc
                GROUP BY institution_id, institution_name
            ),
            counts AS (
                SELECT institution_id, COUNT(*) AS author_count
                FROM authors
                GROUP BY institution_id
            )
            SELECT h.institution_id, h.institution_name, h.h2, c.author_count
            FROM h2_candidates h
            JOIN counts c USING (institution_id)
            ORDER BY h2 DESC, institution_name
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n_inst = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"  {n_inst:,} institutions → {OUT_CSV}")

    print("\nTop 20 institutions by H2:")
    rows = con.execute(f"""
        SELECT institution_name, h2, author_count
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY h2 DESC LIMIT 20
    """).fetchall()
    print(f"  {'Institution':<50} {'H2':>4} {'Authors':>8}")
    print("  " + "-" * 66)
    for name, h2, ac in rows:
        print(f"  {str(name)[:49]:<50} {h2:>4} {ac:>8,}")


if __name__ == "__main__":
    main()
