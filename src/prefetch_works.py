#!/usr/bin/env python3
"""
Stream the OpenAlex works snapshot from S3 and reduce it to per-author,
per-year authorship counts, for primary-institution attribution in build.py.

An author's primary institution is the education institution on the most of
their own authorships in their last five publishing years (last publication
year and the four before it), subject to minimum paper-count and share
thresholds applied in build.py. The authors snapshot can't support this: its
affiliations[] carries only the years an institution appears, not how many
works it appears on. Affiliation *order* within a paper is not used —
OpenAlex's authorships[].affiliations[] order disagrees with publisher
(Crossref / Europe PMC) order about half the time (see
affiliation_order_check.py).

Crediting education institutions on an authorship
-------------------------------------------------
  direct   institutions[] entries with type = 'education'.
  rollup   direct, plus the education-type *ancestors* (from lineage) of every
           non-education institution on the authorship: Jet Propulsion
           Laboratory -> Caltech, Ragon Institute -> Harvard and MIT. Education
           institutions are never rolled up themselves, so a UC Berkeley paper
           credits Berkeley, not also the University of California System.
Ancestor types come from the OpenAlex institutions snapshot, fetched once to
data/interim/institution_types.parquet.

Output rows, one parquet per source file in data/works_staging/:
  author_id, year, institution_id, n_all, n_direct, n_rollup
    institution_id NULL  -> author-year totals: n_all = distinct works;
                            n_direct / n_rollup = distinct works with >= 1
                            education institution credited under that rule
    institution_id set   -> n_all NULL; n_direct / n_rollup = distinct works
                            crediting this institution under that rule
                            (n_direct = 0 for rollup-only institutions)
Each work lives in exactly one snapshot partition, so per-file distinct-work
counts sum correctly across files.

The snapshot is ~2,000 files / ~700 GB, heavily skewed toward the newest
updated_date partition, so work is done per file rather than per partition.
Only id, publication_year, and authorships are read (DuckDB fetches just those
columns over HTTP range requests), which benchmarked faster than downloading
whole files first (~57s vs ~150s per 890 MB file). Each output is written to
a temp name and renamed on completion, so an existing staging file is always
complete; interrupted runs resume by skipping them. Staging files from before
the n_direct / n_rollup schema are detected and redone.

Usage:
  python3 prefetch_works.py                               # all files
  python3 prefetch_works.py --workers 4 --memory-gb 24    # on a larger machine
  python3 prefetch_works.py --limit 3                     # first N remaining files
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import duckdb
from tqdm import tqdm

S3_BUCKET = "s3://openalex"
S3_PREFIX = "data/parquet/works/"
S3_INSTITUTIONS = "s3://openalex/data/parquet/institutions/*/*.parquet"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGING_DIR = os.path.join(ROOT_DIR, "data", "works_staging")
INSTITUTION_TYPES = os.path.join(ROOT_DIR, "data", "interim", "institution_types.parquet")
EXPECTED_COLUMNS = {"author_id", "year", "institution_id", "n_all", "n_direct", "n_rollup"}

_stop = threading.Event()
_active = set()   # connections currently running a query, for interrupt()
_active_lock = threading.Lock()
_workers = 1
_memory_gb = 4.0  # total DuckDB memory budget, split across workers


def _handle_sigint(*_):
    if _stop.is_set():
        print("\nForced exit.")
        os._exit(1)
    _stop.set()
    print("\nInterrupt received — abandoning in-flight files and stopping. "
          "Press Ctrl+C again to force quit.")
    with _active_lock:
        for con in _active:
            con.interrupt()


def make_con():
    con = duckdb.connect()
    con.execute(f"SET threads=4; SET memory_limit='{_memory_gb / _workers:.1f}GB'; "
                "SET enable_progress_bar=false;")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-east-1';")
    con.execute("SET s3_access_key_id=''; SET s3_secret_access_key='';")
    return con


def fetch_institution_types():
    """Write data/interim/institution_types.parquet (id, type, lineage) once."""
    if os.path.exists(INSTITUTION_TYPES):
        return
    print("Fetching institution types from the OpenAlex institutions snapshot...")
    os.makedirs(os.path.dirname(INSTITUTION_TYPES), exist_ok=True)
    con = make_con()
    tmp = INSTITUTION_TYPES + ".tmp"
    con.execute(f"""
        COPY (SELECT id, "type", lineage FROM read_parquet('{S3_INSTITUTIONS}'))
        TO '{tmp}' (FORMAT PARQUET)
    """)
    os.replace(tmp, INSTITUTION_TYPES)
    n = con.execute(f"SELECT COUNT(*) FROM '{INSTITUTION_TYPES}'").fetchone()[0]
    print(f"  {n:,} institutions -> {INSTITUTION_TYPES}")


def list_files():
    """(s3_key, size) for every works parquet file, oldest partition first."""
    result = subprocess.run(
        ["aws", "s3", "ls", f"{S3_BUCKET}/{S3_PREFIX}", "--recursive",
         "--no-sign-request", "--region", "us-east-1"],
        capture_output=True, text=True, check=True,
    )
    files = sorted(
        (parts[3], int(parts[2]))
        for line in result.stdout.splitlines()
        if (parts := line.split()) and len(parts) == 4 and parts[3].endswith(".parquet")
    )
    if not files:
        sys.exit("ERROR: No works files found. Check AWS CLI and network access.")
    return files


def staging_path(key):
    # data/parquet/works/updated_date=2026-09-23/part_0001.parquet
    #   -> updated_date=2026-09-23__part_0001.parquet
    partition, name = key[len(S3_PREFIX):].split("/")
    return os.path.join(STAGING_DIR, f"{partition}__{name}")


def staging_ok(path, con):
    """True if path exists with the current schema (older files lack n_rollup)."""
    if not os.path.exists(path):
        return False
    try:
        cols = {r[0] for r in con.execute(
            f"SELECT * FROM read_parquet('{path}') LIMIT 0").description}
    except duckdb.Error:
        return False
    return EXPECTED_COLUMNS <= cols


def process_file(key):
    out = staging_path(key)
    tmp = out + ".tmp"
    con = make_con()
    with _active_lock:
        _active.add(con)
    try:
        con.execute(f"""
            CREATE TEMP TABLE edu_ids AS
            SELECT id FROM read_parquet('{INSTITUTION_TYPES}') WHERE "type" = 'education'
        """)
        con.execute(f"""
            COPY (
                WITH a AS MATERIALIZED (
                    SELECT w.id               AS work_id,
                           w.publication_year AS year,
                           au.author.id       AS author_id,
                           au.institutions    AS insts
                    FROM read_parquet('{S3_BUCKET}/{key}') w
                    CROSS JOIN LATERAL UNNEST(w.authorships) AS t(au)
                    WHERE au.author.id IS NOT NULL AND w.publication_year IS NOT NULL
                ),
                credit AS MATERIALIZED (
                    SELECT work_id, year, author_id, i.id AS institution_id, true AS direct
                    FROM a CROSS JOIN LATERAL UNNEST(insts) AS u(i)
                    WHERE i."type" = 'education'
                    UNION ALL
                    SELECT work_id, year, author_id, anc AS institution_id, false AS direct
                    FROM a CROSS JOIN LATERAL UNNEST(insts) AS u(i)
                    CROSS JOIN LATERAL UNNEST(list_filter(i.lineage, x -> x <> i.id)) AS v(anc)
                    WHERE i."type" IS DISTINCT FROM 'education'
                      AND anc IN (SELECT id FROM edu_ids)
                ),
                totals AS (
                    SELECT author_id, year, COUNT(DISTINCT work_id) AS n_all
                    FROM a GROUP BY ALL
                ),
                credited_totals AS (
                    SELECT author_id, year,
                           COUNT(DISTINCT work_id) FILTER (WHERE direct) AS n_direct,
                           COUNT(DISTINCT work_id)                      AS n_rollup
                    FROM credit GROUP BY ALL
                )
                SELECT t.author_id, t.year, NULL::VARCHAR AS institution_id,
                       t.n_all::INTEGER AS n_all,
                       COALESCE(c.n_direct, 0)::INTEGER AS n_direct,
                       COALESCE(c.n_rollup, 0)::INTEGER AS n_rollup
                FROM totals t LEFT JOIN credited_totals c USING (author_id, year)
                UNION ALL
                SELECT author_id, year, institution_id, NULL::INTEGER AS n_all,
                       COUNT(DISTINCT work_id) FILTER (WHERE direct)::INTEGER AS n_direct,
                       COUNT(DISTINCT work_id)::INTEGER                      AS n_rollup
                FROM credit GROUP BY ALL
            ) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        os.replace(tmp, out)
    finally:
        with _active_lock:
            _active.discard(con)
        con.close()
        if os.path.exists(tmp):
            os.remove(tmp)


