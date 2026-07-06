#!/usr/bin/env python3
"""
Stream the OpenAlex authors snapshot from S3, one partition at a time.

Each updated_date= partition is filtered and written to data/authors_staging/.
Corrupt or partially-written files are detected at startup and re-downloaded.
If interrupted, already-written partitions are skipped on the next run.

Filters applied per partition:
  - summary_stats.h_index > 0
  - affiliations contains at least one entry with institution.type = 'education'
  - topics contains at least one entry with a non-null field.id

Column pruning: only id, h_index, affiliations, and topics are fetched from
each remote file. affiliations (not last_known_institutions) is pulled
because it carries a years[] array per institution, which build.py uses to
pick each author's most recent education affiliation; last_known_institutions
has no per-entry recency information — its entries are just the affiliations
listed on an author's single most recent work, in no meaningful order.

Usage:
  python3 prefetch.py
  python3 consolidate.py   # once prefetch completes
  python3 build.py         # once consolidate completes
"""

import duckdb
import os
import re
import signal
import subprocess
import sys
import time

_stop_requested = False
_active_con = None  # connection currently running a query, for interrupt()

def _handle_sigint(*_):
    global _stop_requested
    if _stop_requested:
        print("\nForced exit.")
        sys.exit(1)
    _stop_requested = True
    print("\nInterrupt received — finishing current partition then stopping.")
    print("Press Ctrl+C again to force quit.")
    if _active_con is not None:
        _active_con.interrupt()

signal.signal(signal.SIGINT, _handle_sigint)

S3_BASE = "s3://openalex/data/parquet/authors"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGING_DIR = os.path.join(ROOT_DIR, "data", "authors_staging")

FILTER_SQL = """
    summary_stats.h_index IS NOT NULL
    AND summary_stats.h_index > 0
    AND list_count(list_filter(affiliations, x -> x.institution.type = 'education')) > 0
    AND list_count(list_filter(topics, x -> x.field.id IS NOT NULL)) > 0
"""


def make_con():
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='4GB';")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-east-1';")
    con.execute("SET s3_access_key_id=''; SET s3_secret_access_key='';")
    return con


def list_partitions():
    result = subprocess.run(
        ["aws", "s3", "ls", f"{S3_BASE}/", "--no-sign-request", "--region", "us-east-1"],
        capture_output=True, text=True, check=True,
    )
    partitions = sorted(
        m.group(1)
        for line in result.stdout.splitlines()
        if (m := re.search(r"(updated_date=[\d-]+)/", line))
    )
    if not partitions:
        sys.exit("ERROR: No partitions found. Check AWS CLI and network access.")
    return partitions


def staging_path(partition):
    return os.path.join(STAGING_DIR, f"{partition}.parquet")


def parquet_ok(path):
    """True if the file has valid parquet magic bytes and a plausible footer length.

    Parquet layout: [PAR1][...data...][footer bytes][footer_len: int32][PAR1]
    A truncated write typically leaves PAR1 at the end but a footer_length that
    points past the start of the file, which DuckDB rejects as corrupt.
    """
    try:
        size = os.path.getsize(path)
        if size < 12:   # minimum: 4 magic + 4 footer + 4 magic
            return False
        with open(path, "rb") as f:
            if f.read(4) != b"PAR1":
                return False
            f.seek(-8, 2)
            footer_len = int.from_bytes(f.read(4), "little")
            magic = f.read(4)
        if magic != b"PAR1":
            return False
        return 0 < footer_len < size - 8
    except OSError:
        return False


def process_partition(con, partition):
    global _active_con
    s3_glob = f"{S3_BASE}/{partition}/*.parquet"
    out = staging_path(partition)
    _active_con = con
    try:
        con.execute(f"""
            COPY (
                SELECT
                    id,
                    summary_stats.h_index           AS h_index,
                    affiliations,
                    topics
                FROM read_parquet('{s3_glob}')
                WHERE {FILTER_SQL}
            ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
        """)
    finally:
        _active_con = None
    return con.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0]


def fmt_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def main():
    os.makedirs(STAGING_DIR, exist_ok=True)

    con = make_con()
    partitions = list_partitions()
    total = len(partitions)

    done = set()
    for p in partitions:
        path = staging_path(p)
        if not os.path.exists(path):
            continue
        if parquet_ok(path):
            done.add(p)
        else:
            print(f"  Removing corrupt staging file: {path}")
            os.remove(path)

    remaining = [p for p in partitions if p not in done]

    if done:
        print(f"Resuming: {len(done)}/{total} partitions already done, {len(remaining)} remaining.")
    else:
        print(f"Found {total} partitions to process.")
    print()

    cumulative_authors = 0
    partition_times = []
    wall_start = time.time()

    for i, partition in enumerate(remaining, start=1):
        if _stop_requested:
            completed = len(done) + i - 1
            print(f"Stopped after {completed}/{total} partitions. Run again to resume.")
            sys.exit(0)

        idx = len(done) + i
        t0 = time.time()

        try:
            n = process_partition(con, partition)
        except Exception as e:
            path = staging_path(partition)
            if os.path.exists(path):
                os.remove(path)
            print(f"\n  ERROR on {partition}: {e}")
            print("  Skipping — rerun to retry.")
            continue

        elapsed = time.time() - t0
        partition_times.append(elapsed)
        cumulative_authors += n

        avg = sum(partition_times) / len(partition_times)
        eta = fmt_duration(avg * (len(remaining) - i))
        wall_elapsed = fmt_duration(time.time() - wall_start)

        print(
            f"[{idx:>4}/{total}]  {partition}  "
            f"{n:>7,} authors  {elapsed:>5.1f}s  "
            f"| total {cumulative_authors:>10,}  elapsed {wall_elapsed}  ETA {eta}"
        )

    missing = [p for p in partitions if not os.path.exists(staging_path(p))]
    if missing:
        print(f"\n{len(missing)} partition(s) could not be downloaded:")
        for p in missing:
            print(f"  {p}")
        print("Rerun to retry, or run consolidate.py to proceed without them.")
        sys.exit(1)

    print("\nAll partitions downloaded. Run 'python3 consolidate.py'.")


if __name__ == "__main__":
    main()
