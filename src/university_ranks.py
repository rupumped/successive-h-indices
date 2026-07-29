#!/usr/bin/env python3
"""
Look up a university's h2 rank across all fields and subfields.

Usage:
  python3 university_ranks.py "Carnegie Mellon"
  python3 university_ranks.py Harvard
"""

import duckdb
import os
import sys

ROOT_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR     = os.path.join(ROOT_DIR, "data", "interim")
H2_FIELD_CSV    = os.path.join(INTERIM_DIR, "h2_by_institution_field.csv")
H2_SUBFIELD_CSV = os.path.join(INTERIM_DIR, "h2_by_institution_subfield.csv")
H2_INST_CSV     = os.path.join(INTERIM_DIR, "h2_by_institution.csv")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 university_ranks.py <university name>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    for path in (H2_FIELD_CSV, H2_SUBFIELD_CSV):
        if not os.path.exists(path):
            raise SystemExit(f"ERROR: {path} not found. Run build.py first.")

    con = duckdb.connect()
    con.execute("SET threads=4;")

    con.execute(f"CREATE TABLE field    AS SELECT * FROM read_csv_auto('{H2_FIELD_CSV}')")
    con.execute(f"CREATE TABLE subfield AS SELECT * FROM read_csv_auto('{H2_SUBFIELD_CSV}')")

    # Resolve institution — try substring match, fall back to listing candidates.
    matches = con.execute("""
        SELECT DISTINCT institution_id, institution_name
        FROM field
        WHERE institution_name ILIKE ?
        ORDER BY institution_name
    """, [f"%{query}%"]).fetchall()

    if not matches:
        print(f"No institution found matching '{query}'.")
        sys.exit(1)

    if len(matches) > 10:
        print(f"{len(matches)} institutions match '{query}'. Showing first 10 — be more specific:\n")
        for _, name in matches[:10]:
            print(f"  {name}")
        sys.exit(1)

    if len(matches) > 1:
        print(f"Multiple institutions match '{query}':\n")
        for i, (_, name) in enumerate(matches, 1):
            print(f"  {i}. {name}")
        print("\nBe more specific.")
        sys.exit(1)

    inst_id, inst_name = matches[0]

    # Overall rank (optional file — may not exist or may be from a prior run).
    overall_line = ""
    if os.path.exists(H2_INST_CSV):
        row = con.execute(f"""
            WITH inst AS (SELECT * FROM read_csv_auto('{H2_INST_CSV}')),
            ranked AS (
                SELECT institution_id, h2, author_count,
                       RANK() OVER (ORDER BY h2 DESC) AS rank,
                       COUNT(*) OVER ()               AS total
                FROM inst
            )
            SELECT h2, rank, total, author_count FROM ranked WHERE institution_id = ?
        """, [inst_id]).fetchone()
        if row:
            h2, rank, total, ac = row
            overall_line = f"  Overall  h2={h2}  rank #{rank} of {total:,}  ({ac:,} authors)"

    print(f"\n{inst_name}")
    if overall_line:
        print(overall_line)

    # Field ranks.
    field_rows = con.execute("""
        WITH ranked AS (
            SELECT institution_id, field_name, h2, author_count,
                   RANK()  OVER (PARTITION BY field ORDER BY h2 DESC) AS rank,
                   COUNT() OVER (PARTITION BY field)                  AS total
            FROM field
        )
        SELECT field_name, h2, author_count, rank, total
        FROM ranked
        WHERE institution_id = ?
        ORDER BY rank, field_name
    """, [inst_id]).fetchall()

    print(f"\n── Fields ({len(field_rows)}) ──────────────────────────────────────────")
    print(f"  {'Field':<44} {'H2':>4}  {'Rank':<14} {'Authors':>8}")
    print(f"  {'-'*44} {'-'*4}  {'-'*14} {'-'*8}")
    for field_name, h2, ac, rank, total in field_rows:
        rank_str = f"#{rank} of {total:,}"
        print(f"  {field_name:<44} {h2:>4}  {rank_str:<14} {ac:>8,}")

    # Subfield ranks.
    sf_rows = con.execute("""
        WITH ranked AS (
            SELECT institution_id, subfield_name, h2, author_count,
                   RANK()  OVER (PARTITION BY subfield ORDER BY h2 DESC) AS rank,
                   COUNT() OVER (PARTITION BY subfield)                  AS total
            FROM subfield
        )
        SELECT subfield_name, h2, author_count, rank, total
        FROM ranked
        WHERE institution_id = ?
        ORDER BY rank, subfield_name
    """, [inst_id]).fetchall()

    print(f"\n── Subfields ({len(sf_rows)}) ───────────────────────────────────────────")
    print(f"  {'Subfield':<44} {'H2':>4}  {'Rank':<14} {'Authors':>8}")
    print(f"  {'-'*44} {'-'*4}  {'-'*14} {'-'*8}")
    for sf_name, h2, ac, rank, total in sf_rows:
        rank_str = f"#{rank} of {total:,}"
        print(f"  {sf_name:<44} {h2:>4}  {rank_str:<14} {ac:>8,}")

    print()


if __name__ == "__main__":
    main()
