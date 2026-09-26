#!/usr/bin/env python3
"""
Multi-institution robustness check for currently tied affiliations
(reviewer round 2, issue 1: "fractional treatment of multiple current
affiliations").

The paper assigns each author to a single "most recent educational
affiliation," picked by the institution whose recorded affiliation-years
reach latest, with ties broken arbitrarily by smallest institution id
(see build.py). For authors whose OpenAlex record shows two or more
educational institutions tied for the same most-recent year (a genuine
current dual/multi-affiliation, not a data artifact of missing years),
that tiebreak silently drops all but one institution.

This script re-assigns each such author to *every* institution tied for
their most-recent year (inclusive multi-membership, the same pattern the
paper already uses for its multi-field robustness check), recomputes
institution h2 and country h3, and compares to the paper's baseline
single-pick assignment. This is not a literal fractional (1/n-weighted)
h-index -- it is a sensitivity bound on how much the single-institution
tiebreak rule, rather than genuine multi-affiliation, is driving results.

Outputs
-------
results/multi_institution_check.csv          — per-institution comparison
results/multi_institution_check_country.csv  — per-country comparison
results/multi_institution_check.log          — verbose run log

Usage
-----
  python3 src/multi_institution_check.py
"""

import glob
import json
import os
import sys
import time

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import _source_files, _make_batches, _batch_sql  # noqa: E402 (reuse memory-safe batching)

ROOT_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH         = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
STAGING         = os.path.join(ROOT_DIR, "data", "authors_staging", "*.parquet")
COUNTRY_MAP     = os.path.join(ROOT_DIR, "data", "interim", "institution_country_map.csv")
LOTKA_JSON      = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_CSV         = os.path.join(ROOT_DIR, "results", "multi_institution_check.csv")
OUT_COUNTRY_CSV = os.path.join(ROOT_DIR, "results", "multi_institution_check_country.csv")
LOG_PATH        = os.path.join(ROOT_DIR, "results", "multi_institution_check.log")

TOP_N = 20
FLAG_COUNTRIES = ["SA", "IT", "JP", "AU", "ES", "DE", "GB", "FR", "US", "CN"]

_log_file = None


def log(msg):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def h2_table_sql(con, out_tname, roster_expr):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out_tname} AS
        WITH roster AS ({roster_expr}),
        ranked AS (
            SELECT institution_id, institution_name, h_index,
                   ROW_NUMBER() OVER (
                       PARTITION BY institution_id ORDER BY h_index DESC
                   ) AS rank_desc
            FROM roster
        ),
        h2_candidates AS (
            SELECT institution_id,
                   arg_max(institution_name, rank_desc) AS institution_name,
                   MAX(rank_desc) AS h2
            FROM ranked
            WHERE h_index >= rank_desc
            GROUP BY institution_id
        ),
        author_counts AS (
            SELECT institution_id, COUNT(*) AS author_count
            FROM roster GROUP BY institution_id
        )
        SELECT h.institution_id, h.institution_name, h.h2, a.author_count
        FROM h2_candidates h JOIN author_counts a USING (institution_id)
    """)


def h3_table_sql(con, out_tname, h2_tname):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out_tname} AS
        WITH joined AS (
            SELECT c.country_code, h.h2
            FROM {h2_tname} h
            JOIN _country_map c ON h.institution_id = c.id
        ),
        ranked AS (
            SELECT country_code, h2,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_code ORDER BY h2 DESC
                   ) AS rank_desc
            FROM joined
        ),
        h3_candidates AS (
            SELECT country_code, MAX(rank_desc) AS h3
            FROM ranked WHERE h2 >= rank_desc
            GROUP BY country_code
        ),
        counts AS (
            SELECT country_code, COUNT(*) AS institution_count
            FROM joined GROUP BY country_code
        )
        SELECT h.country_code, h.h3, c.institution_count
        FROM h3_candidates h JOIN counts c USING (country_code)
    """)


def spearman(con, t1, t2, key_cols, val_col="h2"):
    key = ", ".join(key_cols)
    return con.execute(f"""
        WITH a AS (SELECT {key}, RANK() OVER (ORDER BY {val_col} DESC) r FROM {t1}),
             b AS (SELECT {key}, RANK() OVER (ORDER BY {val_col} DESC) r FROM {t2})
        SELECT corr(a.r, b.r), COUNT(*) FROM a JOIN b USING ({key})
    """).fetchone()


def topn_overlap(con, t1, t2, key_cols, val_col, n):
    key = ", ".join(key_cols)
    a = con.execute(f"SELECT {key} FROM {t1} ORDER BY {val_col} DESC LIMIT {n}").fetchall()
    b = con.execute(f"SELECT {key} FROM {t2} ORDER BY {val_col} DESC LIMIT {n}").fetchall()
    return len(set(a) & set(b)) / n


