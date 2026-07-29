#!/usr/bin/env python3
"""
Look up a country's h3 rank across all fields and subfields.

Usage:
  python3 country_ranks.py US
  python3 country_ranks.py de
"""

import duckdb
import os
import sys

ROOT_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR     = os.path.join(ROOT_DIR, "data", "interim")
H2_FIELD_CSV    = os.path.join(INTERIM_DIR, "h2_by_institution_field.csv")
H2_SUBFIELD_CSV = os.path.join(INTERIM_DIR, "h2_by_institution_subfield.csv")
COUNTRY_MAP_CSV = os.path.join(INTERIM_DIR, "institution_country_map.csv")
H3_COUNTRY_CSV  = os.path.join(INTERIM_DIR, "h3_by_country.csv")


def h3_sql(src_table, group_col):
    """Return SQL that computes h3 per (country_code, <group_col>) from a joined table."""
    return f"""
        WITH ranked AS (
            SELECT country_code, {group_col}, h2,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_code, {group_col}
                       ORDER BY h2 DESC
                   ) AS rank_desc
            FROM {src_table}
        ),
        h3_raw AS (
            SELECT country_code, {group_col}, MAX(rank_desc) AS h3
            FROM ranked
            WHERE h2 >= rank_desc
            GROUP BY country_code, {group_col}
        ),
        counts AS (
            SELECT country_code, {group_col}, COUNT(*) AS institution_count
            FROM {src_table}
            GROUP BY country_code, {group_col}
        )
        SELECT h.country_code, h.{group_col}, h.h3, c.institution_count
        FROM h3_raw h JOIN counts c USING (country_code, {group_col})
    """


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 country_ranks.py <country code>")
        sys.exit(1)

    country = sys.argv[1].upper()

    for path in (H2_FIELD_CSV, COUNTRY_MAP_CSV):
        if not os.path.exists(path):
            raise SystemExit(f"ERROR: {path} not found. Run build.py / fetch_country_codes.py first.")

    con = duckdb.connect()
    con.execute("SET threads=4;")

    con.execute(f"""
        CREATE TABLE country_map AS
        SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP_CSV}')
    """)
    con.execute(f"""
        CREATE TABLE inst_field AS
        SELECT institution_id, field_name, h2
        FROM read_csv_auto('{H2_FIELD_CSV}')
    """)
    con.execute("""
        CREATE TABLE joined_field AS
        SELECT cm.country_code, f.field_name, f.h2
        FROM inst_field f JOIN country_map cm ON f.institution_id = cm.id
    """)
    con.execute(f"CREATE TABLE h3_field AS {h3_sql('joined_field', 'field_name')}")

    # Validate country code.
    known = {r[0] for r in con.execute(
        "SELECT DISTINCT country_code FROM h3_field"
    ).fetchall()}

    if country not in known:
        close = sorted(c for c in known if c.startswith(country[0]))[:10]
        print(f"Country code '{country}' not found.")
        if close:
            print(f"Codes starting with '{country[0]}': {', '.join(close)}")
        sys.exit(1)

    # Overall h3 rank (optional — may be from a prior run).
    overall_line = ""
    if os.path.exists(H3_COUNTRY_CSV):
        row = con.execute(f"""
            WITH c AS (SELECT * FROM read_csv_auto('{H3_COUNTRY_CSV}')),
            ranked AS (
                SELECT country_code, h3, institution_count,
                       RANK() OVER (ORDER BY h3 DESC) AS rank,
                       COUNT() OVER ()                AS total
                FROM c
            )
            SELECT h3, rank, total, institution_count FROM ranked WHERE country_code = ?
        """, [country]).fetchone()
        if row:
            h3, rank, total, n_inst = row
            overall_line = f"  Overall  h3={h3}  rank #{rank} of {total:,}  ({n_inst:,} institutions)"

    print(f"\n{country}")
    if overall_line:
        print(overall_line)

    # Field ranks.
    field_rows = con.execute("""
        WITH ranked AS (
            SELECT country_code, field_name, h3, institution_count,
                   RANK()  OVER (PARTITION BY field_name ORDER BY h3 DESC) AS rank,
                   COUNT() OVER (PARTITION BY field_name)                  AS total
            FROM h3_field
        )
        SELECT field_name, h3, institution_count, rank, total
        FROM ranked
        WHERE country_code = ?
        ORDER BY rank, field_name
    """, [country]).fetchall()

    print(f"\n── Fields ({len(field_rows)}) ──────────────────────────────────────────")
    print(f"  {'Field':<44} {'H3':>4}  {'Rank':<14} {'Institutions':>12}")
    print(f"  {'-'*44} {'-'*4}  {'-'*14} {'-'*12}")
    for field_name, h3, n_inst, rank, total in field_rows:
        rank_str = f"#{rank} of {total:,}"
        print(f"  {field_name:<44} {h3:>4}  {rank_str:<14} {n_inst:>12,}")

    # Subfield ranks (requires h2_by_institution_subfield.csv).
    if not os.path.exists(H2_SUBFIELD_CSV):
        print("\n(Subfield data not yet available — run build.py first.)")
        print()
        return

    con.execute(f"""
        CREATE TABLE inst_subfield AS
        SELECT institution_id, subfield_name, h2
        FROM read_csv_auto('{H2_SUBFIELD_CSV}')
    """)
    con.execute("""
        CREATE TABLE joined_subfield AS
        SELECT cm.country_code, f.subfield_name, f.h2
        FROM inst_subfield f JOIN country_map cm ON f.institution_id = cm.id
    """)
    con.execute(f"CREATE TABLE h3_subfield AS {h3_sql('joined_subfield', 'subfield_name')}")

    sf_rows = con.execute("""
        WITH ranked AS (
            SELECT country_code, subfield_name, h3, institution_count,
                   RANK()  OVER (PARTITION BY subfield_name ORDER BY h3 DESC) AS rank,
                   COUNT() OVER (PARTITION BY subfield_name)                  AS total
            FROM h3_subfield
        )
        SELECT subfield_name, h3, institution_count, rank, total
        FROM ranked
        WHERE country_code = ?
        ORDER BY rank, subfield_name
    """, [country]).fetchall()

    print(f"\n── Subfields ({len(sf_rows)}) ───────────────────────────────────────────")
    print(f"  {'Subfield':<44} {'H3':>4}  {'Rank':<14} {'Institutions':>12}")
    print(f"  {'-'*44} {'-'*4}  {'-'*14} {'-'*12}")
    for sf_name, h3, n_inst, rank, total in sf_rows:
        rank_str = f"#{rank} of {total:,}"
        print(f"  {sf_name:<44} {h3:>4}  {rank_str:<14} {n_inst:>12,}")

    print()


if __name__ == "__main__":
    main()
