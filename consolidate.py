#!/usr/bin/env python3
"""
Merge the per-partition staging files produced by prefetch.py into a single
data/authors_filtered.parquet for use by build.py.

Usage:
  python3 consolidate.py
"""

import duckdb
import glob
import os
import re
import sys
import time

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR = os.path.join(OUT_DIR, "data", "authors_staging")
FILTERED_PARQUET = os.path.join(OUT_DIR, "data", "authors_filtered.parquet")


def main():
    staging_files = sorted(glob.glob(os.path.join(STAGING_DIR, "*.parquet")))
    if not staging_files:
        sys.exit(f"ERROR: No staging files found in {STAGING_DIR}.\nRun prefetch.py first.")

    print(f"Staging files : {len(staging_files)}")
    print(f"Output        : {FILTERED_PARQUET}")

    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='16GB';")
    con.execute("SET enable_progress_bar=true;")

    staging_glob = os.path.join(STAGING_DIR, "*.parquet")
    t0 = time.time()
    try:
        con.execute(f"""
            COPY (SELECT * FROM read_parquet('{staging_glob}'))
            TO '{FILTERED_PARQUET}'
            (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
        """)
    except Exception as e:
        m = re.search(r"'(/[^']+\.parquet)'", str(e))
        if m:
            bad = m.group(1)
            print(f"\nCorrupt staging file detected: {bad}")
            answer = input("Remove it and consolidate without it? [y/N] ").strip().lower()
            if answer != "y":
                sys.exit(1)
            os.remove(bad)
            print("Removed. Re-run consolidate.py to try again.")
            sys.exit(1)
        raise

    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{FILTERED_PARQUET}')").fetchone()[0]
    size_mb = os.path.getsize(FILTERED_PARQUET) / 1e6
    print(f"Done: {n:,} authors, {size_mb:.0f} MB  ({time.time()-t0:.0f}s)")
    print("Run 'python3 build.py' to compute H2.")


if __name__ == "__main__":
    main()
