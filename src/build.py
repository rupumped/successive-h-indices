#!/usr/bin/env python3
"""
Build the H2 dataset from the pre-filtered local parquet produced by prefetch.py.

Steps:
  3. Build per-author table (id, h_index, institution_id, institution_name, field)
  4. Compute H2 per (institution_id, field)
  5. Write authors.csv and h2_by_institution_field.csv
  6. Sanity checks

Usage:
  python3 build.py
"""

import duckdb
import glob as _glob
import math
import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
INTERIM_DIR = os.path.join(DATA_DIR, "interim")
# Use the consolidated file if present; otherwise read directly from staging.
_consolidated = os.path.join(DATA_DIR, "authors_filtered.parquet")
_staging_glob = os.path.join(DATA_DIR, "authors_staging", "*.parquet")
FILTERED_PARQUET = _consolidated if os.path.exists(_consolidated) else _staging_glob
AUTHORS_CSV = os.path.join(INTERIM_DIR, "authors.csv")
H2_CSV = os.path.join(INTERIM_DIR, "h2_by_institution_field.csv")


def connect():
    db = os.path.join(DATA_DIR, "openalex.duckdb")
    con = duckdb.connect(database=db)
    con.execute("SET threads=4; SET memory_limit='4GB';")
    con.execute(f"SET temp_directory='{DATA_DIR}';")
    con.execute("SET enable_progress_bar=true;")
    con.execute("SET preserve_insertion_order=false;")
    return con


MAX_BATCH_MB = 50  # cap per batch so _modal's unnested hash table stays under 4 GB


def _source_files():
    if "*" in FILTERED_PARQUET:
        return sorted(_glob.glob(FILTERED_PARQUET))
    return [FILTERED_PARQUET]


def _make_batches(files):
    """Group files into batches capped at MAX_BATCH_MB each.

    A file larger than MAX_BATCH_MB on its own is split into row-hash
    buckets (hash(id) % n_chunks) rather than combined with others —
    _modal's unnested hash table scales with row count, not file count,
    so an oversized single file must be cut down too, not just grouped.
    """
    parts = []  # (file, n_chunks, chunk_idx or None, mb)
    for f in files:
        mb = os.path.getsize(f) / 1e6
        if mb <= MAX_BATCH_MB:
            parts.append((f, 1, None, mb))
        else:
            n_chunks = math.ceil(mb / MAX_BATCH_MB)
            for i in range(n_chunks):
                parts.append((f, n_chunks, i, mb / n_chunks))

    batches, current, current_mb = [], [], 0
    for part in parts:
        mb = part[3]
        if current and current_mb + mb > MAX_BATCH_MB:
            batches.append(current)
            current, current_mb = [], 0
        current.append(part)
        current_mb += mb
    if current:
        batches.append(current)
    return batches


def _read_expr(part):
    f, n_chunks, chunk_idx, _mb = part
    expr = f"SELECT id, h_index, affiliations, topics FROM read_parquet('{f}')"
    if chunk_idx is not None:
        expr += f" WHERE hash(id) % {n_chunks} = {chunk_idx}"
    return expr


