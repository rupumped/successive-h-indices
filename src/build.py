#!/usr/bin/env python3
"""
Build the H2 dataset from the pre-filtered local parquet produced by prefetch.py.

Steps:
  2. Primary institution per author, from prefetch_works.py's authorship counts
     (--attribution primary only)
  3. Build per-author table (id, h_index, works_count, institution_id, institution_name, field)
  4. Compute H2 per (institution_id, field)
  5. Write authors.csv and h2_by_institution_field.csv
  6. Sanity checks

Institutional attribution (--attribution):
  primary (default)  The education institution credited on the largest number
                     of the author's own authorships in their last
                     PRIMARY_WINDOW publishing years (last publication year
                     and the four before it), provided it is credited on
                     >= PRIMARY_MIN_PAPERS of them and on >= PRIMARY_MIN_SHARE
                     of the share denominator. Ties go to the institution
                     seen most recently, then most often over the whole
                     career, then smallest id. Authors with no institution
                     meeting the thresholds are excluded. Affiliation order on
                     the paper is deliberately not used (see
                     affiliation_order_check.py).
                     Two switches (see prefetch_works.py for definitions):
                       --rollup / --no-rollup   credit education ancestors
                           of non-education institutions (JPL -> Caltech).
                           Default on.
                       --share-of edu|all       denominator for the share
                           threshold: the author's works in the window that
                           credit any education institution (default), or all
                           their works in the window. "all" excludes
                           hospital- and institute-based faculty whose papers
                           mostly list only the hospital (e.g. Dana-Farber).
  recent             The previous rule: the education affiliation with the
                     latest year in the author record's affiliations[].years.

Outputs for the default configuration have no suffix; any other configuration
gets one (_recent, _norollup, _shareall, _norollup_shareall) so sensitivity
runs don't overwrite the main results.

works_count carries through from prefetch.py's top-level works_count column
(the T in Egghe's 2008 author-article IPP) purely so estimate_alphas.py can
fit alpha_1 later; it isn't used anywhere else in this script.

Usage:
  python3 build.py                        # primary, rollup, share of edu works
  python3 build.py --no-rollup            # sensitivity: direct credit only
  python3 build.py --share-of all         # sensitivity: share of all works
  python3 build.py --attribution recent   # most-recent-affiliation rule
  python3 build.py --memory-gb 16         # DuckDB memory limit (default 3)
Step 2 is cached in openalex.duckdb and recomputed automatically when the
configuration changes, or on --rebuild-primary.
"""

import argparse
import duckdb
import glob as _glob
import math
import os
import shutil
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

WORKS_STAGING_DIR = os.path.join(DATA_DIR, "works_staging")
WORKS_BUCKET_DIR = os.path.join(DATA_DIR, "works_buckets")
PRIMARY_WINDOW = 5         # publishing years, counting the author's last one
PRIMARY_MIN_PAPERS = 2
PRIMARY_MIN_SHARE = 0.10
# Publication years after the snapshot year are data errors; left in, they
# would drag an author's window into years with no real output.
MAX_YEAR = 2026            # year of the works snapshot (updated_date=2026-09-23)
N_BUCKETS = 64             # ~25M authorship-count rows per bucket; fits in 3 GB


def connect(memory_gb=3):
    # 4 GB was OOM-killed on a 7 GB machine (DuckDB's RSS overshoots its
    # limit, and the OS and editor need the rest).
    db = os.path.join(DATA_DIR, "openalex.duckdb")
    con = duckdb.connect(database=db)
    con.execute(f"SET threads=4; SET memory_limit='{memory_gb:g}GB';")
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


def check_works_staging_complete():
    """Exit unless every works file on S3 has a current-schema staging output
    (needs network)."""
    from prefetch_works import list_files, staging_path, staging_ok
    probe = duckdb.connect()
    missing = [k for k, _ in list_files() if not staging_ok(staging_path(k), probe)]
    probe.close()
    if missing:
        sys.exit(f"ERROR: {len(missing)} works file(s) missing or outdated in "
                 f"{WORKS_STAGING_DIR}. Finish prefetch_works.py, or pass "
                 "--allow-incomplete-works.")


