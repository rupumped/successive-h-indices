#!/usr/bin/env python3
"""
Stable-affiliation robustness check for the institution/country attribution
problem (reviewer round 2, issue 1/6).

The paper assigns each author's entire-career h-index to their single most
recent educational affiliation. This conflates an author's current location
with the institution(s) where the underlying work was actually produced,
which is most distorting for internationally mobile or multiply-affiliated
researchers.

This script isolates the subset of authors OpenAlex records as having had
exactly one educational institution ever (no recorded mobility), recomputes
institution-level h2 and country-level h3 on that subset alone, and compares
the resulting rankings to the full-population baseline. Because a "stable"
author's one-and-only institution is unambiguously the institution where
their career happened, this subset is not subject to the attribution
problem, so large rank movements between baseline and stable-only rankings
indicate where the attribution rule is likely distorting results.

Outputs
-------
results/stable_affiliation_check.csv  — per-institution and per-country
                                         baseline vs. stable-only comparison
results/stable_affiliation_check.log  — verbose run log, including specific
                                         call-outs (Saudi Arabia, top movers)

Usage
-----
  python3 src/stable_affiliation_check.py
"""

import glob
import json
import os
import sys
import time

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import _source_files, _make_batches, _batch_sql  # noqa: E402 (reuse memory-safe batching)

ROOT_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH        = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
STAGING        = os.path.join(ROOT_DIR, "data", "authors_staging", "*.parquet")
COUNTRY_MAP    = os.path.join(ROOT_DIR, "data", "interim", "institution_country_map.csv")
LOTKA_JSON     = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_CSV        = os.path.join(ROOT_DIR, "results", "stable_affiliation_check.csv")
OUT_COUNTRY_CSV = os.path.join(ROOT_DIR, "results", "stable_affiliation_check_country.csv")
LOG_PATH       = os.path.join(ROOT_DIR, "results", "stable_affiliation_check.log")

TOP_N = 20
FLAG_COUNTRIES = ["SA", "IT", "JP", "AU", "ES", "DE", "GB", "FR", "US", "CN"]

_log_file = None