def fmt_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def main():
    # Registered here, not at import, so build.py can import list_files /
    # staging_path without taking over Ctrl+C.
    signal.signal(signal.SIGINT, _handle_sigint)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="process at most N remaining files")
    ap.add_argument("--workers", type=int, default=1,
                    help="files processed concurrently, sharing --memory-gb")
    ap.add_argument("--memory-gb", type=float, default=4.0,
                    help="total DuckDB memory budget (default 4; about 1.5 GB of "
                         "headroom per worker beyond this is needed for Python "
                         "and the OS)")
    args = ap.parse_args()
    global _workers, _memory_gb
    _workers, _memory_gb = args.workers, args.memory_gb

    os.makedirs(STAGING_DIR, exist_ok=True)
    for f in os.listdir(STAGING_DIR):
        if f.endswith(".tmp"):
            os.remove(os.path.join(STAGING_DIR, f))
    fetch_institution_types()

    files = list_files()
    con = duckdb.connect()
    remaining = []
    for k, s in files:
        path = staging_path(k)
        if staging_ok(path, con):
            continue
        if os.path.exists(path):
            os.remove(path)   # outdated schema or unreadable
        remaining.append((k, s))
    con.close()
    n_done = len(files) - len(remaining)
    if args.limit:
        remaining = remaining[:args.limit]
    total_bytes = sum(s for _, s in remaining)
    print(f"{n_done}/{len(files)} files already done; processing {len(remaining)} "
          f"({total_bytes / 1e9:.1f} GB) with {_workers} worker(s), "
          f"{_memory_gb:g} GB DuckDB memory.")

    t0 = time.time()
    failed = []
    with ThreadPoolExecutor(max_workers=_workers) as ex, \
            tqdm(total=total_bytes, unit="B", unit_scale=True, desc="works") as bar:
        futures = {ex.submit(process_file, k): (k, s) for k, s in remaining}
        for fut in as_completed(futures):
            k, s = futures[fut]
            try:
                fut.result()
            except Exception as e:
                if not _stop.is_set():
                    failed.append(k)
                    tqdm.write(f"  ERROR on {k}: {e}")
            bar.update(s)
            if _stop.is_set():
                for f in futures:
                    f.cancel()

    print(f"Elapsed {fmt_duration(time.time() - t0)}.")
    if _stop.is_set():
        print("Stopped early. Run again to resume.")
        sys.exit(0)
    if failed:
        print(f"{len(failed)} file(s) failed; rerun to retry:")
        for k in failed:
            print(f"  {k}")
        sys.exit(1)
    print("All requested files done.")


if __name__ == "__main__":
    main()
