#!/usr/bin/env python3
"""
Sensitivity analysis: how much author-disambiguation-style error would it
take, at the magnitude actually observed in manual cross-validation, before
the paper's institution- and country-level rankings changed?

Scenarios
---------
bidirectional         existing design: each flagged author is inflated OR deflated
                      with equal probability (symmetric, captures both merge and
                      split errors).
directional           inflation-only: all flagged authors are inflated (simulates a
                      pure over-merge environment with no corrective splits).
threshold             only authors whose h₁ falls within ±5 of their institution's
                      baseline h₂ are eligible for perturbation (the authors who
                      most directly determine rank-threshold crossings); perturbation
                      is bidirectional for those flagged.
bidirectional_uniform bidirectional but without country-stratification (uniform error
                      rate for all countries; see Comment 5c response).

Perturbation model
------------------
At a population-wide "error rate" p, each eligible author is independently
flagged with probability p (country-stratified where applicable).  Flagged
authors receive a perturbation drawn uniformly from the four ratios observed in
manual cross-validation: Donald Small 103/57, Karen Calhoun 45/11, Lei Jiang
215/115, A. Jafari 139/41 (vs. Web of Science).

Country-stratified error rates: authors affiliated with CN, KR, IR, or SA
receive HIGH_ERROR_MULT times the base error rate.

Usage:
  conda activate base
  python3 src/sensitivity_disambiguation.py
"""

import csv
import os
import time

import duckdb
import tqdm

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
COUNTRY_MAP_CSV = os.path.join(ROOT_DIR, "data", "interim", "institution_country_map.csv")
OUT_CSV = os.path.join(ROOT_DIR, "results", "sensitivity_disambiguation.csv")
LOG_PATH = os.path.join(ROOT_DIR, "results", "sensitivity_disambiguation.log")

RATIOS = [103 / 57, 45 / 11, 215 / 115, 139 / 41]

HIGH_ERROR_COUNTRIES = {"CN", "KR", "IR", "SA"}
HIGH_ERROR_MULT = 3.0

WAGENINGEN_ID = "https://openalex.org/I913481162"
CMU_ID = "https://openalex.org/I74973139"
UCAS_ID = "https://openalex.org/I4210165038"
TARGET_FIELDS = {
    "https://openalex.org/fields/11": ("Agricultural and Biological Sciences", WAGENINGEN_ID),
    "https://openalex.org/fields/23": ("Environmental Science", UCAS_ID),
    "https://openalex.org/fields/17": ("Computer Science", CMU_ID),
}

ERROR_RATES = [0.01, 0.05, 0.1, 0.13, 0.20, 0.40, 0.80]
TRIALS_PER_RATE = 50
TOP_K = 20

SCENARIOS = [
    "bidirectional",
    "directional",
    "threshold",
    "bidirectional_uniform",
]

FIELDNAMES = [
    "scenario", "error_rate", "trial", "seed",
    "spearman_h2_institution", "top20_overlap_institution",
    "spearman_h3_country", "top10_overlap_country",
    "italy_h3", "japan_h3",
    "wageningen_agbio_rank", "ucas_envsci_rank", "cmu_cs_rank",
    "elapsed_s",
]

_RATIO_CASE = (
    "CASE CAST(FLOOR(r_ratio * 4) AS INTEGER) "
    f"WHEN 0 THEN {RATIOS[0]}::DOUBLE WHEN 1 THEN {RATIOS[1]}::DOUBLE "
    f"WHEN 2 THEN {RATIOS[2]}::DOUBLE ELSE {RATIOS[3]}::DOUBLE END"
)
_HIGH_CC = ", ".join(f"'{cc}'" for cc in sorted(HIGH_ERROR_COUNTRIES))


def log(msg):
    tqdm.tqdm.write(msg)
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")


