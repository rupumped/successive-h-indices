#!/usr/bin/env python3
"""
Manual validation check for reviewer round-2, issue 3/Tier 3: several
top-ranked institutions by efficiency (epsilon_2) are community colleges
with implausibly high h2 for a two-year teaching institution. Pulls the
full roster of authors listing each flagged institution as an educational
affiliation, plus each such author's complete list of educational
affiliations, to check whether these are genuine small research
populations or authors who list the community college for reasons
unrelated to research conducted there (e.g. as a secondary/demographic
affiliation alongside a real research-active institution).

Batched scan (mirrors build.py) to stay within this machine's memory
budget; filters to the four flagged institutions inside each batch so
per-batch work stays cheap.

Usage:
  python3 src/community_college_check.py
"""

import os
import sys
import time

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import _source_files, _make_batches, _batch_sql  # noqa: E402

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_CSV  = os.path.join(ROOT_DIR, "results", "community_college_check.csv")
LOG_PATH = os.path.join(ROOT_DIR, "results", "community_college_check.log")

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


def main():
    global _log_file
    with open(LOG_PATH, "w") as _log_file:
        t0 = time.time()
        con = duckdb.connect()
        con.execute("SET threads=4; SET memory_limit='4GB'; SET enable_progress_bar=false;")
        con.execute(f"SET temp_directory='{os.path.join(ROOT_DIR, 'data')}';")

        target_ids = "(" + ", ".join(f"'{v}'" for v in FLAGGED.values()) + ")"

        files = _source_files()
        batches = _make_batches(files)
        con.execute("DROP TABLE IF EXISTS _hits")
        created = False
        log(f"Scanning {len(files)} staging files in {len(batches)} batches, filtering to "
            f"{len(FLAGGED)} flagged institutions per batch...")
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
                flagged_authors AS (
                    SELECT DISTINCT author_id FROM edu WHERE institution_id IN {target_ids}
                )
                SELECT e.author_id, e.h_index, e.works_count, e.institution_id, e.institution_name
                FROM edu e
                JOIN flagged_authors fa USING (author_id)
            """)
            if not created:
                con.execute("CREATE TEMP TABLE _hits AS SELECT * FROM _hits_batch")
                created = True
            else:
                con.execute("INSERT INTO _hits SELECT * FROM _hits_batch")
            con.execute("DROP TABLE _hits_batch")
            if (b + 1) % 10 == 0 or (b + 1) == len(batches):
                log(f"  batch {b+1}/{len(batches)} done")

        log(f"\nScan complete ({time.time()-t0:.0f}s)\n")

        for name, iid in FLAGGED.items():
            log(f"=== {name} ({iid}) ===")
            rows = con.execute("""
                SELECT author_id, h_index, works_count
                FROM _hits
                WHERE institution_id = ?
                ORDER BY h_index DESC
                LIMIT 10
            """, [iid]).fetchall()
            log(f"  {'author_id':<35}{'h_index':>9}{'works_count':>13}")
            for aid, h, w in rows:
                log(f"  {aid:<35}{h:>9}{w:>13}")

            log("  All educational affiliations for these top authors:")
            top_author_ids = [r[0] for r in rows]
            for aid in top_author_ids[:5]:
                affs = con.execute("""
                    SELECT institution_name FROM _hits WHERE author_id = ?
                """, [aid]).fetchall()
                log(f"    {aid}: {[a[0] for a in affs]}")
            log("")

        con.execute(f"COPY _hits TO '{OUT_CSV}' (FORMAT CSV, HEADER TRUE)")
        log(f"Wrote {OUT_CSV}")
        log(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
