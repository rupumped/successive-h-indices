#!/usr/bin/env python3
"""
Gini coefficient of H2 across institutions within each field.

Gini = 0  → all institutions in the field have identical H2 (perfect equality)
Gini = 1  → one institution has all the H2 (perfect concentration)

High Gini → one institution dominates the field globally.
Low Gini  → excellence is broadly distributed across many institutions.

Formula (values sorted ascending, 1-indexed):
  G = (2 * Σ(i * x_i)) / (n * Σx_i)  −  (n + 1) / n

Output: field_gini.csv

Usage:
  python3 field_gini.py
"""

import duckdb
import os

ROOT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELD_CSV = os.path.join(ROOT_DIR, "data", "interim", "h2_by_institution_field.csv")
OUT_CSV   = os.path.join(ROOT_DIR, "results", "field_gini.csv")


def main():
    if not os.path.exists(FIELD_CSV):
        raise SystemExit(f"ERROR: {FIELD_CSV} not found.")

    con = duckdb.connect()
    con.execute("SET threads=4;")

    con.execute(f"""
        COPY (
            WITH deduped AS (
                SELECT institution_id, field,
                       arg_max(field_name, h2) AS field_name,
                       MAX(h2)                 AS h2
                FROM read_csv_auto('{FIELD_CSV}')
                GROUP BY institution_id, field
            ),
            per_field AS (
                SELECT field_name, h2,
                       ROW_NUMBER() OVER (PARTITION BY field ORDER BY h2 ASC, institution_id) AS i,
                       COUNT(*)  OVER (PARTITION BY field)  AS n,
                       SUM(h2)   OVER (PARTITION BY field)  AS total,
                       MAX(h2)   OVER (PARTITION BY field)  AS max_h2,
                       AVG(h2)   OVER (PARTITION BY field)  AS mean_h2
                FROM deduped
            )
            SELECT field_name,
                   MAX(n)::INTEGER                                                             AS institution_count,
                   MAX(max_h2)::INTEGER                                                        AS max_h2,
                   ROUND(MAX(mean_h2), 2)                                                      AS mean_h2,
                   ROUND(
                       (2.0 * SUM(CAST(i AS DOUBLE) * h2) / (MAX(n) * MAX(total)))
                       - (MAX(n) + 1.0) / MAX(n),
                       4
                   )                                                                           AS gini
            FROM per_field
            GROUP BY field_name
            ORDER BY gini DESC
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"{n} fields → {OUT_CSV}\n")

    hdr = f"  {'Field':<45} {'#Inst':>6} {'MaxH2':>6} {'MeanH2':>7} {'Gini':>6}"
    sep = "  " + "-" * (len(hdr) - 2)

    print("Fields ranked by Gini (high = one institution dominates, low = distributed):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT field_name, institution_count, max_h2, mean_h2, gini
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY gini DESC
    """).fetchall()
    for fname, ic, max_h2, mean_h2, gini in rows:
        print(f"  {str(fname)[:44]:<45} {ic:>6,} {max_h2:>6} {mean_h2:>7.2f} {gini:>6.4f}")

    print("\nDominance detail: top institution per field vs. field mean H2:")
    print(f"  {'Field':<45} {'Leader':<35} {'H2':>4} {'Mean':>6} {'Ratio':>6}")
    print("  " + "-" * 103)
    rows = con.execute(f"""
        WITH ranked AS (
            SELECT field_name, institution_name, h2,
                   AVG(h2) OVER (PARTITION BY field_name) AS mean_h2,
                   ROW_NUMBER() OVER (PARTITION BY field_name ORDER BY h2 DESC, institution_name) AS rnk
            FROM read_csv_auto('{FIELD_CSV}')
        )
        SELECT r.field_name, r.institution_name, r.h2,
               ROUND(r.mean_h2, 1) AS mean_h2,
               ROUND(r.h2 / r.mean_h2, 1) AS ratio
        FROM ranked r
        JOIN read_csv_auto('{OUT_CSV}') g USING (field_name)
        WHERE r.rnk = 1
        ORDER BY g.gini DESC
    """).fetchall()
    for fname, inst, h2, mean, ratio in rows:
        print(f"  {str(fname)[:44]:<45} {str(inst)[:34]:<35} {h2:>4} {mean:>6.1f} {ratio:>6.1f}x")


if __name__ == "__main__":
    main()
