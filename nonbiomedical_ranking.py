#!/usr/bin/env python3
"""
Re-rank institutions excluding the five core biomedical fields:
  Medicine, Biochemistry/Genetics/Molecular Biology, Immunology and Microbiology,
  Neuroscience, and Health Professions.

These five fields dominate the overall H2 because they have by far the largest,
most-cited author pools. Removing them tests whether the overall ranking is
a biomedical ranking in disguise.

Each author in authors.csv is assigned their single modal field, so filtering
by field_name excludes those authors entirely from the recomputed H2.

Output: nonbiomedical_h2.csv

Usage:
  python3 nonbiomedical_ranking.py
"""

import duckdb
import os

OUT_DIR     = os.path.dirname(os.path.abspath(__file__))
AUTHORS_CSV = os.path.join(OUT_DIR, "authors.csv")
INST_CSV    = os.path.join(OUT_DIR, "h2_by_institution.csv")
OUT_CSV     = os.path.join(OUT_DIR, "nonbiomedical_h2.csv")

TOP_N = 30

BIOMEDICAL_FIELDS = [
    "Medicine",
    "Biochemistry, Genetics and Molecular Biology",
    "Immunology and Microbiology",
    "Neuroscience",
    "Health Professions",
]


def main():
    for p in (AUTHORS_CSV, INST_CSV):
        if not os.path.exists(p):
            raise SystemExit(f"ERROR: {p} not found.")

    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='4GB';")

    fields_sql = ", ".join(f"'{f}'" for f in BIOMEDICAL_FIELDS)

    con.execute(f"""
        CREATE TABLE nonbio_h2 AS
        WITH filtered AS (
            SELECT author_id, h_index, institution_id, institution_name
            FROM read_csv_auto('{AUTHORS_CSV}')
            WHERE field_name NOT IN ({fields_sql})
        ),
        ranked AS (
            SELECT institution_id, institution_name, h_index,
                   ROW_NUMBER() OVER (
                       PARTITION BY institution_id
                       ORDER BY h_index DESC
                   ) AS rank_desc
            FROM filtered
        ),
        h2_calc AS (
            SELECT institution_id, institution_name, MAX(rank_desc) AS nonbio_h2
            FROM ranked
            WHERE h_index >= rank_desc
            GROUP BY institution_id, institution_name
        ),
        counts AS (
            SELECT institution_id, COUNT(*) AS nonbio_author_count
            FROM filtered
            GROUP BY institution_id
        )
        SELECT h.institution_id, h.institution_name,
               h.nonbio_h2, c.nonbio_author_count,
               ROW_NUMBER() OVER (ORDER BY h.nonbio_h2 DESC, h.institution_name) AS nonbio_rank
        FROM h2_calc h JOIN counts c USING (institution_id)
    """)

    con.execute(f"""
        CREATE TABLE overall AS
        WITH deduped AS (
            SELECT institution_id, MAX(h2) AS overall_h2, MAX(author_count) AS overall_author_count,
                   arg_max(institution_name, h2) AS institution_name
            FROM read_csv_auto('{INST_CSV}')
            GROUP BY institution_id
        )
        SELECT institution_id, overall_h2, overall_author_count,
               ROW_NUMBER() OVER (ORDER BY overall_h2 DESC, institution_name) AS overall_rank
        FROM deduped
    """)

    con.execute(f"""
        COPY (
            SELECT n.institution_id, n.institution_name,
                   n.nonbio_rank, n.nonbio_h2, n.nonbio_author_count,
                   o.overall_rank, o.overall_h2, o.overall_author_count,
                   (o.overall_rank - n.nonbio_rank) AS rank_change
            FROM nonbio_h2 n
            JOIN overall o USING (institution_id)
            ORDER BY n.nonbio_rank
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"{n:,} institutions → {OUT_CSV}\n")
    print(f"Biomedical fields excluded: {', '.join(BIOMEDICAL_FIELDS)}\n")

    hdr = f"  {'Institution':<45} {'NbRk':>5} {'NbH2':>5} {'OvRk':>5} {'OvH2':>5} {'Δrank':>6}"
    sep = "  " + "-" * (len(hdr) - 2)

    print(f"Top {TOP_N} institutions in non-biomedical ranking:")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, nonbio_rank, nonbio_h2, overall_rank, overall_h2, rank_change
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY nonbio_rank
        LIMIT {TOP_N}
    """).fetchall()
    for name, nb_rk, nb_h2, ov_rk, ov_h2, delta in rows:
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {str(name)[:44]:<45} {nb_rk:>5} {nb_h2:>5} {ov_rk:>5} {ov_h2:>5} {ds:>6}")

    print(f"\nBiggest rank gains when biomedical fields are removed (nonbio_h2 >= 30):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, nonbio_rank, nonbio_h2, overall_rank, overall_h2, rank_change
        FROM read_csv_auto('{OUT_CSV}')
        WHERE nonbio_h2 >= 30
        ORDER BY rank_change DESC
        LIMIT {TOP_N}
    """).fetchall()
    for name, nb_rk, nb_h2, ov_rk, ov_h2, delta in rows:
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {str(name)[:44]:<45} {nb_rk:>5} {nb_h2:>5} {ov_rk:>5} {ov_h2:>5} {ds:>6}")

    print(f"\nBiggest rank drops when biomedical fields are removed (nonbio_h2 >= 30):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, nonbio_rank, nonbio_h2, overall_rank, overall_h2, rank_change
        FROM read_csv_auto('{OUT_CSV}')
        WHERE nonbio_h2 >= 30
        ORDER BY rank_change ASC
        LIMIT {TOP_N}
    """).fetchall()
    for name, nb_rk, nb_h2, ov_rk, ov_h2, delta in rows:
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {str(name)[:44]:<45} {nb_rk:>5} {nb_h2:>5} {ov_rk:>5} {ov_h2:>5} {ds:>6}")


if __name__ == "__main__":
    main()
