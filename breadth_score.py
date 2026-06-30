#!/usr/bin/env python3
"""
Breadth score: for each institution, count how many fields it ranks in the
global top 10, top 50, and top 100 (by H2 within that field).

High breadth → genuinely elite across many disciplines (the "true generalists").
Low breadth  → focused powerhouse, or too small to appear in multiple fields.

Institutions with high overall H2 but zero top-10 appearances are also surfaced:
they achieve aggregate strength through scale, not through leading any single field.

Output: breadth_score.csv

Usage:
  python3 breadth_score.py
"""

import duckdb
import os

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
FIELD_CSV = os.path.join(OUT_DIR, "h2_by_institution_field.csv")
INST_CSV  = os.path.join(OUT_DIR, "h2_by_institution.csv")
OUT_CSV   = os.path.join(OUT_DIR, "breadth_score.csv")

TOP_N = 30


def main():
    for p in (FIELD_CSV, INST_CSV):
        if not os.path.exists(p):
            raise SystemExit(f"ERROR: {p} not found.")

    con = duckdb.connect()
    con.execute("SET threads=4;")

    con.execute(f"""
        CREATE TABLE field_ranks AS
        WITH deduped AS (
            SELECT institution_id, field,
                   arg_max(institution_name, h2) AS institution_name,
                   arg_max(field_name, h2)        AS field_name,
                   MAX(h2)                        AS h2
            FROM read_csv_auto('{FIELD_CSV}')
            GROUP BY institution_id, field
        )
        SELECT institution_id, institution_name, field_name, h2,
               ROW_NUMBER() OVER (
                   PARTITION BY field ORDER BY h2 DESC, institution_name
               ) AS field_rank
        FROM deduped
    """)

    con.execute(f"""
        COPY (
            WITH deduped_overall AS (
                SELECT institution_id,
                       MAX(h2)           AS h2,
                       MAX(author_count) AS author_count
                FROM read_csv_auto('{INST_CSV}')
                GROUP BY institution_id
            ),
            breadth AS (
                SELECT institution_id, institution_name,
                       COUNT(*) FILTER (WHERE field_rank <= 10)  AS top10_fields,
                       COUNT(*) FILTER (WHERE field_rank <= 50)  AS top50_fields,
                       COUNT(*) FILTER (WHERE field_rank <= 100) AS top100_fields,
                       COUNT(*)                                   AS total_fields
                FROM field_ranks
                GROUP BY institution_id, institution_name
            )
            SELECT b.institution_id, b.institution_name,
                   b.top10_fields, b.top50_fields, b.top100_fields, b.total_fields,
                   o.h2 AS overall_h2, o.author_count,
                   ROW_NUMBER() OVER (ORDER BY o.h2 DESC, b.institution_name) AS overall_rank
            FROM breadth b
            JOIN deduped_overall o USING (institution_id)
            ORDER BY b.top10_fields DESC, b.top50_fields DESC, b.institution_name
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"{n:,} institutions → {OUT_CSV}\n")

    hdr = f"  {'Institution':<45} {'OvRk':>5} {'OvH2':>5} {'T10':>4} {'T50':>4} {'T100':>5}"
    sep = "  " + "-" * (len(hdr) - 2)

    print(f"Top {TOP_N} broadest institutions (most fields in global top 10):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, overall_rank, overall_h2,
               top10_fields, top50_fields, top100_fields
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY top10_fields DESC, top50_fields DESC, institution_name
        LIMIT {TOP_N}
    """).fetchall()
    for name, ov_rk, ov_h2, t10, t50, t100 in rows:
        print(f"  {str(name)[:44]:<45} {ov_rk:>5} {ov_h2:>5} {t10:>4} {t50:>4} {t100:>5}")

    # Which fields does the broadest institution not lead?
    top_inst_name = rows[0][0] if rows else None
    if top_inst_name:
        missing = con.execute(f"""
            SELECT field_name, field_rank, h2
            FROM field_ranks
            WHERE institution_name = '{top_inst_name.replace("'", "''")}'
              AND field_rank > 10
            ORDER BY field_rank
        """).fetchall()
        if missing:
            print(f"\n  Fields where {top_inst_name} is NOT in the global top 10:")
            for fname, frnk, fh2 in missing:
                print(f"    Rank {frnk:>4}  {str(fname):<40}  H2={fh2}")

    print(f"\nTop {TOP_N} by breadth (most fields in global top 50):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, overall_rank, overall_h2,
               top10_fields, top50_fields, top100_fields
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY top50_fields DESC, top10_fields DESC, institution_name
        LIMIT {TOP_N}
    """).fetchall()
    for name, ov_rk, ov_h2, t10, t50, t100 in rows:
        print(f"  {str(name)[:44]:<45} {ov_rk:>5} {ov_h2:>5} {t10:>4} {t50:>4} {t100:>5}")

    print(f"\nHigh overall H2 but 0 top-10 fields (strength through scale, not field leadership):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, overall_rank, overall_h2,
               top10_fields, top50_fields, top100_fields
        FROM read_csv_auto('{OUT_CSV}')
        WHERE top10_fields = 0 AND overall_h2 >= 20
        ORDER BY overall_h2 DESC
        LIMIT {TOP_N}
    """).fetchall()
    for name, ov_rk, ov_h2, t10, t50, t100 in rows:
        print(f"  {str(name)[:44]:<45} {ov_rk:>5} {ov_h2:>5} {t10:>4} {t50:>4} {t100:>5}")


if __name__ == "__main__":
    main()