def primary_config(rollup, share_of):
    return (f"rollup={rollup} share_of={share_of} window={PRIMARY_WINDOW} "
            f"min_papers={PRIMARY_MIN_PAPERS} min_share={PRIMARY_MIN_SHARE} "
            f"max_year={MAX_YEAR}")


def cached_primary_config(con):
    try:
        return con.execute("SELECT config FROM primary_institution_config").fetchone()[0]
    except duckdb.Error:
        return None


def step2_primary_institutions(con, rollup=True, share_of="edu", rebuild=False,
                               staging_glob=None):
    """Build table primary_institution: one row per author in the works staging.

    Columns: author_id, last_year, n_all (distinct works in the window),
    n_denom (share denominator: n_all, or works in the window crediting any
    education institution, per share_of), institution_id / n_inst /
    latest_year / n_career for the top-ranked education institution (NULL if
    the window credits none), and passes (meets PRIMARY_MIN_PAPERS and
    PRIMARY_MIN_SHARE). Only rows with passes = true are used for
    attribution; the rest are kept for diagnostics. The configuration it was
    built with is stored in primary_institution_config, and the table is
    rebuilt whenever that differs from the requested one.

    Staging rows are per (author, year[, institution]) counts from
    prefetch_works.py, one set per source works file. Each work lives in
    exactly one snapshot partition, so per-file counts sum correctly across
    files. The ~1.6B staging rows are hash-partitioned by author into
    N_BUCKETS once (kept in data/works_buckets/ so sensitivity runs with a
    different configuration skip this pass), so each bucket's aggregation
    fits in memory.
    """
    config = primary_config(rollup, share_of)
    if not rebuild and cached_primary_config(con) == config:
        print(f"Step 2: Reusing primary_institution table ({config}).")
        return
    print(f"Step 2: Computing primary institutions ({config})...")
    t0 = time.time()
    staging_glob = staging_glob or os.path.join(WORKS_STAGING_DIR, "*.parquet")
    n_col = "n_rollup" if rollup else "n_direct"
    denom_col = "n_all" if share_of == "all" else n_col

    complete_marker = os.path.join(WORKS_BUCKET_DIR, "_COMPLETE")
    if rebuild or not os.path.exists(complete_marker):
        print(f"  Partitioning by author into {N_BUCKETS} buckets...", end=" ", flush=True)
        if os.path.exists(WORKS_BUCKET_DIR):
            shutil.rmtree(WORKS_BUCKET_DIR)
        con.execute(f"""
            COPY (
                SELECT author_id, year, institution_id, n_all, n_direct, n_rollup,
                       hash(author_id) % {N_BUCKETS} AS bucket
                FROM read_parquet('{staging_glob}')
                WHERE year <= {MAX_YEAR}
            ) TO '{WORKS_BUCKET_DIR}' (FORMAT PARQUET, PARTITION_BY (bucket), COMPRESSION ZSTD)
        """)
        open(complete_marker, "w").close()
        print(f"({time.time()-t0:.0f}s)")
    else:
        print(f"  Reusing author buckets in {WORKS_BUCKET_DIR} (--rebuild-primary to redo).")

    con.execute("""
        CREATE OR REPLACE TABLE primary_institution (
            author_id VARCHAR, last_year INTEGER, n_all INTEGER, n_denom INTEGER,
            institution_id VARCHAR, n_inst INTEGER, latest_year INTEGER,
            n_career INTEGER, passes BOOLEAN
        )
    """)
    con.execute("DROP TABLE IF EXISTS primary_institution_config")
    for b in range(N_BUCKETS):
        print(f"\r  Aggregating bucket {b+1}/{N_BUCKETS}...", end="", flush=True)
        if not os.path.isdir(os.path.join(WORKS_BUCKET_DIR, f"bucket={b}")):
            continue   # no authors hashed here (only happens on small inputs)
        con.execute(f"""
            INSERT INTO primary_institution
            WITH c AS (
                SELECT author_id, year, institution_id,
                       SUM(n_all) AS n_all, SUM({n_col}) AS n_inst, SUM({denom_col}) AS n_denom
                FROM read_parquet('{WORKS_BUCKET_DIR}/bucket={b}/*.parquet')
                GROUP BY ALL
            ),
            last AS (
                SELECT author_id, MAX(year) AS last_year
                FROM c WHERE institution_id IS NULL GROUP BY author_id
            ),
            win AS (
                SELECT c.* FROM c JOIN last USING (author_id)
                WHERE c.year > last.last_year - {PRIMARY_WINDOW}
            ),
            tot AS (
                SELECT author_id, SUM(n_all) AS n_all, SUM(n_denom) AS n_denom
                FROM win WHERE institution_id IS NULL GROUP BY author_id
            ),
            career AS (
                SELECT author_id, institution_id, SUM(n_inst) AS n_career
                FROM c WHERE institution_id IS NOT NULL GROUP BY ALL
            ),
            ranked AS (
                SELECT w.author_id, w.institution_id, SUM(w.n_inst) AS n_inst,
                       MAX(w.year) AS latest_year, ANY_VALUE(k.n_career) AS n_career,
                       ROW_NUMBER() OVER (
                           PARTITION BY w.author_id
                           ORDER BY SUM(w.n_inst) DESC, MAX(w.year) DESC,
                                    ANY_VALUE(k.n_career) DESC, w.institution_id
                       ) AS rnk
                FROM win w JOIN career k USING (author_id, institution_id)
                WHERE w.institution_id IS NOT NULL AND w.n_inst > 0
                GROUP BY w.author_id, w.institution_id
            )
            SELECT l.author_id, l.last_year, t.n_all, t.n_denom,
                   r.institution_id, r.n_inst, r.latest_year, r.n_career,
                   COALESCE(r.n_inst >= {PRIMARY_MIN_PAPERS}
                            AND r.n_inst >= {PRIMARY_MIN_SHARE} * t.n_denom, false) AS passes
            FROM last l
            JOIN tot t USING (author_id)
            LEFT JOIN (SELECT * FROM ranked WHERE rnk = 1) r USING (author_id)
        """)
    print()
    con.execute("CREATE TABLE primary_institution_config AS SELECT ? AS config", [config])

    n, n_edu, n_pass, n_few, n_share = con.execute(f"""
        SELECT COUNT(*),
               COUNT(institution_id),
               COUNT(*) FILTER (WHERE passes),
               COUNT(*) FILTER (WHERE institution_id IS NOT NULL AND n_inst < {PRIMARY_MIN_PAPERS}),
               COUNT(*) FILTER (WHERE institution_id IS NOT NULL AND n_inst >= {PRIMARY_MIN_PAPERS}
                                AND NOT passes)
        FROM primary_institution
    """).fetchone()
    print(f"  Authors in works staging:                 {n:>12,}")
    print(f"    with an education institution in window: {n_edu:>10,}")
    print(f"    failing min papers ({PRIMARY_MIN_PAPERS}):                {n_few:>10,}")
    print(f"    failing min share ({PRIMARY_MIN_SHARE:.0%}):               {n_share:>10,}")
    print(f"    assigned a primary institution:          {n_pass:>10,}  ({time.time()-t0:.0f}s)")