def _flag_expr(error_rate, stratified):
    """SQL expression for whether an author is flagged (True/False)."""
    if stratified:
        return (
            f"r_flag < LEAST(1.0, CASE WHEN country_code IN ({_HIGH_CC}) "
            f"THEN {error_rate} * {HIGH_ERROR_MULT} "
            f"ELSE {error_rate} END)"
        )
    else:
        return f"r_flag < LEAST(1.0, {error_rate}::DOUBLE)"


def build_perturbed_bidirectional(con, seed, error_rate, stratified=True):
    """Bidirectional: flagged authors are inflated OR deflated with equal probability."""
    con.execute(f"SELECT setseed({seed})")
    flag = _flag_expr(error_rate, stratified)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE perturbed AS
        WITH draws AS (
            SELECT institution_id, field, h_index, country_code,
                   random() AS r_flag,
                   random() AS r_dir,
                   random() AS r_ratio
            FROM authors_mem
        ),
        flagged AS (
            SELECT institution_id, field, h_index,
                   {flag} AS is_flagged,
                   r_dir,
                   {_RATIO_CASE} AS ratio
            FROM draws
        )
        SELECT institution_id, field,
            CASE WHEN is_flagged
                 THEN GREATEST(1, CAST(ROUND(CAST(h_index AS DOUBLE)
                      * CASE WHEN r_dir < 0.5 THEN ratio ELSE 1.0 / ratio END) AS INTEGER))
                 ELSE h_index
            END AS h_index
        FROM flagged
    """)


def build_perturbed_directional(con, seed, error_rate):
    """Directional (inflation-only): all flagged authors receive upward perturbation."""
    con.execute(f"SELECT setseed({seed})")
    flag = _flag_expr(error_rate, stratified=True)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE perturbed AS
        WITH draws AS (
            SELECT institution_id, field, h_index, country_code,
                   random() AS r_flag,
                   random() AS r_ratio
            FROM authors_mem
        ),
        flagged AS (
            SELECT institution_id, field, h_index,
                   {flag} AS is_flagged,
                   {_RATIO_CASE} AS ratio
            FROM draws
        )
        SELECT institution_id, field,
            CASE WHEN is_flagged
                 THEN GREATEST(1, CAST(ROUND(CAST(h_index AS DOUBLE) * ratio) AS INTEGER))
                 ELSE h_index
            END AS h_index
        FROM flagged
    """)


def build_perturbed_threshold(con, seed, error_rate, h2_base_table):
    """Threshold-concentrated: only perturb authors whose h₁ is within ±5 of their
    institution's baseline h₂ threshold; perturbation is bidirectional for those flagged."""
    con.execute(f"SELECT setseed({seed})")
    flag = _flag_expr(error_rate, stratified=True)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE perturbed AS
        WITH draws AS (
            SELECT a.institution_id, a.field, a.h_index, a.country_code,
                   random() AS r_flag,
                   random() AS r_dir,
                   random() AS r_ratio
            FROM authors_mem a
        ),
        flagged AS (
            SELECT d.institution_id, d.field, d.h_index,
                   ABS(d.h_index - COALESCE(b.h2, 0)) <= 5
                       AND {flag} AS is_flagged,
                   r_dir,
                   {_RATIO_CASE} AS ratio
            FROM draws d
            LEFT JOIN {h2_base_table} b ON b.institution_id = d.institution_id
        )
        SELECT institution_id, field,
            CASE WHEN is_flagged
                 THEN GREATEST(1, CAST(ROUND(CAST(h_index AS DOUBLE)
                      * CASE WHEN r_dir < 0.5 THEN ratio ELSE 1.0 / ratio END) AS INTEGER))
                 ELSE h_index
            END AS h_index
        FROM flagged
    """)


def compute_institution_h2(con, table_name):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {table_name} AS
        WITH ranked AS (
            SELECT institution_id, h_index,
                   ROW_NUMBER() OVER (PARTITION BY institution_id ORDER BY h_index DESC) AS rnk
            FROM perturbed
        )
        SELECT institution_id, MAX(rnk) AS h2
        FROM ranked WHERE h_index >= rnk
        GROUP BY institution_id
    """)


