#!/usr/bin/env python3
"""
Build the H2 dataset from the pre-filtered local parquet produced by prefetch.py.

Steps:
  3. Build per-author table (id, h_index, works_count, institution_id, institution_name, field)
  4. Compute H2 per (institution_id, field)
  5. Write authors.csv and h2_by_institution_field.csv
  6. Sanity checks

works_count carries through from prefetch.py's top-level works_count column
(the T in Egghe's 2008 author-article IPP) purely so estimate_alphas.py can
fit alpha_1 later; it isn't used anywhere else in this script.

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
H2_SUBFIELD_CSV = os.path.join(INTERIM_DIR, "h2_by_institution_subfield.csv")


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
    expr = f"SELECT id, h_index, works_count, affiliations, topics FROM read_parquet('{f}')"
    if chunk_idx is not None:
        expr += f" WHERE hash(id) % {n_chunks} = {chunk_idx}"
    return expr


def _batch_sql(batch):
    """Build SELECT SQL for a batch.

    Unchunked files are passed as a list to a single read_parquet() call so
    DuckDB opens them sequentially rather than all at once (avoiding EMFILE
    when a batch contains hundreds of small files).  Chunked parts keep their
    individual SELECT … WHERE hash(id) % n = i expressions and are UNION ALL'd
    in the normal way.
    """
    unchunked = [p for p in batch if p[2] is None]
    chunked   = [p for p in batch if p[2] is not None]

    segments = []
    if unchunked:
        files_list = ", ".join(f"'{p[0]}'" for p in unchunked)
        segments.append(
            f"SELECT id, h_index, works_count, affiliations, topics"
            f" FROM read_parquet([{files_list}])"
        )
    for p in chunked:
        segments.append(_read_expr(p))

    return "\n            UNION ALL\n            ".join(segments)


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
        union_sql = _batch_sql(batch)
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
                SELECT id AS author_id, h_index, works_count,
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
            SELECT author_id, h_index, works_count, institution_id, institution_name
            FROM ranked
            WHERE rnk = 1
        """)
        print(f"{con.execute('SELECT COUNT(*) FROM _inst').fetchone()[0]:,} rows")

        print("    _unnested...", end=" ", flush=True)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _unnested AS
            SELECT id AS author_id,
                   tp.field.id              AS field_id,
                   tp.field.display_name    AS field_name,
                   tp.subfield.id           AS subfield_id,
                   tp.subfield.display_name AS subfield_name,
                   tp.domain.id             AS domain_id,
                   tp.domain.display_name   AS domain_name,
                   tp.id                    AS topic_id,
                   tp.display_name          AS topic_name,
                   tp.count                 AS cnt
            FROM _raw
            CROSS JOIN LATERAL UNNEST(topics) AS t(tp)
            WHERE tp.field.id IS NOT NULL
        """)
        print(f"{con.execute('SELECT COUNT(*) FROM _unnested').fetchone()[0]:,} rows")

        print("    _modal...", end=" ", flush=True)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _modal AS
            WITH field_sums AS (
                SELECT author_id, field_id, field_name, SUM(cnt) AS total
                FROM _unnested GROUP BY author_id, field_id, field_name
            ),
            subfield_sums AS (
                SELECT author_id, subfield_id, subfield_name, SUM(cnt) AS total
                FROM _unnested WHERE subfield_id IS NOT NULL
                GROUP BY author_id, subfield_id, subfield_name
            ),
            domain_sums AS (
                SELECT author_id, domain_id, domain_name, SUM(cnt) AS total
                FROM _unnested WHERE domain_id IS NOT NULL
                GROUP BY author_id, domain_id, domain_name
            ),
            topic_sums AS (
                SELECT author_id, topic_id, topic_name, SUM(cnt) AS total
                FROM _unnested WHERE topic_id IS NOT NULL
                GROUP BY author_id, topic_id, topic_name
            )
            SELECT mf.author_id,
                   mf.field,       mf.field_name,
                   ms.subfield,    ms.subfield_name,
                   md.domain,      md.domain_name,
                   mt.topic,       mt.topic_name
            FROM (
                SELECT author_id,
                       arg_max({'id': field_id, 'name': field_name}, total)['id']   AS field,
                       arg_max({'id': field_id, 'name': field_name}, total)['name'] AS field_name
                FROM field_sums GROUP BY author_id
            ) mf
            LEFT JOIN (
                SELECT author_id,
                       arg_max({'id': subfield_id, 'name': subfield_name}, total)['id']   AS subfield,
                       arg_max({'id': subfield_id, 'name': subfield_name}, total)['name'] AS subfield_name
                FROM subfield_sums GROUP BY author_id
            ) ms USING (author_id)
            LEFT JOIN (
                SELECT author_id,
                       arg_max({'id': domain_id, 'name': domain_name}, total)['id']   AS domain,
                       arg_max({'id': domain_id, 'name': domain_name}, total)['name'] AS domain_name
                FROM domain_sums GROUP BY author_id
            ) md USING (author_id)
            LEFT JOIN (
                SELECT author_id,
                       arg_max({'id': topic_id, 'name': topic_name}, total)['id']   AS topic,
                       arg_max({'id': topic_id, 'name': topic_name}, total)['name'] AS topic_name
                FROM topic_sums GROUP BY author_id
            ) mt USING (author_id)
        """)
        print(f"{con.execute('SELECT COUNT(*) FROM _modal').fetchone()[0]:,} rows")

        batch_sql = """
            SELECT i.author_id, i.h_index, i.works_count, i.institution_id, i.institution_name,
                   m.field, m.field_name,
                   m.subfield, m.subfield_name,
                   m.domain, m.domain_name,
                   m.topic, m.topic_name
            FROM _inst i JOIN _modal m USING (author_id)
        """
        print("    authors...", end=" ", flush=True)
        if not authors_created:
            con.execute(f"CREATE TABLE authors AS {batch_sql}")
            authors_created = True
        else:
            con.execute(f"INSERT INTO authors {batch_sql}")
        print("ok")

        con.execute("DROP TABLE _raw; DROP TABLE _inst; DROP TABLE _unnested; DROP TABLE _modal;")

    con.execute("SET enable_progress_bar=true;")
    print()
    n = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    print(f"  Authors (education + h_index > 0 + field): {n:,}  ({time.time()-t0:.0f}s)")


