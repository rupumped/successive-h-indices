#!/usr/bin/env python3
"""
Multi-institution robustness check (works-based, 5-year window).

For each qualifying author, finds every institution meeting both primary-attribution
thresholds (>=2 papers AND >=10% of education-crediting works) in the author's
5-year window — not just the one with the most works. Assigns the author's full
h₁ to each such institution, recomputes institution h₂ and country h₃, and
compares to the default single-institution rankings.

Addresses the reviewer's request for "fractional treatment of multiple current
affiliations." Since h-indices are integer by definition, multi-institution
assignment (each author counted fully at every qualifying institution) is the
closest tractable analog to fractional credit.

Outputs
-------
results/multi_institution_check.csv         — per-institution comparison
results/multi_institution_check_country.csv — per-country comparison
results/multi_institution_check.log         — verbose run log

Usage
-----
  conda run -n base python3 src/multi_institution_check.py
"""

import json
import os
import time

import duckdb
import tqdm

ROOT_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH         = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
WORKS_BUCKET_DIR = os.path.join(ROOT_DIR, "data", "works_buckets")
COUNTRY_MAP     = os.path.join(ROOT_DIR, "data", "interim", "institution_country_map.csv")
H2_CSV          = os.path.join(ROOT_DIR, "data", "interim", "h2_by_institution.csv")
LOTKA_JSON      = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_CSV         = os.path.join(ROOT_DIR, "results", "multi_institution_check.csv")
OUT_COUNTRY_CSV = os.path.join(ROOT_DIR, "results", "multi_institution_check_country.csv")
LOG_PATH        = os.path.join(ROOT_DIR, "results", "multi_institution_check.log")

