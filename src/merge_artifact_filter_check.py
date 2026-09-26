#!/usr/bin/env python3
"""
Follow-up to community_college_check.py (reviewer round-2, issue 3/Tier 3).

That check found the community colleges' implausibly high h2 values are
driven by a small number of top-h_index "authors" who each list an
implausible number of distinct lifetime educational institutions (tens to
hundreds) -- a signature of author-disambiguation merge failure (multiple
distinct real people collapsed into one OpenAlex author_id), not authors
genuinely affiliated with a community college for demographic reasons.

This script tests a concrete, principled filter -- exclude authors with an
implausible number (>= MERGE_THRESHOLD) of distinct lifetime educational
institutions from the h2/efficiency computation -- and reports:
  1. Its effect on the four originally-flagged community colleges.
  2. Its effect on institution-level h2 system-wide (Spearman rho, top-N
     overlap vs. the current baseline) to see whether this is a narrow
     fix for a few small institutions or a broader systematic issue.
  3. How many institutions in the paper's existing >=100-author efficiency
     table have a top-h2-list dominated by flagged (likely-merged) authors.

Outputs
-------
results/merge_artifact_filter_check.csv  -- per-institution before/after h2
results/merge_artifact_filter_check.log  -- verbose run log

Usage
-----
  python3 src/merge_artifact_filter_check.py
"""

import os
import sys
import time

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import _source_files, _make_batches, _batch_sql  # noqa: E402

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
OUT_CSV  = os.path.join(ROOT_DIR, "results", "merge_artifact_filter_check.csv")
LOG_PATH = os.path.join(ROOT_DIR, "results", "merge_artifact_filter_check.log")

MERGE_THRESHOLD = 20  # >= this many distinct lifetime educational institutions => likely merge artifact

FLAGGED = {
    "Bellevue University": "https://openalex.org/I58064216",
    "Imperial Valley College": "https://openalex.org/I2802000487",
    "City College of San Francisco": "https://openalex.org/I158404207",
    "Frederick Community College": "https://openalex.org/I138066346",
}

_log_file = None


