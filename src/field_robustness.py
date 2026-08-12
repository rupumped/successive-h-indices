#!/usr/bin/env python3
"""
Multiple-field robustness check for field-specific h₂ rankings.

Current approach: each author is assigned to exactly one field (modal by
publication volume).  This script re-assigns each author to every field in
which they have at least a given fraction of their total topic-weight,
recomputes field-specific h₂ rankings at two thresholds (20 % and 33 %),
and reports how much the single-field assumption moves the results relative
to the original.

Outputs
-------
results/field_robustness.csv         — per-threshold summary metrics
results/h2_by_field_multifield_20pct.csv  — full h₂ table at 20 % threshold
results/h2_by_field_multifield_33pct.csv  — full h₂ table at 33 % threshold
results/field_robustness.log         — verbose run log

Usage
-----
  python3 src/field_robustness.py
"""

import csv
import glob
import os
import time

import duckdb

ROOT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH    = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
STAGING    = os.path.join(ROOT_DIR, "data", "authors_staging", "*.parquet")
OUT_CSV    = os.path.join(ROOT_DIR, "results", "field_robustness.csv")
LOG_PATH   = os.path.join(ROOT_DIR, "results", "field_robustness.log")

THRESHOLDS = [0.20, 0.33]

# Reuse the same IDs and target fields as sensitivity_disambiguation.py
WAGENINGEN_ID = "https://openalex.org/I913481162"
CMU_ID        = "https://openalex.org/I74973139"
TARGET_FIELDS = {
    "https://openalex.org/fields/11": ("Agricultural and Biological Sciences", WAGENINGEN_ID),
    "https://openalex.org/fields/23": ("Environmental Science",               WAGENINGEN_ID),
    "https://openalex.org/fields/17": ("Computer Science",                    CMU_ID),
}

FIELDNAMES = [
    "threshold",
    "n_orig_pairs", "n_new_pairs", "n_new_pairs_pct_increase",
    "spearman_rho",
    "leaders_unchanged", "leaders_total",
    "wageningen_agbio_rank1", "wageningen_envsci_rank1", "cmu_cs_rank1",
]

_log_file = None


def log(msg):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def parquet_src():
    """Return a read_parquet([...]) expression covering all staging files."""
    files = sorted(glob.glob(STAGING))
    if not files:
        raise FileNotFoundError(f"No Parquet files at {STAGING}")
    files_sql = ", ".join(f"'{f}'" for f in files)
    return f"read_parquet([{files_sql}])"


def build_field_weights(con):
    """
    Materialise per-author per-field weights from the staging Parquet files,
    restricted to the qualifying authors already in the `authors` table.

    Columns: author_id, field_id, field_name, field_fraction
    """
    log("Building per-author field-weight table from staging Parquet files...")
    t0 = time.time()
    src = parquet_src()
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _field_weights AS
        WITH unnested AS (
            SELECT
                id                        AS author_id,
                tp.field.id              AS field_id,
                tp.field.display_name    AS field_name,
                tp.count                 AS cnt
            FROM {src}
            CROSS JOIN LATERAL UNNEST(topics) AS t(tp)
            WHERE tp.field.id IS NOT NULL
        ),
        field_sums AS (
            SELECT author_id, field_id, field_name, SUM(cnt) AS field_weight
            FROM unnested
            GROUP BY author_id, field_id, field_name
        ),
        author_totals AS (
            SELECT author_id, SUM(field_weight) AS total_weight
            FROM field_sums
            GROUP BY author_id
        )
        SELECT
            fs.author_id,
            fs.field_id,
            fs.field_name,
            (fs.field_weight::DOUBLE / tot.total_weight) AS field_fraction
        FROM field_sums fs
        JOIN author_totals tot USING (author_id)
        -- restrict to qualifying authors only (educational affiliation, h>0, topic)
        JOIN (SELECT author_id FROM authors) q USING (author_id)
    """)
    n = con.execute("SELECT COUNT(*) FROM _field_weights").fetchone()[0]
    log(f"  {n:,} (author, field) pairs  ({time.time()-t0:.0f}s)")


def compute_multifield_h2(con, threshold):
    """
    Build a field-specific h₂ table using all (author, field) pairs where the
    author's field_fraction >= threshold.  The h₂ algorithm is identical to
    the original: largest rank r in the per-(institution, field) h₁ sequence
    such that h₁[r] >= r.
    """
    tname = f"mf_h2_{int(threshold * 100)}"
    log(f"Computing field-specific h₂ at threshold={threshold:.0%}...")
    t0 = time.time()
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {tname} AS
        WITH
        roster AS (
            SELECT
                a.institution_id,
                a.institution_name,
                fw.field_id   AS field,
                fw.field_name,
                a.h_index
            FROM _field_weights fw
            JOIN authors a USING (author_id)
            WHERE fw.field_fraction >= {threshold}
        ),
        ranked AS (
            SELECT
                institution_id, institution_name, field, field_name, h_index,
                ROW_NUMBER() OVER (
                    PARTITION BY institution_id, field
                    ORDER BY h_index DESC
                ) AS rank_desc
            FROM roster
        ),
        h2_candidates AS (
            SELECT institution_id, field,
                   arg_max(institution_name, rank_desc) AS institution_name,
                   arg_max(field_name,       rank_desc) AS field_name,
                   MAX(rank_desc) AS h2
            FROM ranked
            WHERE h_index >= rank_desc
            GROUP BY institution_id, field
        ),
        author_counts AS (
            SELECT institution_id, field, COUNT(*) AS author_count
            FROM roster
            GROUP BY institution_id, field
        )
        SELECT
            h.institution_id, h.institution_name,
            h.field, h.field_name,
            h.h2, a.author_count
        FROM h2_candidates h
        JOIN author_counts a USING (institution_id, field)
        ORDER BY h2 DESC, institution_name, field_name
    """)
    n = con.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
    log(f"  {n:,} (institution, field) pairs  ({time.time()-t0:.0f}s)")
    return tname


