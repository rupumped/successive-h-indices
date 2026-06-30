#!/usr/bin/env python3
"""
Compute a specialization index for each institution:

  specialization_index = overall_rank - best_field_rank

Where:
  overall_rank     = rank in h2_by_institution.csv (1 = highest overall H2)
  best_field_rank  = best (lowest) rank the institution achieves in any
                     single field in h2_by_institution_field.csv
                     (ties broken by highest field H2, then field name)

A high specialization index means the institution ranks much higher in its
best field than it does overall — a hallmark of a focused research powerhouse.
A near-zero index means the institution is broad: it ranks similarly in its
best field as it does overall.

Output: specialization_index.csv  (all institutions)

The printed tables filter to overall_h2 >= MIN_H2 to surface meaningful results.

Usage:
  python3 specialization_index.py
"""

import duckdb
import os

OUT_DIR        = os.path.dirname(os.path.abspath(__file__))
INST_CSV       = os.path.join(OUT_DIR, "h2_by_institution.csv")
INST_FIELD_CSV = os.path.join(OUT_DIR, "h2_by_institution_field.csv")
OUT_CSV        = os.path.join(OUT_DIR, "specialization_index.csv")

TOP_N          = 20
MIN_H2         = 10   # only show institutions with meaningful overall strength
MAX_FIELD_RANK = 5   # only show institutions that are elite in at least one field


def main():
    for p in (INST_CSV, INST_FIELD_CSV):
        if not os.path.exists(p):
            raise SystemExit(f"ERROR: {p} not found. Run build.py and build_institution_h2.py first.")

    con = duckdb.connect()
    con.execute("SET threads=4;")

    con.execute(f"""
        CREATE TABLE overall AS
        WITH deduped AS (
            SELECT institution_id,
                   arg_max(institution_name, h2) AS institution_name,
                   MAX(h2)           AS h2,
                   MAX(author_count) AS author_count
            FROM read_csv_auto('{INST_CSV}')
            GROUP BY institution_id
        )
        SELECT institution_id, institution_name,
               h2            AS overall_h2,
               author_count  AS overall_author_count,
               ROW_NUMBER() OVER (ORDER BY h2 DESC, institution_name) AS overall_rank
        FROM deduped
    """)

    # Rank every institution within each field.
    # Ties broken by field_h2 DESC then field_name so each institution gets
    # exactly one best-field row.
    con.execute(f"""
        CREATE TABLE field_ranks AS
        WITH deduped_field AS (
            SELECT institution_id, field,
                   arg_max(field_name, h2)    AS field_name,
                   MAX(h2)                    AS h2,
                   MAX(author_count)          AS author_count
            FROM read_csv_auto('{INST_FIELD_CSV}')
            GROUP BY institution_id, field
        ),
        ranked AS (
            SELECT institution_id,
                   field_name,
                   h2           AS field_h2,
                   author_count AS field_author_count,
                   ROW_NUMBER() OVER (
                       PARTITION BY field
                       ORDER BY h2 DESC, field_name
                   ) AS field_rank
            FROM deduped_field
        ),
        best AS (
            SELECT institution_id,
                   MIN(field_rank) AS best_rank
            FROM ranked
            GROUP BY institution_id
        )
        SELECT DISTINCT ON (r.institution_id)
               r.institution_id, r.field_name, r.field_h2,
               r.field_author_count, r.field_rank
        FROM ranked r
        JOIN best b ON r.institution_id = b.institution_id
                    AND r.field_rank = b.best_rank
        ORDER BY r.institution_id, r.field_h2 DESC, r.field_name
    """)

    con.execute(f"""
        COPY (
            SELECT
                o.institution_id,
                o.institution_name,
                o.overall_rank,
                o.overall_h2,
                o.overall_author_count,
                f.field_rank          AS best_field_rank,
                f.field_name          AS best_field_name,
                f.field_h2            AS best_field_h2,
                f.field_author_count  AS best_field_author_count,
                (o.overall_rank - f.field_rank) AS specialization_index
            FROM overall o
            JOIN field_ranks f USING (institution_id)
            ORDER BY specialization_index DESC, o.institution_name
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"{n:,} institutions → {OUT_CSV}\n")

    hdr = f"  {'Institution':<45} {'OvRk':>5} {'OvH2':>5}  {'FldRk':>5} {'FldH2':>5}  {'Best Field':<38} {'Spec':>5}"
    sep = "  " + "-" * (len(hdr) - 2)

    def print_table(rows):
        print(hdr)
        print(sep)
        for name, ov_rk, ov_h2, f_rk, f_name, f_h2, spec in rows:
            print(f"  {str(name)[:44]:<45} {ov_rk:>5} {ov_h2:>5}  {f_rk:>5} {f_h2:>5}  {str(f_name)[:37]:<38} {spec:>5}")

    print(f"Top {TOP_N} most specialized (overall_h2 >= {MIN_H2}, best_field_rank <= {MAX_FIELD_RANK}):")
    rows = con.execute(f"""
        SELECT institution_name, overall_rank, overall_h2,
               best_field_rank, best_field_name, best_field_h2,
               specialization_index
        FROM read_csv_auto('{OUT_CSV}')
        WHERE overall_h2 >= {MIN_H2}
          AND best_field_rank <= {MAX_FIELD_RANK}
        ORDER BY specialization_index DESC, institution_name
        LIMIT {TOP_N}
    """).fetchall()
    print_table(rows)

    print(f"\nTop {TOP_N} least specialized / broadest (overall_h2 >= {MIN_H2}, best_field_rank <= {MAX_FIELD_RANK}):")
    rows = con.execute(f"""
        SELECT institution_name, overall_rank, overall_h2,
               best_field_rank, best_field_name, best_field_h2,
               specialization_index
        FROM read_csv_auto('{OUT_CSV}')
        WHERE overall_h2 >= {MIN_H2}
          AND best_field_rank <= {MAX_FIELD_RANK}
        ORDER BY specialization_index ASC, institution_name
        LIMIT {TOP_N}
    """).fetchall()
    print_table(rows)


if __name__ == "__main__":
    main()
