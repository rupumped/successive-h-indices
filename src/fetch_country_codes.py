#!/usr/bin/env python3
"""
Download the institution id -> country_code lookup from the OpenAlex S3
snapshot once, so build_country_h3.py and build_country_h3_by_field.py can
read it locally instead of re-scanning s3://openalex/.../institutions on
every run.

Output: data/interim/institution_country_map.csv (id, country_code)

Usage:
  python3 fetch_country_codes.py
"""

import os

import duckdb

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_CSV = os.path.join(ROOT_DIR, "data", "interim", "institution_country_map.csv")

S3_INSTITUTIONS = "s3://openalex/data/parquet/institutions/*/*.parquet"


def main():
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-east-1'; SET s3_access_key_id=''; SET s3_secret_access_key='';")
    con.execute("SET threads=4; SET enable_progress_bar=true;")

    print("Fetching country codes from S3...")
    con.execute(f"""
        COPY (
            SELECT id, country_code
            FROM read_parquet('{S3_INSTITUTIONS}')
            WHERE country_code IS NOT NULL
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"  {n:,} institutions with country codes → {OUT_CSV}")


if __name__ == "__main__":
    main()