def step3_build_authors(con, attribution="primary"):
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

        print("    _inst...", end=" ", flush=True)
        if attribution == "primary":
            # Institution from step 2. The name comes from the author's own
            # affiliations[] when present there; otherwise it's left NULL and
            # filled with the canonical name in step 3b.
            con.execute("""
                CREATE OR REPLACE TEMP TABLE _inst AS
                WITH names AS (
                    SELECT id AS author_id,
                           aff.institution.id AS institution_id,
                           ANY_VALUE(aff.institution.display_name) AS institution_name
                    FROM _raw
                    CROSS JOIN LATERAL UNNEST(affiliations) AS t(aff)
                    WHERE aff.institution.type = 'education'
                    GROUP BY ALL
                )
                SELECT r.id AS author_id, r.h_index, r.works_count,
                       p.institution_id, n.institution_name
                FROM _raw r
                JOIN primary_institution p ON p.author_id = r.id AND p.passes
                LEFT JOIN names n ON n.author_id = r.id AND n.institution_id = p.institution_id
            """)
        else:
            # Each author is assigned their most recent education affiliation:
            # among affiliations with institution.type = 'education', rank by the
            # latest publication year in that affiliation's years[] (ties broken
            # by smallest institution id for determinism).
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
            WHERE institution_name IS NOT NULL
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
    # Primary institutions absent from every assigned author's own
    # affiliations[] have no name source at all.
    unnamed = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT institution_id) FROM authors WHERE institution_name IS NULL"
    ).fetchone()
    if unnamed[0]:
        print(f"  {unnamed[0]:,} authors at {unnamed[1]:,} institutions still have no name")
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--attribution", choices=["primary", "recent"], default="primary")
    ap.add_argument("--rebuild-primary", action="store_true",
                    help="recompute the primary_institution table from works staging")
    ap.add_argument("--allow-incomplete-works", action="store_true",
                    help="skip the check that every works file has been prefetched")
    ap.add_argument("--rollup", action=argparse.BooleanOptionalAction, default=True,
                    help="credit education ancestors of non-education institutions")
    ap.add_argument("--share-of", choices=["edu", "all"], default="edu",
                    help="share-threshold denominator: works crediting any education "
                         "institution (edu) or all works (all)")
    ap.add_argument("--memory-gb", type=float, default=3,
                    help="DuckDB memory limit; leave ~3-4 GB of RAM for everything else")
    args = ap.parse_args()

    if args.attribution == "recent":
        suffix = "_recent"
    else:
        suffix = ("" if args.rollup else "_norollup") + ("_shareall" if args.share_of == "all" else "")
    if suffix:
        AUTHORS_CSV, H2_CSV, H2_SUBFIELD_CSV = (
            p.replace(".csv", f"{suffix}.csv") for p in (AUTHORS_CSV, H2_CSV, H2_SUBFIELD_CSV))
        print(f"Non-default configuration: outputs get suffix '{suffix}'.")

    staging_files = _glob.glob(_staging_glob)
    if not os.path.exists(_consolidated) and not staging_files:
        print("ERROR: No data found. Run prefetch.py first.")
        sys.exit(1)

    if FILTERED_PARQUET == _staging_glob:
        print(f"Source: {len(staging_files)} staging files in {os.path.dirname(_staging_glob)}")
    else:
        size_mb = os.path.getsize(FILTERED_PARQUET) / 1e6
        print(f"Source: {FILTERED_PARQUET} ({size_mb:.0f} MB)")

    con = connect(args.memory_gb)
    if args.attribution == "primary":
        needs_step2 = (args.rebuild_primary
                       or cached_primary_config(con) != primary_config(args.rollup, args.share_of))
        if needs_step2 and not args.allow_incomplete_works:
            check_works_staging_complete()
        step2_primary_institutions(con, rollup=args.rollup, share_of=args.share_of,
                                   rebuild=args.rebuild_primary)
    step3_build_authors(con, attribution=args.attribution)
    step3b_normalize_institution_names(con)
    step4_compute_h2(con)
    step4b_compute_h2_subfield(con)
    step5_write_outputs(con)
    step6_sanity_checks(con)
    print("\nDone.")