def step3_build_authors(con):
    print("Step 3: Building per-author dataset...")
    t0 = time.time()
    con.execute("SET enable_progress_bar=false;")

    files = _source_files()
    batches = _make_batches(files)
    n_batches = len(batches)

    con.execute("DROP TABLE IF EXISTS authors")
    authors_created = False

    for b, batch in enumerate(batches):
        batch_mb = sum(part[3] for part in batch)
        start = sum(len(batches[i]) for i in range(b))
        print(f"  Batch {b+1}/{n_batches}  parts {start+1}–{start+len(batch)}  ({batch_mb:.0f} MB)  [{batch[0][0].split('=')[-1]} … {batch[-1][0].split('=')[-1]}]")

        print("    _raw...", end=" ", flush=True)
        union_sql = "\n            UNION ALL\n            ".join(_read_expr(part) for part in batch)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _raw AS
            {union_sql}
        """)
        raw_n = con.execute("SELECT COUNT(*) FROM _raw").fetchone()[0]
        print(f"{raw_n:,} rows")

        # Each author is assigned their most recent education affiliation:
        # among affiliations with institution.type = 'education', rank by the
        # latest publication year in that affiliation's years[] (ties broken
        # by smallest institution id for determinism).
        print("    _inst...", end=" ", flush=True)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _inst AS
            WITH edu AS (
                SELECT id AS author_id, h_index,
                       aff.institution.id           AS institution_id,
                       aff.institution.display_name AS institution_name,
                       list_max(aff.years)          AS latest_year
                FROM _raw
                CROSS JOIN LATERAL UNNEST(affiliations) AS t(aff)
                WHERE aff.institution.type = 'education'
            ),
            ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY author_id
                           ORDER BY latest_year DESC NULLS LAST, institution_id
                       ) AS rnk
                FROM edu
            )
            SELECT author_id, h_index, institution_id, institution_name
            FROM ranked
            WHERE rnk = 1
        """)
        print(f"{con.execute('SELECT COUNT(*) FROM _inst').fetchone()[0]:,} rows")

        print("    _modal...", end=" ", flush=True)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _modal AS
            WITH sums AS (
                SELECT id AS author_id,
                       tp.field.id             AS field_id,
                       tp.field.display_name   AS field_name,
                       SUM(tp.count)           AS cnt
                FROM _raw
                CROSS JOIN LATERAL UNNEST(topics) AS t(tp)
                WHERE tp.field.id IS NOT NULL
                GROUP BY id, tp.field.id, tp.field.display_name
            )
            SELECT author_id,
                   arg_max({'id': field_id, 'name': field_name}, cnt)['id']   AS field,
                   arg_max({'id': field_id, 'name': field_name}, cnt)['name'] AS field_name
            FROM sums
            GROUP BY author_id
        """)
        print(f"{con.execute('SELECT COUNT(*) FROM _modal').fetchone()[0]:,} rows")

        batch_sql = """
            SELECT i.author_id, i.h_index, i.institution_id, i.institution_name,
                   m.field, m.field_name
            FROM _inst i JOIN _modal m USING (author_id)
        """
        print("    authors...", end=" ", flush=True)
        if not authors_created:
            con.execute(f"CREATE TABLE authors AS {batch_sql}")
            authors_created = True
        else:
            con.execute(f"INSERT INTO authors {batch_sql}")
        print("ok")

        con.execute("DROP TABLE _raw; DROP TABLE _inst; DROP TABLE _modal;")

    con.execute("SET enable_progress_bar=true;")
    print()
    n = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    print(f"  Authors (education + h_index > 0 + field): {n:,}  ({time.time()-t0:.0f}s)")


def step4_compute_h2(con):
    print("Step 4: Computing H2 index...")
    t0 = time.time()

    con.execute("""
        CREATE OR REPLACE TABLE h2_by_institution_field AS
        WITH
        ranked AS (
            SELECT
                institution_id, institution_name, field, field_name, h_index,
                ROW_NUMBER() OVER (
                    PARTITION BY institution_id, field
                    ORDER BY h_index DESC
                ) AS rank_desc
            FROM authors
        ),
        -- H2 = largest rank where h_index >= rank (same algorithm as h-index itself).
        -- Group by (institution_id, field) only — excluding institution_name/field_name
        -- prevents name-variant strings across batches from splitting one institution
        -- into multiple groups, each seeing only a subset of the ranked list.
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
            FROM authors
            GROUP BY institution_id, field
        )
        SELECT
            h.institution_id,
            h.institution_name,
            h.field,
            h.field_name,
            h.h2,
            a.author_count
        FROM h2_candidates h
        JOIN author_counts a USING (institution_id, field)
        ORDER BY h2 DESC, institution_name, field_name
    """)

    n = con.execute("SELECT COUNT(*) FROM h2_by_institution_field").fetchone()[0]
    print(f"  (institution, field) pairs: {n:,}  ({time.time()-t0:.0f}s)")


def step5_write_outputs(con):
    print("Step 5: Writing output CSVs...")
    os.makedirs(INTERIM_DIR, exist_ok=True)
    con.execute(f"COPY authors TO '{AUTHORS_CSV}' (HEADER, DELIMITER ',')")
    print(f"  Wrote {AUTHORS_CSV}")
    con.execute(f"COPY h2_by_institution_field TO '{H2_CSV}' (HEADER, DELIMITER ',')")
    print(f"  Wrote {H2_CSV}")


def step6_sanity_checks(con):
    print("\nStep 6: Sanity checks")
    print("=" * 60)

    print("\nH2 value distribution (percentiles):")
    row = con.execute("""
        SELECT
            MIN(h2),
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY h2),
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY h2),
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY h2),
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY h2),
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY h2),
            MAX(h2)
        FROM h2_by_institution_field
    """).fetchone()
    for label, val in zip(["min", "p25", "p50", "p75", "p90", "p99", "max"], row):
        print(f"  {label:>4}: {val}")

    print("\nTop 20 (institution, field) by H2:")
    rows = con.execute("""
        SELECT institution_name, field_name, h2, author_count
        FROM h2_by_institution_field ORDER BY h2 DESC LIMIT 20
    """).fetchall()
    print(f"  {'Institution':<45} {'Field':<35} {'H2':>4} {'Authors':>8}")
    print("  " + "-" * 96)
    for r in rows:
        print(f"  {str(r[0])[:44]:<45} {str(r[1])[:34]:<35} {r[2]:>4} {r[3]:>8,}")

    print("\nSpot-check — well-known US research universities:")
    for name in ["Harvard University", "Massachusetts Institute of Technology",
                 "Stanford University", "University of California, Berkeley",
                 "Johns Hopkins University"]:
        rows = con.execute("""
            SELECT field_name, h2, author_count
            FROM h2_by_institution_field
            WHERE institution_name ILIKE $name
            ORDER BY h2 DESC LIMIT 5
        """, {"name": f"%{name}%"}).fetchall()
        if rows:
            print(f"\n  {name}:")
            for r in rows:
                print(f"    {r[0]:<38} H2={r[1]:>3}  ({r[2]:,} authors)")
        else:
            print(f"\n  {name}: not found")

    small = con.execute(
        "SELECT COUNT(*) FROM h2_by_institution_field WHERE author_count < 10"
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM h2_by_institution_field").fetchone()[0]
    print(f"\nGroups with < 10 authors: {small:,} / {total:,} ({100*small/total:.1f}%) — H2 unreliable at small n")

    max_h2 = con.execute("SELECT MAX(h2) FROM h2_by_institution_field").fetchone()[0]
    if max_h2 > 200:
        print(f"\nWARNING: Max H2 = {max_h2} — suspiciously high, review top entries.")
    elif max_h2 < 5:
        print(f"\nWARNING: Max H2 = {max_h2} — suspiciously low, check data coverage.")
    else:
        print(f"\nMax H2 = {max_h2} — within plausible range.")


if __name__ == "__main__":
    import glob as _glob
    staging_files = _glob.glob(_staging_glob)
    if not os.path.exists(_consolidated) and not staging_files:
        print("ERROR: No data found. Run prefetch.py first.")
        sys.exit(1)

    if FILTERED_PARQUET == _staging_glob:
        print(f"Source: {len(staging_files)} staging files in {os.path.dirname(_staging_glob)}")
    else:
        size_mb = os.path.getsize(FILTERED_PARQUET) / 1e6
        print(f"Source: {FILTERED_PARQUET} ({size_mb:.0f} MB)")

    con = connect()
    step3_build_authors(con)
    step4_compute_h2(con)
    step5_write_outputs(con)
    step6_sanity_checks(con)
    print("\nDone.")
