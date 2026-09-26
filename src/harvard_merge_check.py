#!/usr/bin/env python3
"""
Targeted follow-up: are Harvard's ~34 top-h_index authors excluded by the
n_lifetime_institutions >= 20 merge-artifact filter (merge_artifact_filter_check.py)
genuine disambiguation-merge artifacts (like the community-college cases:
huge n_inst, cross-field, implausible career span) or borderline legitimate
hyper-mobile researchers? Pulls Harvard's full author roster with
n_lifetime_institutions and, for the top ones, their complete affiliation
history for manual inspection.

Usage:
  python3 src/harvard_merge_check.py
"""

import os
import sys
import time

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import _source_files, _make_batches, _batch_sql  # noqa: E402

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_CSV  = os.path.join(ROOT_DIR, "results", "harvard_merge_check.csv")
LOG_PATH = os.path.join(ROOT_DIR, "results", "harvard_merge_check.log")

HARVARD_ID = "https://openalex.org/I136199984"

_log_file = None


def log(msg):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def main():
    global _log_file
    with open(LOG_PATH, "w") as _log_file:
        t0 = time.time()
        con = duckdb.connect()
        con.execute("SET threads=4; SET memory_limit='4GB'; SET enable_progress_bar=false;")
        con.execute(f"SET temp_directory='{os.path.join(ROOT_DIR, 'data')}';")

        files = _source_files()
        batches = _make_batches(files)
        con.execute("DROP TABLE IF EXISTS _hits")
        created = False
        log(f"Scanning {len(files)} staging files in {len(batches)} batches, filtering to Harvard...")
        for b, batch in enumerate(batches):
            batch_sql = _batch_sql(batch)
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE _hits_batch AS
                WITH _raw AS ({batch_sql}),
                edu AS (
                    SELECT id AS author_id, h_index, works_count,
                           aff.institution.id           AS institution_id,
                           aff.institution.display_name AS institution_name
                    FROM _raw
                    CROSS JOIN LATERAL UNNEST(affiliations) AS t(aff)
                    WHERE aff.institution.type = 'education'
                ),
                harvard_authors AS (
                    SELECT DISTINCT author_id FROM edu WHERE institution_id = '{HARVARD_ID}'
                )
                SELECT e.author_id, e.h_index, e.works_count, e.institution_id, e.institution_name
                FROM edu e
                JOIN harvard_authors ha USING (author_id)
            """)
            if not created:
                con.execute("CREATE TEMP TABLE _hits AS SELECT * FROM _hits_batch")
                created = True
            else:
                con.execute("INSERT INTO _hits SELECT * FROM _hits_batch")
            con.execute("DROP TABLE _hits_batch")
            if (b + 1) % 15 == 0 or (b + 1) == len(batches):
                log(f"  batch {b+1}/{len(batches)} done")

        log(f"\nScan complete ({time.time()-t0:.0f}s)\n")

        con.execute("""
            CREATE TEMP TABLE _agg AS
            SELECT author_id, COUNT(DISTINCT institution_id) AS n_inst,
                   FIRST(h_index) AS h, FIRST(works_count) AS w
            FROM _hits GROUP BY author_id
        """)

        log("Top 40 Harvard authors by h_index, with n_lifetime_institutions:")
        rows = con.execute("SELECT author_id, h, w, n_inst FROM _agg ORDER BY h DESC LIMIT 40").fetchall()
        log(f"  {'author_id':<35}{'h_index':>9}{'works':>8}{'n_inst':>8}")
        for aid, h, w, n in rows:
            log(f"  {aid:<35}{h:>9}{w:>8}{n:>8}")
        log("")

        log("n_inst distribution among the excluded (n_inst>=20) top-40:")
        excluded = [r for r in rows if r[3] >= 20]
        log(f"  {len(excluded)} of top 40 are excluded by the n_inst>=20 filter")
        log("")

        log("Full affiliation lists for the top 8 excluded (n_inst>=20) authors:")
        for aid, h, w, n in [r for r in rows if r[3] >= 20][:8]:
            affs = con.execute("SELECT institution_name FROM _hits WHERE author_id = ?", [aid]).fetchall()
            log(f"  {aid} (h={h}, works={w}, n_inst={n}):")
            log(f"    {[a[0] for a in affs]}")
            log("")

        con.execute(f"COPY _hits TO '{OUT_CSV}' (FORMAT CSV, HEADER TRUE)")
        log(f"Wrote {OUT_CSV}")
        log(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