def compute_country_h3(con, h2_table, out_table):
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out_table} AS
        WITH joined AS (
            SELECT c.country_code, h.h2
            FROM {h2_table} h JOIN country_map c ON h.institution_id = c.id
        ), ranked AS (
            SELECT country_code, h2,
                   ROW_NUMBER() OVER (PARTITION BY country_code ORDER BY h2 DESC) AS rnk
            FROM joined
        )
        SELECT country_code, MAX(rnk) AS h3
        FROM ranked WHERE h2 >= rnk
        GROUP BY country_code
    """)


def compute_field_ranks(con):
    """Returns {field_id: {institution_id: rank}} for the three target fields."""
    out = {}
    for field_id in TARGET_FIELDS:
        rows = con.execute(f"""
            WITH field_authors AS (
                SELECT institution_id, h_index FROM perturbed WHERE field = ?
            ), ranked AS (
                SELECT institution_id, h_index,
                       ROW_NUMBER() OVER (PARTITION BY institution_id ORDER BY h_index DESC) AS rnk
                FROM field_authors
            ), h2c AS (
                SELECT institution_id, MAX(rnk) AS h2
                FROM ranked WHERE h_index >= rnk GROUP BY institution_id
            )
            SELECT institution_id, RANK() OVER (ORDER BY h2 DESC) AS rank
            FROM h2c
        """, [field_id]).fetchall()
        out[field_id] = {inst: rank for inst, rank in rows}
    return out


def spearman_and_overlap(con, base_table, pert_table, key_col, val_col, top_k):
    row = con.execute(f"""
        WITH b AS (
            SELECT {key_col}, RANK() OVER (ORDER BY {val_col} DESC) AS r
            FROM {base_table}
        ), p AS (
            SELECT {key_col}, RANK() OVER (ORDER BY {val_col} DESC) AS r
            FROM {pert_table}
        ), joined AS (
            SELECT b.r AS rb, p.r AS rp FROM b JOIN p USING ({key_col})
        )
        SELECT corr(rb, rp) FROM joined
    """).fetchone()
    spearman = row[0]

    base_top = {r[0] for r in con.execute(
        f"SELECT {key_col} FROM {base_table} ORDER BY {val_col} DESC LIMIT {top_k}"
    ).fetchall()}
    pert_top = {r[0] for r in con.execute(
        f"SELECT {key_col} FROM {pert_table} ORDER BY {val_col} DESC LIMIT {top_k}"
    ).fetchall()}
    overlap = len(base_top & pert_top) / top_k
    return spearman, overlap


def run_trial(con, scenario, seed, error_rate):
    """Build perturbed table for the given scenario and compute all metrics."""
    if scenario == "bidirectional":
        build_perturbed_bidirectional(con, seed, error_rate, stratified=True)
    elif scenario == "directional":
        build_perturbed_directional(con, seed, error_rate)
    elif scenario == "threshold":
        build_perturbed_threshold(con, seed, error_rate, "h2_base")
    elif scenario == "bidirectional_uniform":
        build_perturbed_bidirectional(con, seed, error_rate, stratified=False)
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    compute_institution_h2(con, "h2_pert")
    compute_country_h3(con, "h2_pert", "h3_pert")
    field_ranks = compute_field_ranks(con)

    sp_h2, ov_h2 = spearman_and_overlap(con, "h2_base", "h2_pert", "institution_id", "h2", TOP_K)
    sp_h3, ov_h3 = spearman_and_overlap(con, "h3_base", "h3_pert", "country_code", "h3", 10)

    it = con.execute("SELECT h3 FROM h3_pert WHERE country_code='IT'").fetchone()
    jp = con.execute("SELECT h3 FROM h3_pert WHERE country_code='JP'").fetchone()

    wag_agbio = field_ranks["https://openalex.org/fields/11"].get(WAGENINGEN_ID)
    ucas_env = field_ranks["https://openalex.org/fields/23"].get(UCAS_ID)
    cmu_cs = field_ranks["https://openalex.org/fields/17"].get(CMU_ID)

    return {
        "spearman_h2_institution": sp_h2, "top20_overlap_institution": ov_h2,
        "spearman_h3_country": sp_h3, "top10_overlap_country": ov_h3,
        "italy_h3": it[0] if it else None, "japan_h3": jp[0] if jp else None,
        "wageningen_agbio_rank": wag_agbio, "ucas_envsci_rank": ucas_env,
        "cmu_cs_rank": cmu_cs,
    }


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("SET threads=16; SET enable_progress_bar=false; SET memory_limit='6GB';")

    con.execute(f"CREATE TEMP TABLE country_map AS SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP_CSV}')")

    log("Loading authors into memory...")
    t0 = time.time()
    con.execute("""
        CREATE TEMP TABLE authors_mem AS
        SELECT a.institution_id, a.field, a.h_index, cm.country_code
        FROM authors a
        LEFT JOIN country_map cm ON cm.id = a.institution_id
    """)
    log(f"  {time.time()-t0:.1f}s")

    log("Computing baseline (error_rate=0)...")
    t0 = time.time()
    build_perturbed_bidirectional(con, seed=0.0, error_rate=0.0)
    compute_institution_h2(con, "h2_base")
    compute_country_h3(con, "h2_base", "h3_base")
    base_field_ranks = compute_field_ranks(con)
    log(f"  {time.time()-t0:.1f}s")

    wag_agbio_base = base_field_ranks["https://openalex.org/fields/11"].get(WAGENINGEN_ID)
    ucas_env_base = base_field_ranks["https://openalex.org/fields/23"].get(UCAS_ID)
    cmu_cs_base = base_field_ranks["https://openalex.org/fields/17"].get(CMU_ID)
    it_base = con.execute("SELECT h3 FROM h3_base WHERE country_code='IT'").fetchone()
    jp_base = con.execute("SELECT h3 FROM h3_base WHERE country_code='JP'").fetchone()
    log(f"  baseline: Wageningen Ag&Bio rank={wag_agbio_base}, UCAS EnvSci rank={ucas_env_base}, "
        f"CMU CS rank={cmu_cs_base}, Italy h3={it_base[0] if it_base else None}, "
        f"Japan h3={jp_base[0] if jp_base else None}")

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        total = len(SCENARIOS) * len(ERROR_RATES) * TRIALS_PER_RATE
        pbar = tqdm.tqdm(total=total, unit="trial")
        for scenario in SCENARIOS:
            log(f"\n=== Scenario: {scenario} ===")
            for error_rate in ERROR_RATES:
                for trial in range(TRIALS_PER_RATE):
                    seed = round((trial + 1) * 0.001 + error_rate * 0.01, 6)
                    t0 = time.time()
                    metrics = run_trial(con, scenario, seed, error_rate)
                    elapsed = time.time() - t0

                    row = {
                        "scenario": scenario,
                        "error_rate": error_rate, "trial": trial, "seed": seed,
                        **metrics,
                        "elapsed_s": round(elapsed, 1),
                    }
                    writer.writerow(row)
                    f.flush()
                    log(
                        f"  {scenario} p={error_rate:.2f} trial={trial}: "
                        f"spearman_h2={metrics['spearman_h2_institution']:.4f} "
                        f"top20_ov={metrics['top20_overlap_institution']:.2f} "
                        f"spearman_h3={metrics['spearman_h3_country']:.4f} "
                        f"top10_ov={metrics['top10_overlap_country']:.2f} "
                        f"wag={metrics['wageningen_agbio_rank']} "
                        f"ucas={metrics['ucas_envsci_rank']} "
                        f"cmu={metrics['cmu_cs_rank']} "
                        f"({elapsed:.1f}s)"
                    )
                    pbar.update(1)
        pbar.close()

    log(f"\nWrote {len(SCENARIOS) * len(ERROR_RATES) * TRIALS_PER_RATE} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