def spearman_sql(con, tname):
    """
    Spearman ρ between original and multi-field h₂, computed on the inner join
    of shared (institution_id, field) pairs.  Uses DuckDB's corr() on ranks.
    """
    return con.execute(f"""
        WITH orig AS (
            SELECT institution_id, field,
                   RANK() OVER (ORDER BY h2 DESC) AS r
            FROM h2_by_institution_field
        ),
        new AS (
            SELECT institution_id, field,
                   RANK() OVER (ORDER BY h2 DESC) AS r
            FROM {tname}
        )
        SELECT corr(o.r, n.r)
        FROM orig o JOIN new n USING (institution_id, field)
    """).fetchone()[0]


def field_leader_rank(con, tname, field_id, institution_id):
    """Return the rank of institution_id in tname for field_id (1 = leader)."""
    row = con.execute(f"""
        SELECT rnk FROM (
            SELECT institution_id,
                   RANK() OVER (ORDER BY h2 DESC) AS rnk
            FROM {tname}
            WHERE field = ?
        ) ranked
        WHERE institution_id = ?
    """, [field_id, institution_id]).fetchone()
    return row[0] if row else None


def count_unchanged_leaders(con, tname):
    """
    For every field present in the original h2_by_institution_field, check
    whether the original #1 institution is still #1 in tname.
    Returns (n_unchanged, n_total, list_of_changed_tuples).
    """
    orig_leaders = con.execute("""
        SELECT field, field_name, institution_id, institution_name
        FROM h2_by_institution_field
        WHERE h2 = (
            SELECT MAX(h2) FROM h2_by_institution_field o2
            WHERE o2.field = h2_by_institution_field.field
        )
    """).fetchall()

    unchanged, changed = 0, []
    for field_id, field_name, orig_inst, orig_name in orig_leaders:
        new_leader = con.execute(
            f"SELECT institution_id, institution_name FROM {tname} "
            f"WHERE field = ? ORDER BY h2 DESC LIMIT 1",
            [field_id],
        ).fetchone()
        if new_leader and new_leader[0] == orig_inst:
            unchanged += 1
        else:
            new_name = new_leader[1] if new_leader else "(field disappeared)"
            changed.append((field_name, orig_name, new_name))

    return unchanged, len(orig_leaders), changed


def save_csv(con, tname, threshold):
    path = os.path.join(ROOT_DIR, "results",
                        f"h2_by_field_multifield_{int(threshold * 100)}pct.csv")
    con.execute(f"COPY {tname} TO '{path}' (FORMAT CSV, HEADER TRUE)")
    log(f"  Saved {path}")


def main():
    global _log_file
    with open(LOG_PATH, "w") as _log_file:
        con = duckdb.connect(DB_PATH)
        con.execute("SET enable_progress_bar=false; SET threads=8;")

        n_orig = con.execute(
            "SELECT COUNT(*) FROM h2_by_institution_field"
        ).fetchone()[0]
        log(f"Original h2_by_institution_field: {n_orig:,} (institution, field) pairs\n")

        build_field_weights(con)

        rows = []
        for threshold in THRESHOLDS:
            tname = compute_multifield_h2(con, threshold)

            rho = spearman_sql(con, tname)
            n_new = con.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
            pct_increase = 100.0 * (n_new - n_orig) / n_orig

            unchanged, total, changed = count_unchanged_leaders(con, tname)

            wag_agbio = field_leader_rank(con, tname, "https://openalex.org/fields/11", WAGENINGEN_ID)
            wag_env   = field_leader_rank(con, tname, "https://openalex.org/fields/23", WAGENINGEN_ID)
            cmu_cs    = field_leader_rank(con, tname, "https://openalex.org/fields/17", CMU_ID)

            log(f"\nThreshold {threshold:.0%}:")
            log(f"  (institution, field) pairs: {n_orig:,} → {n_new:,} (+{pct_increase:.1f}%)")
            log(f"  Spearman ρ (shared pairs):  {rho:.4f}")
            log(f"  Field leaders unchanged:    {unchanged}/{total}")
            log(f"  Wageningen Ag&Bio rank:     {wag_agbio}")
            log(f"  Wageningen EnvSci rank:     {wag_env}")
            log(f"  CMU CS rank:                {cmu_cs}")
            if changed:
                log("  Changed leaders:")
                for fname, orig, new in changed:
                    log(f"    {fname}: {orig} → {new}")

            save_csv(con, tname, threshold)

            rows.append({
                "threshold":             threshold,
                "n_orig_pairs":          n_orig,
                "n_new_pairs":           n_new,
                "n_new_pairs_pct_increase": round(pct_increase, 1),
                "spearman_rho":          round(rho, 4),
                "leaders_unchanged":     unchanged,
                "leaders_total":         total,
                "wageningen_agbio_rank1": wag_agbio == 1,
                "wageningen_envsci_rank1": wag_env == 1,
                "cmu_cs_rank1":          cmu_cs == 1,
            })

        with open(OUT_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        log(f"\nWrote summary to {OUT_CSV}")


if __name__ == "__main__":
    main()