def step3b_normalize_institution_names(con):
    print("Step 3b: Normalizing institution names...")
    t0 = time.time()
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _canonical_names AS
        SELECT institution_id, arg_max(institution_name, cnt) AS institution_name
        FROM (
            SELECT institution_id, institution_name, COUNT(*) AS cnt
            FROM authors
            GROUP BY institution_id, institution_name
        )
        GROUP BY institution_id
    """)
    con.execute("""
        UPDATE authors
        SET institution_name = c.institution_name
        FROM _canonical_names c
        WHERE authors.institution_id = c.institution_id
    """)
    con.execute("DROP TABLE _canonical_names")
    print(f"  Done  ({time.time()-t0:.0f}s)")


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


def step4b_compute_h2_subfield(con):
    print("Step 4b: Computing H2 index by subfield...")
    t0 = time.time()

    con.execute("""
        CREATE OR REPLACE TABLE h2_by_institution_subfield AS
        WITH ranked AS (
            SELECT institution_id, institution_name, subfield, subfield_name, h_index,
                ROW_NUMBER() OVER (
                    PARTITION BY institution_id, subfield
                    ORDER BY h_index DESC
                ) AS rank_desc
            FROM authors
            WHERE subfield IS NOT NULL
        ),
        h2_candidates AS (
            SELECT institution_id, subfield,
                   arg_max(institution_name, rank_desc) AS institution_name,
                   arg_max(subfield_name,    rank_desc) AS subfield_name,
                   MAX(rank_desc)                       AS h2
            FROM ranked
            WHERE h_index >= rank_desc
            GROUP BY institution_id, subfield
        ),
        author_counts AS (
            SELECT institution_id, subfield, COUNT(*) AS author_count
            FROM authors
            WHERE subfield IS NOT NULL
            GROUP BY institution_id, subfield
        )
        SELECT
            h.institution_id,
            h.institution_name,
            h.subfield,
            h.subfield_name,
            h.h2,
            a.author_count
        FROM h2_candidates h
        JOIN author_counts a USING (institution_id, subfield)
        ORDER BY h2 DESC, institution_name, subfield_name
    """)

    n = con.execute("SELECT COUNT(*) FROM h2_by_institution_subfield").fetchone()[0]
    print(f"  (institution, subfield) pairs: {n:,}  ({time.time()-t0:.0f}s)")


def step5_write_outputs(con):
    print("Step 5: Writing output CSVs...")
    os.makedirs(INTERIM_DIR, exist_ok=True)
    con.execute(f"COPY authors TO '{AUTHORS_CSV}' (HEADER, DELIMITER ',')")
    print(f"  Wrote {AUTHORS_CSV}")
    con.execute(f"COPY h2_by_institution_field TO '{H2_CSV}' (HEADER, DELIMITER ',')")
    print(f"  Wrote {H2_CSV}")
    con.execute(f"COPY h2_by_institution_subfield TO '{H2_SUBFIELD_CSV}' (HEADER, DELIMITER ',')")
    print(f"  Wrote {H2_SUBFIELD_CSV}")


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

    print("\nTop 10 (institution, subfield) by H2:")
    rows = con.execute("""
        SELECT institution_name, subfield_name, h2, author_count
        FROM h2_by_institution_subfield ORDER BY h2 DESC LIMIT 10
    """).fetchall()
    print(f"  {'Institution':<45} {'Subfield':<40} {'H2':>4} {'Authors':>8}")
    print("  " + "-" * 101)
    for r in rows:
        print(f"  {str(r[0])[:44]:<45} {str(r[1])[:39]:<40} {r[2]:>4} {r[3]:>8,}")

    n_subfields = con.execute(
        "SELECT COUNT(DISTINCT subfield) FROM h2_by_institution_subfield"
    ).fetchone()[0]
    print(f"\nDistinct subfields in h2_by_institution_subfield: {n_subfields}")


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
    step3b_normalize_institution_names(con)
    step4_compute_h2(con)
    step4b_compute_h2_subfield(con)
    step5_write_outputs(con)
    step6_sanity_checks(con)
    print("\nDone.")