def main():
    global _log_file
    with open(LOG_PATH, "w") as _log_file:
        t_start = time.time()
        con = duckdb.connect(DB_PATH)
        con.execute("SET enable_progress_bar=false; SET threads=4; SET memory_limit='4GB';")
        con.execute(f"SET temp_directory='{os.path.join(ROOT_DIR, 'data')}';")
        con.execute("SET preserve_insertion_order=false;")

        with open(LOTKA_JSON) as f:
            lotka = json.load(f)
        beta_2 = lotka["beta_2"]

        log("Loading institution -> country map...")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _country_map AS
            SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP}')
        """)

        log("Finding every educational institution tied for each author's most-recent affiliation "
            "year (batched scan, mirrors build.py's memory-safe batching)...")
        t0 = time.time()
        files = _source_files()
        batches = _make_batches(files)
        con.execute("DROP TABLE IF EXISTS _tied")
        tied_created = False
        for b, batch in enumerate(batches):
            batch_sql = _batch_sql(batch)
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE _tied_batch AS
                WITH _raw AS ({batch_sql}),
                edu AS (
                    SELECT id AS author_id,
                           aff.institution.id           AS institution_id,
                           aff.institution.display_name AS institution_name,
                           list_max(aff.years)          AS latest_year
                    FROM _raw
                    CROSS JOIN LATERAL UNNEST(affiliations) AS t(aff)
                    WHERE aff.institution.type = 'education'
                ),
                maxyear AS (
                    SELECT author_id, MAX(latest_year) AS m FROM edu GROUP BY author_id
                )
                SELECT e.author_id, e.institution_id, e.institution_name
                FROM edu e JOIN maxyear m USING (author_id)
                WHERE e.latest_year = m.m OR (e.latest_year IS NULL AND m.m IS NULL)
            """)
            if not tied_created:
                con.execute("CREATE TEMP TABLE _tied AS SELECT * FROM _tied_batch")
                tied_created = True
            else:
                con.execute("INSERT INTO _tied SELECT * FROM _tied_batch")
            con.execute("DROP TABLE _tied_batch")
            log(f"  batch {b+1}/{len(batches)} done")
        n_tied_rows, n_tied_authors = con.execute("""
            SELECT COUNT(*), COUNT(DISTINCT author_id) FROM _tied
        """).fetchone()
        n_multi_authors = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT author_id FROM _tied GROUP BY author_id HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        log(f"  {n_tied_authors:,} authors have >=1 institution at their most-recent year; "
            f"{n_multi_authors:,} of them ({n_multi_authors/n_tied_authors:.1%}) have a genuine tie "
            f"(2+ institutions)  ({time.time()-t0:.0f}s)\n")

        log("Building inclusive multi-institution roster (join h_index onto every tied institution)...")
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _roster_multi AS
            SELECT t.institution_id, t.institution_name, a.h_index
            FROM _tied t
            JOIN authors a USING (author_id)
        """)
        n_pairs_multi = con.execute("SELECT COUNT(*) FROM _roster_multi").fetchone()[0]
        n_pairs_baseline = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
        log(f"  baseline (author, institution) pairs: {n_pairs_baseline:,}")
        log(f"  inclusive multi-institution pairs:     {n_pairs_multi:,} "
            f"({(n_pairs_multi/n_pairs_baseline - 1):+.1%})\n")

        log("Computing institution h2: baseline vs inclusive multi-institution roster...")
        h2_table_sql(con, "h2_baseline",
                     "SELECT institution_id, institution_name, h_index FROM authors")
        h2_table_sql(con, "h2_multi",
                     "SELECT institution_id, institution_name, h_index FROM _roster_multi")

        n_inst_baseline = con.execute("SELECT COUNT(*) FROM h2_baseline").fetchone()[0]
        n_inst_multi = con.execute("SELECT COUNT(*) FROM h2_multi").fetchone()[0]
        log(f"  baseline: {n_inst_baseline:,} institutions | multi-institution: {n_inst_multi:,} institutions\n")

        rho_inst, n_shared_inst = spearman(con, "h2_baseline", "h2_multi", ["institution_id"])
        overlap10 = topn_overlap(con, "h2_baseline", "h2_multi", ["institution_id"], "h2", 10)
        overlap20 = topn_overlap(con, "h2_baseline", "h2_multi", ["institution_id"], "h2", 20)
        log(f"Institution h2 rank correlation (baseline vs multi-institution, {n_shared_inst:,} shared): "
            f"rho = {rho_inst:.4f}")
        log(f"  Top-10 overlap: {overlap10:.0%} | Top-20 overlap: {overlap20:.0%}\n")

        log("Computing country h3: baseline vs multi-institution...")
        h3_table_sql(con, "h3_baseline", "h2_baseline")
        h3_table_sql(con, "h3_multi", "h2_multi")

        rho_country, n_shared_country = spearman(con, "h3_baseline", "h3_multi",
                                                   ["country_code"], val_col="h3")
        overlap10_c = topn_overlap(con, "h3_baseline", "h3_multi", ["country_code"], "h3", 10)
        overlap20_c = topn_overlap(con, "h3_baseline", "h3_multi", ["country_code"], "h3", 20)
        log(f"Country h3 rank correlation (baseline vs multi-institution, {n_shared_country:,} shared): "
            f"rho = {rho_country:.4f}")
        log(f"  Top-10 overlap: {overlap10_c:.0%} | Top-20 overlap: {overlap20_c:.0%}\n")

        log("Efficiency comparison (epsilon_3 = h3 / institution_count^(1/beta_2)) for flagged countries:")
        for tname in ["h3_baseline", "h3_multi"]:
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE {tname}_ranked AS
                SELECT *, h3 / POW(institution_count, 1.0/{beta_2}) AS eps3
                FROM {tname}
            """)
        rows = con.execute(f"""
            SELECT b.country_code, b.h3, RANK() OVER (ORDER BY b.h3 DESC), b.eps3,
                   m.h3, RANK() OVER (ORDER BY m.h3 DESC), m.eps3
            FROM h3_baseline_ranked b
            LEFT JOIN h3_multi_ranked m USING (country_code)
            WHERE b.country_code IN ({",".join(f"'{c}'" for c in FLAG_COUNTRIES)})
            ORDER BY b.h3 DESC
        """).fetchall()
        log(f"  {'cc':<4}{'h3_base':>9}{'rank_base':>11}{'eps3_base':>11}"
            f"{'h3_multi':>10}{'rank_multi':>12}{'eps3_multi':>12}")
        for cc, h3b, rb, eb, h3m, rm, em in rows:
            log(f"  {cc:<4}{h3b:>9}{rb:>11}{eb:>11.3f}{h3m:>10}{rm:>12}{em:>12.3f}")
        log("")

        log(f"Top {TOP_N} institutions by |rank shift|, restricted to institutions gaining "
            f">=20 authors under the multi-institution roster:")
        movers = con.execute(f"""
            WITH b AS (SELECT institution_id, institution_name, h2 AS h2_base, author_count AS n_base,
                              RANK() OVER (ORDER BY h2 DESC) AS rank_base FROM h2_baseline),
                 m AS (SELECT institution_id, h2 AS h2_multi, author_count AS n_multi,
                              RANK() OVER (ORDER BY h2 DESC) AS rank_multi FROM h2_multi)
            SELECT b.institution_name, b.h2_base, b.rank_base, m.h2_multi, m.rank_multi,
                   b.n_base, m.n_multi, (b.rank_base - m.rank_multi) AS shift
            FROM b JOIN m USING (institution_id)
            WHERE (m.n_multi - b.n_base) >= 20
            ORDER BY ABS(shift) DESC
            LIMIT {TOP_N}
        """).fetchall()
        log(f"  {'institution':<40}{'h2_base':>8}{'rank_base':>10}{'h2_multi':>9}{'rank_multi':>11}{'n_base':>8}{'n_multi':>8}{'shift':>7}")
        for name, h2b, rb, h2m, rm, nb, nm, shift in movers:
            log(f"  {str(name)[:39]:<40}{h2b:>8}{rb:>10}{h2m:>9}{rm:>11}{nb:>8,}{nm:>8,}{shift:>7}")
        log("")

        con.execute(f"""
            COPY (
                SELECT b.institution_id, b.institution_name,
                       b.h2 AS h2_baseline, b.author_count AS authors_baseline,
                       m.h2 AS h2_multi, m.author_count AS authors_multi,
                       RANK() OVER (ORDER BY b.h2 DESC) AS rank_baseline,
                       RANK() OVER (ORDER BY m.h2 DESC) AS rank_multi
                FROM h2_baseline b LEFT JOIN h2_multi m USING (institution_id)
                ORDER BY b.h2 DESC
            ) TO '{OUT_CSV}' (FORMAT CSV, HEADER TRUE)
        """)
        con.execute(f"""
            COPY (
                SELECT b.country_code,
                       b.h3 AS h3_baseline, b.institution_count AS institutions_baseline,
                       m.h3 AS h3_multi, m.institution_count AS institutions_multi,
                       RANK() OVER (ORDER BY b.h3 DESC) AS rank_baseline,
                       RANK() OVER (ORDER BY m.h3 DESC) AS rank_multi
                FROM h3_baseline b LEFT JOIN h3_multi m USING (country_code)
                ORDER BY b.h3 DESC
            ) TO '{OUT_COUNTRY_CSV}' (FORMAT CSV, HEADER TRUE)
        """)
        log(f"Wrote {OUT_CSV}")
        log(f"Wrote {OUT_COUNTRY_CSV}")
        log(f"\nTotal runtime: {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