N_BUCKETS        = 64
PRIMARY_WINDOW   = 5
PRIMARY_MIN_PAPERS = 2
PRIMARY_MIN_SHARE  = 0.10
MAX_YEAR         = 2026
TOP_N            = 20
FLAG_COUNTRIES   = ["SA", "IT", "JP", "AU", "ES", "DE", "GB", "FR", "US", "CN"]

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

        log(f"Primary-institution thresholds: min_papers={PRIMARY_MIN_PAPERS}, "
            f"min_share={PRIMARY_MIN_SHARE:.0%}, window={PRIMARY_WINDOW} years")
        log("Multi-institution variant: keep ALL institutions meeting both thresholds "
            "(not just the one with most works).\n")

        log("Loading institution -> country map...")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _country_map AS
            SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP}')
        """)

        log("Loading institution name lookup (from h2_by_institution.csv)...")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _inst_names AS
            SELECT institution_id, institution_name
            FROM read_csv_auto('{H2_CSV}')
        """)

        # primary_institution is in openalex.duckdb (from build.py step 2).
        # It has: author_id, last_year, n_all, n_denom, institution_id,
        #         n_inst, latest_year, n_career, passes
        n_qualifying = con.execute(
            "SELECT COUNT(*) FROM primary_institution WHERE passes"
        ).fetchone()[0]
        log(f"Qualifying authors (passes=true in primary_institution): {n_qualifying:,}\n")

        # Build multi-institution roster: for each qualifying author, find every
        # institution meeting both thresholds in their 5-year window.
        log("Building multi-institution roster (scanning works_buckets by bucket)...")
        t0 = time.time()
        con.execute("DROP TABLE IF EXISTS _multi_pairs")
        pairs_created = False

        for b in tqdm.tqdm(range(N_BUCKETS), desc="  Scanning buckets", unit="bucket"):
            bucket_dir = os.path.join(WORKS_BUCKET_DIR, f"bucket={b}")
            if not os.path.isdir(bucket_dir):
                continue
            bucket_glob = os.path.join(bucket_dir, "*.parquet")
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE _bucket_pairs AS
                WITH raw AS (
                    SELECT author_id, year, institution_id, n_rollup
                    FROM read_parquet('{bucket_glob}')
                    WHERE year <= {MAX_YEAR}
                ),
                last_year AS (
                    SELECT author_id, MAX(year) AS last_year
                    FROM raw WHERE institution_id IS NULL GROUP BY author_id
                ),
                win_inst AS (
                    SELECT r.author_id, r.institution_id,
                           SUM(r.n_rollup) AS n_inst_window
                    FROM raw r JOIN last_year l USING (author_id)
                    WHERE r.year > l.last_year - {PRIMARY_WINDOW}
                    AND r.institution_id IS NOT NULL
                    GROUP BY r.author_id, r.institution_id
                )
                SELECT w.author_id, w.institution_id, w.n_inst_window
                FROM win_inst w
                JOIN primary_institution p ON p.author_id = w.author_id AND p.passes
                WHERE w.n_inst_window >= {PRIMARY_MIN_PAPERS}
                AND w.n_inst_window >= {PRIMARY_MIN_SHARE} * p.n_denom
            """)
            if not pairs_created:
                con.execute("CREATE TEMP TABLE _multi_pairs AS SELECT * FROM _bucket_pairs")
                pairs_created = True
            else:
                con.execute("INSERT INTO _multi_pairs SELECT * FROM _bucket_pairs")
            con.execute("DROP TABLE _bucket_pairs")

        n_pairs = con.execute("SELECT COUNT(*) FROM _multi_pairs").fetchone()[0]
        n_authors_multi = con.execute(
            "SELECT COUNT(DISTINCT author_id) FROM _multi_pairs"
        ).fetchone()[0]
        n_baseline = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
        log(f"  {n_pairs:,} (author, institution) pairs in multi-institution roster "
            f"({n_pairs/n_baseline - 1:+.1%} vs baseline {n_baseline:,})  "
            f"({time.time()-t0:.0f}s)")

        n_multi_only = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT author_id FROM _multi_pairs GROUP BY author_id HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        log(f"  {n_multi_only:,} authors ({n_multi_only/n_authors_multi:.1%}) qualify at "
            f">=2 institutions\n")

        # Build the expanded roster: (institution_id, institution_name, h_index)
        # Institution name: from authors table (primary assignment) where available,
        # otherwise from h2_by_institution lookup.
        log("Joining h_index and institution names onto multi-institution pairs...")
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _roster_multi AS
            SELECT mp.institution_id,
                   COALESCE(n.institution_name, '[unknown]') AS institution_name,
                   a.h_index
            FROM _multi_pairs mp
            JOIN authors a ON a.author_id = mp.author_id
            LEFT JOIN _inst_names n ON n.institution_id = mp.institution_id
        """)
        n_roster = con.execute("SELECT COUNT(*) FROM _roster_multi").fetchone()[0]
        log(f"  {n_roster:,} rows in expanded roster\n")

        # Compute h₂: baseline (single institution per author) vs multi-institution
        log("Computing institution h2: baseline...")
        h2_table_sql(con, "h2_baseline",
                     "SELECT institution_id, institution_name, h_index FROM authors")
        log("Computing institution h2: multi-institution...")
        h2_table_sql(con, "h2_multi",
                     "SELECT institution_id, institution_name, h_index FROM _roster_multi")

        n_inst_baseline = con.execute("SELECT COUNT(*) FROM h2_baseline").fetchone()[0]
        n_inst_multi = con.execute("SELECT COUNT(*) FROM h2_multi").fetchone()[0]
        log(f"  baseline: {n_inst_baseline:,} institutions | "
            f"multi-institution: {n_inst_multi:,} institutions\n")

        rho_inst, n_shared_inst = spearman(con, "h2_baseline", "h2_multi", ["institution_id"])
        overlap10 = topn_overlap(con, "h2_baseline", "h2_multi", ["institution_id"], "h2", 10)
        overlap20 = topn_overlap(con, "h2_baseline", "h2_multi", ["institution_id"], "h2", 20)
        log(f"Institution h2 rank correlation (baseline vs multi-institution, "
            f"{n_shared_inst:,} shared): rho = {rho_inst:.4f}")
        log(f"  Top-10 overlap: {overlap10:.0%} | Top-20 overlap: {overlap20:.0%}\n")

        # Compute h₃
        log("Computing country h3: baseline vs multi-institution...")
        h3_table_sql(con, "h3_baseline", "h2_baseline")
        h3_table_sql(con, "h3_multi", "h2_multi")

        rho_country, n_shared_country = spearman(con, "h3_baseline", "h3_multi",
                                                   ["country_code"], val_col="h3")
        overlap10_c = topn_overlap(con, "h3_baseline", "h3_multi", ["country_code"], "h3", 10)
        overlap20_c = topn_overlap(con, "h3_baseline", "h3_multi", ["country_code"], "h3", 20)
        log(f"Country h3 rank correlation (baseline vs multi-institution, "
            f"{n_shared_country:,} shared): rho = {rho_country:.4f}")
        log(f"  Top-10 overlap: {overlap10_c:.0%} | Top-20 overlap: {overlap20_c:.0%}\n")

        log("Efficiency comparison for flagged countries:")
        for tname in ["h3_baseline", "h3_multi"]:
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE {tname}_ranked AS
                SELECT *, h3 / POW(institution_count, 1.0/{beta_2}) AS eps3,
                       RANK() OVER (ORDER BY h3 / POW(institution_count, 1.0/{beta_2}) DESC) AS eff_rank
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
            h3m_s = f"{h3m:>10}" if h3m is not None else f"{'n/a':>10}"
            rm_s  = f"{rm:>12}" if rm  is not None else f"{'n/a':>12}"
            em_s  = f"{em:>12.3f}" if em is not None else f"{'n/a':>12}"
            log(f"  {cc:<4}{h3b:>9}{rb:>11}{eb:>11.3f}{h3m_s}{rm_s}{em_s}")
        log("")

        log(f"Top {TOP_N} institutions by |rank shift|, multi-institution vs baseline:")
        movers = con.execute(f"""
            WITH b AS (SELECT institution_id, institution_name, h2 AS h2_base,
                              author_count AS n_base,
                              RANK() OVER (ORDER BY h2 DESC) AS rank_base FROM h2_baseline),
                 m AS (SELECT institution_id, h2 AS h2_multi, author_count AS n_multi,
                              RANK() OVER (ORDER BY h2 DESC) AS rank_multi FROM h2_multi)
            SELECT b.institution_name, b.h2_base, b.rank_base,
                   m.h2_multi, m.rank_multi, b.n_base, m.n_multi,
                   (b.rank_base - m.rank_multi) AS shift
            FROM b JOIN m USING (institution_id)
            ORDER BY ABS(shift) DESC
            LIMIT {TOP_N}
        """).fetchall()
        log(f"  {'institution':<40}{'h2_base':>8}{'rnk_base':>9}{'h2_multi':>9}"
            f"{'rnk_multi':>10}{'n_base':>8}{'n_multi':>8}{'shift':>7}")
        for name, h2b, rb, h2m, rm, nb, nm, shift in movers:
            log(f"  {str(name)[:39]:<40}{h2b:>8}{rb:>9}{h2m:>9}{rm:>10}"
                f"{nb:>8,}{nm:>8,}{shift:>7}")
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
