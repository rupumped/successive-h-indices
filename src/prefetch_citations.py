#!/usr/bin/env python3
"""
Sample cited_by_count from a spread of the OpenAlex works snapshot on S3, to
directly fit alpha_0 (Egghe 2008's article-citation Lotka exponent, his eq. 3).

Unlike prefetch.py (which needs the *entire* authors snapshot, since dropping
any of it would leave holes in every institution/country aggregate),
estimating a single power-law tail exponent is data-efficient: one ~360K-row
works file already yields ~90K nonzero-citation points, an order of magnitude
more than an MLE fit needs (SE(alpha) ~ (alpha-1)/sqrt(n_tail)). So this
samples one file each from a spread of partitions across the full 2016-2026
date range, rather than scanning all 482 partitions / ~725 GB of the full
works snapshot.

Partitions are spread across the full date range rather than clustered (e.g.
all-recent) because `updated_date` correlates with how recently a work's
metadata was touched, which correlates with how recently it was published,
which correlates with how little time it has had to accumulate citations --
an all-recent sample would bias cited_by_count downward.

Only id and cited_by_count are selected (both top-level scalar columns), so
DuckDB's columnar parquet reader never touches the large nested columns
(authorships, locations, topics, abstract_inverted_index, ...) that make up
most of each file's size -- this is why 25 files is enough bandwidth-wise,
not just statistically.

This samples the aggregate article-citation distribution (Egghe's Lemma
III.1 / eq. 20: same alpha_0 as the individual-author case, by his own
homogeneity assumption), not citations restricted to articles by the
17.1M-author population in authors.csv -- that would require pulling
authorships (a large nested column) back into the scan, defeating most of
the size savings, for a level of precision alpha_0 doesn't need here since
it's only used as a consistency check against beta_1/alpha_1 and
beta_2/(alpha_1*alpha_2).

Output: data/interim/citation_sample.csv (id, cited_by_count), cited_by_count > 0 only.

Usage:
  python3 prefetch_citations.py
  python3 estimate_alphas.py   # picks this up automatically if present
"""

import os
import re
import subprocess
import sys

import duckdb

S3_BASE = "s3://openalex/data/parquet/works"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_CSV = os.path.join(ROOT_DIR, "data", "interim", "citation_sample.csv")

N_PARTITIONS = 25  # spread across the full date range; see module docstring


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


def spread(items, n):
    """n items evenly spread across items (by index), including both ends."""
    if n >= len(items):
        return items
    step = (len(items) - 1) / (n - 1)
    idxs = sorted({round(i * step) for i in range(n)})
    return [items[i] for i in idxs]


def first_file(con, partition):
    row = con.execute(f"""
        SELECT file FROM glob('{S3_BASE}/{partition}/*.parquet') AS t(file)
        ORDER BY file LIMIT 1
    """).fetchone()
    return row[0] if row else None


def main():
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    con = make_con()

    partitions = list_partitions()
    chosen = spread(partitions, N_PARTITIONS)
    print(f"{len(partitions)} partitions available; sampling {len(chosen)} spread across the full date range.\n")

    files = []
    for p in chosen:
        f = first_file(con, p)
        if f is None:
            print(f"  {p}: no files found, skipping")
            continue
        print(f"  {p}: {f.rsplit('/', 1)[-1]}")
        files.append(f)

    if not files:
        sys.exit("ERROR: No files found in any sampled partition.")

    union_sql = "\n        UNION ALL\n        ".join(
        f"SELECT id, cited_by_count FROM read_parquet('{f}') WHERE cited_by_count > 0"
        for f in files
    )

    print(f"\nPulling id + cited_by_count from {len(files)} files...")
    con.execute(f"COPY ({union_sql}) TO '{OUT_CSV}' (HEADER, DELIMITER ',')")

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    size_mb = os.path.getsize(OUT_CSV) / 1e6
    print(f"\n{n:,} works with cited_by_count > 0 ({size_mb:.0f} MB) → {OUT_CSV}")
    print("Run estimate_alphas.py next to fold this into the alpha_0 fit and consistency check.")


if __name__ == "__main__":
    main()