def log(msg):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def h2_table_sql(con, out_tname, roster_expr):
    """roster_expr must yield (institution_id, institution_name, h_index) rows."""
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
        beta_1, beta_2 = lotka["beta_1"], lotka["beta_2"]
        log(f"Reusing fitted exponents from full-population fit: beta_1={beta_1:.4f}, beta_2={beta_2:.4f}")
        log("(Note: these exponents are not refit on the stable-only subset; efficiency\n"
            " comparisons below should be read as approximate, not a full re-derivation.)\n")

        log("Loading institution -> country map...")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _country_map AS
            SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP}')
        """)

        log("Flagging authors by lifetime educational-institution mobility (batched scan, "
            "mirrors build.py's memory-safe batching)...")
        t0 = time.time()
        files = _source_files()
        batches = _make_batches(files)
        con.execute("DROP TABLE IF EXISTS _mobility")
        mobility_created = False
        for b, batch in enumerate(batches):
            batch_sql = _batch_sql(batch)
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE _mobility_batch AS
                WITH _raw AS ({batch_sql}),
                edu AS (
                    SELECT id AS author_id, aff.institution.id AS institution_id
                    FROM _raw
                    CROSS JOIN LATERAL UNNEST(affiliations) AS t(aff)
                    WHERE aff.institution.type = 'education'
                )
                SELECT author_id, COUNT(DISTINCT institution_id) AS n_lifetime_institutions,
                       (COUNT(DISTINCT institution_id) = 1) AS stable
                FROM edu
                GROUP BY author_id
            """)
            if not mobility_created:
                con.execute("CREATE TEMP TABLE _mobility AS SELECT * FROM _mobility_batch")
                mobility_created = True
            else:
                con.execute("INSERT INTO _mobility SELECT * FROM _mobility_batch")
            con.execute("DROP TABLE _mobility_batch")
            log(f"  batch {b+1}/{len(batches)} done")
        n_stable, n_total = con.execute("""
            SELECT SUM(CASE WHEN stable THEN 1 ELSE 0 END), COUNT(*) FROM _mobility
        """).fetchone()
        log(f"  {n_stable:,} / {n_total:,} authors ({n_stable/n_total:.1%}) have a single "
            f"lifetime educational institution recorded  ({time.time()-t0:.0f}s)\n")

        log("Joining mobility flag onto the paper's assigned authors table...")
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _authors_flagged AS
            SELECT a.author_id, a.institution_id, a.institution_name, a.h_index, m.stable
            FROM authors a JOIN _mobility m USING (author_id)
        """)
        n_baseline = con.execute("SELECT COUNT(*) FROM _authors_flagged").fetchone()[0]
        n_stable_in_pop = con.execute(
            "SELECT COUNT(*) FROM _authors_flagged WHERE stable"
        ).fetchone()[0]
        log(f"  {n_baseline:,} authors in the paper's qualifying population; "
            f"{n_stable_in_pop:,} ({n_stable_in_pop/n_baseline:.1%}) are stable\n")

        # --- Institution-level h2: baseline (all) vs stable-only ---
        log("Computing institution h2: baseline (all authors)...")
        h2_table_sql(con, "h2_baseline",
                     "SELECT institution_id, institution_name, h_index FROM _authors_flagged")
        log("Computing institution h2: stable-only subset...")
        h2_table_sql(con, "h2_stable",
                     "SELECT institution_id, institution_name, h_index FROM _authors_flagged WHERE stable")

        n_inst_baseline = con.execute("SELECT COUNT(*) FROM h2_baseline").fetchone()[0]
        n_inst_stable = con.execute("SELECT COUNT(*) FROM h2_stable").fetchone()[0]
        log(f"  baseline: {n_inst_baseline:,} institutions | stable-only: {n_inst_stable:,} institutions\n")

        rho_inst, n_shared_inst = spearman(con, "h2_baseline", "h2_stable", ["institution_id"])
        overlap10 = topn_overlap(con, "h2_baseline", "h2_stable", ["institution_id"], "h2", 10)
        overlap20 = topn_overlap(con, "h2_baseline", "h2_stable", ["institution_id"], "h2", 20)
        log(f"Institution h2 rank correlation (baseline vs stable-only, {n_shared_inst:,} shared institutions): "
            f"rho = {rho_inst:.4f}")
        log(f"  Top-10 overlap: {overlap10:.0%} | Top-20 overlap: {overlap20:.0%}\n")

        # --- Country-level h3: baseline vs stable-only ---
        log("Computing country h3: baseline vs stable-only...")
        h3_table_sql(con, "h3_baseline", "h2_baseline")
        h3_table_sql(con, "h3_stable", "h2_stable")

        rho_country, n_shared_country = spearman(con, "h3_baseline", "h3_stable",
                                                   ["country_code"], val_col="h3")
        overlap10_c = topn_overlap(con, "h3_baseline", "h3_stable", ["country_code"], "h3", 10)
        overlap20_c = topn_overlap(con, "h3_baseline", "h3_stable", ["country_code"], "h3", 20)
        log(f"Country h3 rank correlation (baseline vs stable-only, {n_shared_country:,} shared countries): "
            f"rho = {rho_country:.4f}")
        log(f"  Top-10 overlap: {overlap10_c:.0%} | Top-20 overlap: {overlap20_c:.0%}\n")

        # --- Efficiency (reusing full-population exponents) for flagged countries ---
        log("Efficiency comparison (epsilon_3 = h3 / institution_count^(1/beta_2)) for flagged countries:")
        log(f"  {'cc':<4}{'h3_base':>9}{'rank_base':>11}{'eps3_base':>11}"
            f"{'h3_stable':>11}{'rank_stable':>13}{'eps3_stable':>13}")
        for tname, label in [("h3_baseline", "base"), ("h3_stable", "stable")]:
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE {tname}_ranked AS
                SELECT *, h3 / POW(institution_count, 1.0/{beta_2}) AS eps3,
                       RANK() OVER (ORDER BY h3 / POW(institution_count, 1.0/{beta_2}) DESC) AS eff_rank
                FROM {tname}
            """)
        rows = con.execute(f"""
            SELECT b.country_code, b.h3, RANK() OVER (ORDER BY b.h3 DESC),
                   b.eps3, s.h3, RANK() OVER (ORDER BY s.h3 DESC), s.eps3
            FROM h3_baseline_ranked b
            LEFT JOIN h3_stable_ranked s USING (country_code)
            WHERE b.country_code IN ({",".join(f"'{c}'" for c in FLAG_COUNTRIES)})
            ORDER BY b.h3 DESC
        """).fetchall()
        for cc, h3b, rb, eb, h3s, rs, es in rows:
            h3s_str = f"{h3s:>11}" if h3s is not None else f"{'n/a':>11}"
            rs_str = f"{rs:>13}" if rs is not None else f"{'n/a':>13}"
            es_str = f"{es:>13.3f}" if es is not None else f"{'n/a':>13}"
            log(f"  {cc:<4}{h3b:>9}{rb:>11}{eb:>11.3f}{h3s_str}{rs_str}{es_str}")
        log("")

        # --- Top movers: institutions whose stable-only rank differs most from baseline ---
        log(f"Top {TOP_N} institutions by |rank shift| (baseline rank vs stable-only rank), "
            f"restricted to institutions with >=20 stable authors:")
        movers = con.execute(f"""
            WITH b AS (SELECT institution_id, institution_name, h2 AS h2_base,
                              RANK() OVER (ORDER BY h2 DESC) AS rank_base FROM h2_baseline),
                 s AS (SELECT institution_id, h2 AS h2_stable, author_count AS stable_authors,
                              RANK() OVER (ORDER BY h2 DESC) AS rank_stable FROM h2_stable)
            SELECT b.institution_name, b.h2_base, b.rank_base, s.h2_stable, s.rank_stable,
                   s.stable_authors, (b.rank_base - s.rank_stable) AS shift
            FROM b JOIN s USING (institution_id)
            WHERE s.stable_authors >= 20
            ORDER BY ABS(shift) DESC
            LIMIT {TOP_N}
        """).fetchall()
        log(f"  {'institution':<45}{'h2_base':>8}{'rank_base':>10}{'h2_stable':>10}{'rank_stable':>12}{'stable_n':>9}{'shift':>7}")
        for name, h2b, rb, h2s, rs, sn, shift in movers:
            log(f"  {str(name)[:44]:<45}{h2b:>8}{rb:>10}{h2s:>10}{rs:>12}{sn:>9,}{shift:>7}")
        log("")

        # --- Write CSVs ---
        con.execute(f"""
            COPY (
                SELECT b.institution_id, b.institution_name,
                       b.h2 AS h2_baseline, b.author_count AS authors_baseline,
                       s.h2 AS h2_stable, s.author_count AS authors_stable,
                       RANK() OVER (ORDER BY b.h2 DESC) AS rank_baseline,
                       RANK() OVER (ORDER BY s.h2 DESC) AS rank_stable
                FROM h2_baseline b LEFT JOIN h2_stable s USING (institution_id)
                ORDER BY b.h2 DESC
            ) TO '{OUT_CSV}' (FORMAT CSV, HEADER TRUE)
        """)
        con.execute(f"""
            COPY (
                SELECT b.country_code,
                       b.h3 AS h3_baseline, b.institution_count AS institutions_baseline,
                       s.h3 AS h3_stable, s.institution_count AS institutions_stable,
                       RANK() OVER (ORDER BY b.h3 DESC) AS rank_baseline,
                       RANK() OVER (ORDER BY s.h3 DESC) AS rank_stable
                FROM h3_baseline b LEFT JOIN h3_stable s USING (country_code)
                ORDER BY b.h3 DESC
            ) TO '{OUT_COUNTRY_CSV}' (FORMAT CSV, HEADER TRUE)
        """)
        log(f"Wrote {OUT_CSV}")
        log(f"Wrote {OUT_COUNTRY_CSV}")
        log(f"\nTotal runtime: {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main()