def log(msg):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def h2_table_sql(con, out_tname, roster_expr):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out_tname} AS
        WITH roster AS ({roster_expr}),
        ranked AS (
            SELECT institution_id, institution_name, h_index,
                   ROW_NUMBER() OVER (
                       PARTITION BY institution_id ORDER BY h_index DESC
                   ) AS rank_desc
            FROM roster
        ),
        h2_candidates AS (
            SELECT institution_id,
                   arg_max(institution_name, rank_desc) AS institution_name,
                   MAX(rank_desc) AS h2
            FROM ranked
            WHERE h_index >= rank_desc
            GROUP BY institution_id
        ),
        author_counts AS (
            SELECT institution_id, COUNT(*) AS author_count
            FROM roster GROUP BY institution_id
        )
        SELECT h.institution_id, h.institution_name, h.h2, a.author_count
        FROM h2_candidates h JOIN author_counts a USING (institution_id)
    """)


def spearman(con, t1, t2, key_cols, val_col="h2"):
    key = ", ".join(key_cols)
    return con.execute(f"""
        WITH a AS (SELECT {key}, RANK() OVER (ORDER BY {val_col} DESC) r FROM {t1}),
             b AS (SELECT {key}, RANK() OVER (ORDER BY {val_col} DESC) r FROM {t2})
        SELECT corr(a.r, b.r), COUNT(*) FROM a JOIN b USING ({key})
    """).fetchone()


def topn_overlap(con, t1, t2, key_cols, val_col, n):
    key = ", ".join(key_cols)
    a = con.execute(f"SELECT {key} FROM {t1} ORDER BY {val_col} DESC LIMIT {n}").fetchall()
    b = con.execute(f"SELECT {key} FROM {t2} ORDER BY {val_col} DESC LIMIT {n}").fetchall()
    return len(set(a) & set(b)) / n


def main():
    global _log_file
    with open(LOG_PATH, "w") as _log_file:
        t_start = time.time()
        con = duckdb.connect(DB_PATH)
        con.execute("SET enable_progress_bar=false; SET threads=4; SET memory_limit='4GB';")
        con.execute(f"SET temp_directory='{os.path.join(ROOT_DIR, 'data')}';")
        con.execute("SET preserve_insertion_order=false;")

        log(f"Computing n_lifetime_institutions per author (batched scan), threshold={MERGE_THRESHOLD}...")
        t0 = time.time()
        files = _source_files()
        batches = _make_batches(files)
        con.execute("DROP TABLE IF EXISTS _ninst")
        created = False
        for b, batch in enumerate(batches):
            batch_sql = _batch_sql(batch)
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE _ninst_batch AS
                WITH _raw AS ({batch_sql}),
                edu AS (
                    SELECT id AS author_id, aff.institution.id AS institution_id
                    FROM _raw
                    CROSS JOIN LATERAL UNNEST(affiliations) AS t(aff)
                    WHERE aff.institution.type = 'education'
                )
                SELECT author_id, COUNT(DISTINCT institution_id) AS n_lifetime_institutions
                FROM edu GROUP BY author_id
            """)
            if not created:
                con.execute("CREATE TEMP TABLE _ninst AS SELECT * FROM _ninst_batch")
                created = True
            else:
                con.execute("INSERT INTO _ninst SELECT * FROM _ninst_batch")
            con.execute("DROP TABLE _ninst_batch")
            if (b + 1) % 15 == 0 or (b + 1) == len(batches):
                log(f"  batch {b+1}/{len(batches)} done")
        log(f"  scan complete ({time.time()-t0:.0f}s)\n")

        n_flagged = con.execute(
            f"SELECT COUNT(*) FROM _ninst WHERE n_lifetime_institutions >= {MERGE_THRESHOLD}"
        ).fetchone()[0]
        n_total = con.execute("SELECT COUNT(*) FROM _ninst").fetchone()[0]
        log(f"Authors with >= {MERGE_THRESHOLD} distinct lifetime educational institutions "
            f"(likely disambiguation-merge artifacts): {n_flagged:,} / {n_total:,} ({n_flagged/n_total:.2%})\n")

        con.execute("""
            CREATE OR REPLACE TEMP TABLE _authors_flagged AS
            SELECT a.author_id, a.institution_id, a.institution_name, a.h_index, n.n_lifetime_institutions
            FROM authors a JOIN _ninst n USING (author_id)
        """)

        log("Computing institution h2: baseline (all authors) vs filtered (merge artifacts excluded)...")
        h2_table_sql(con, "h2_baseline",
                     "SELECT institution_id, institution_name, h_index FROM _authors_flagged")
        h2_table_sql(con, "h2_filtered",
                     f"SELECT institution_id, institution_name, h_index FROM _authors_flagged "
                     f"WHERE n_lifetime_institutions < {MERGE_THRESHOLD}")

        rho, n_shared = spearman(con, "h2_baseline", "h2_filtered", ["institution_id"])
        ov10 = topn_overlap(con, "h2_baseline", "h2_filtered", ["institution_id"], "h2", 10)
        ov20 = topn_overlap(con, "h2_baseline", "h2_filtered", ["institution_id"], "h2", 20)
        log(f"System-wide effect: rho = {rho:.4f} ({n_shared:,} shared institutions), "
            f"top-10 overlap {ov10:.0%}, top-20 overlap {ov20:.0%}\n")

        log("Effect on the four originally-flagged community colleges:")
        log(f"  {'institution':<32}{'h2_base':>8}{'authors_base':>13}{'h2_filtered':>12}{'authors_filt':>13}")
        for name, iid in FLAGGED.items():
            base = con.execute("SELECT h2, author_count FROM h2_baseline WHERE institution_id = ?", [iid]).fetchone()
            filt = con.execute("SELECT h2, author_count FROM h2_filtered WHERE institution_id = ?", [iid]).fetchone()
            b_h2, b_n = base if base else (0, 0)
            f_h2, f_n = filt if filt else (0, 0)
            log(f"  {name:<32}{b_h2:>8}{b_n:>13,}{f_h2:>12}{f_n:>13,}")
        log("")

        log(f"Top 20 institutions by |h2 drop| under the filter (baseline h2 - filtered h2), "
            f"restricted to institutions with >=100 baseline authors (paper's efficiency-table cutoff):")
        movers = con.execute(f"""
            SELECT b.institution_name, b.h2 AS h2_base, b.author_count AS n_base,
                   COALESCE(f.h2, 0) AS h2_filt, COALESCE(f.author_count, 0) AS n_filt,
                   (b.h2 - COALESCE(f.h2, 0)) AS drop_
            FROM h2_baseline b
            LEFT JOIN h2_filtered f USING (institution_id)
            WHERE b.author_count >= 100
            ORDER BY drop_ DESC
            LIMIT 20
        """).fetchall()
        log(f"  {'institution':<45}{'h2_base':>8}{'n_base':>8}{'h2_filt':>8}{'n_filt':>8}{'drop':>6}")
        for name, h2b, nb, h2f, nf, drop in movers:
            log(f"  {str(name)[:44]:<45}{h2b:>8}{nb:>8,}{h2f:>8}{nf:>8,}{drop:>6}")
        log("")

        con.execute(f"""
            COPY (
                SELECT b.institution_id, b.institution_name,
                       b.h2 AS h2_baseline, b.author_count AS authors_baseline,
                       f.h2 AS h2_filtered, f.author_count AS authors_filtered
                FROM h2_baseline b LEFT JOIN h2_filtered f USING (institution_id)
                ORDER BY b.h2 DESC
            ) TO '{OUT_CSV}' (FORMAT CSV, HEADER TRUE)
        """)
        log(f"Wrote {OUT_CSV}")
        log(f"\nTotal runtime: {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
