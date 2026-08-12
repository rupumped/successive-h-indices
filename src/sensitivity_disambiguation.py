#!/usr/bin/env python3
"""
Sensitivity analysis: how much author-disambiguation-style error would it
take, at the magnitude actually observed in manual cross-validation, before
the paper's institution- and country-level rankings changed?

Perturbation model: at a population-wide "error rate" p, each author is
independently flagged with probability p as a merged/inflated identity, and
a flagged author's h1 is multiplied by an inflation ratio drawn uniformly
from the four ratios actually observed among the manual cross-validation
outliers (Donald Small 103/57, Karen Calhoun 45/11, Lei Jiang 215/115,
A. Jafari 139/41 vs. Web of Science). The 21% outlier rate (4/19) in that
sample comes from a deliberately adversarial, non-random selection
(threshold authors, non-Anglophone institutions, common names) enriched for
exactly the strata most likely to carry disambiguation errors, so treating
21% as a population-wide error rate is a worst-case stress test, not a
claim about the dataset's true error rate; 1% and 5% are included as more
plausible population-wide rates.

For each trial, recomputes institution-overall h2, country h3, and the
within-field h2 ranking for two headline field-leader claims (Wageningen in
Agricultural & Biological Sciences and Environmental Science; Carnegie
Mellon in Computer Science), and compares each to the unperturbed baseline.

Usage:
  python3 sensitivity_disambiguation.py
"""

import csv
import os
import time

import duckdb

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
COUNTRY_MAP_CSV = os.path.join(ROOT_DIR, "data", "interim", "institution_country_map.csv")
OUT_CSV = os.path.join(ROOT_DIR, "results", "sensitivity_disambiguation.csv")
LOG_PATH = os.path.join(ROOT_DIR, "results", "sensitivity_disambiguation.log")

RATIOS = [103 / 57, 45 / 11, 215 / 115, 139 / 41]

WAGENINGEN_ID = "https://openalex.org/I913481162"
CMU_ID = "https://openalex.org/I74973139"
TARGET_FIELDS = {
    "https://openalex.org/fields/11": ("Agricultural and Biological Sciences", WAGENINGEN_ID),
    "https://openalex.org/fields/23": ("Environmental Science", WAGENINGEN_ID),
    "https://openalex.org/fields/17": ("Computer Science", CMU_ID),
}

ERROR_RATES = [0.20, 0.40, 0.80]
TRIALS_PER_RATE = 5
TOP_K = 20

FIELDNAMES = [
    "error_rate", "trial", "seed",
    "spearman_h2_institution", "top20_overlap_institution",
    "spearman_h3_country", "top10_overlap_country",
    "italy_h3", "japan_h3",
    "wageningen_agbio_rank", "wageningen_envsci_rank", "cmu_cs_rank",
    "elapsed_s",
]


def log(msg):
    print(msg, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")


def build_perturbed(con, seed, error_rate):
    con.execute(f"SELECT setseed({seed})")
    ratio_case = (
        "CASE CAST(FLOOR(random()*4) AS INTEGER) "
        f"WHEN 0 THEN {RATIOS[0]}::DOUBLE WHEN 1 THEN {RATIOS[1]}::DOUBLE "
        f"WHEN 2 THEN {RATIOS[2]}::DOUBLE ELSE {RATIOS[3]}::DOUBLE END"
    )
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE perturbed AS
        SELECT institution_id, field,
            CASE WHEN random() < {error_rate}
                 THEN CAST(ROUND(CAST(h_index AS DOUBLE) * ({ratio_case})) AS INTEGER)
                 ELSE h_index
            END AS h_index
        FROM authors_mem
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


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("SET threads=16; SET enable_progress_bar=false; SET memory_limit='6GB';")

    log("Loading authors into memory...")
    t0 = time.time()
    con.execute("CREATE TEMP TABLE authors_mem AS SELECT institution_id, field, h_index FROM authors")
    log(f"  {time.time()-t0:.1f}s")

    con.execute(f"CREATE TEMP TABLE country_map AS SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP_CSV}')")

    log("Computing baseline (error_rate=0)...")
    t0 = time.time()
    build_perturbed(con, seed=0.0, error_rate=0.0)
    compute_institution_h2(con, "h2_base")
    compute_country_h3(con, "h2_base", "h3_base")
    base_field_ranks = compute_field_ranks(con)
    log(f"  {time.time()-t0:.1f}s")

    wag_agbio_base = base_field_ranks["https://openalex.org/fields/11"].get(WAGENINGEN_ID)
    wag_env_base = base_field_ranks["https://openalex.org/fields/23"].get(WAGENINGEN_ID)
    cmu_cs_base = base_field_ranks["https://openalex.org/fields/17"].get(CMU_ID)
    it_base = con.execute("SELECT h3 FROM h3_base WHERE country_code='IT'").fetchone()
    jp_base = con.execute("SELECT h3 FROM h3_base WHERE country_code='JP'").fetchone()
    log(f"  baseline: Wageningen Ag&Bio rank={wag_agbio_base}, EnvSci rank={wag_env_base}, "
        f"CMU CS rank={cmu_cs_base}, Italy h3={it_base}, Japan h3={jp_base}")

    file_exists = os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()

        for error_rate in ERROR_RATES:
            for trial in range(TRIALS_PER_RATE):
                seed = round(0.01 * (trial + 1) + error_rate, 6)
                t0 = time.time()
                build_perturbed(con, seed=seed, error_rate=error_rate)
                compute_institution_h2(con, "h2_pert")
                compute_country_h3(con, "h2_pert", "h3_pert")
                field_ranks = compute_field_ranks(con)

                sp_h2, ov_h2 = spearman_and_overlap(con, "h2_base", "h2_pert", "institution_id", "h2", TOP_K)
                sp_h3, ov_h3 = spearman_and_overlap(con, "h3_base", "h3_pert", "country_code", "h3", 10)

                it = con.execute("SELECT h3 FROM h3_pert WHERE country_code='IT'").fetchone()
                jp = con.execute("SELECT h3 FROM h3_pert WHERE country_code='JP'").fetchone()

                wag_agbio = field_ranks["https://openalex.org/fields/11"].get(WAGENINGEN_ID)
                wag_env = field_ranks["https://openalex.org/fields/23"].get(WAGENINGEN_ID)
                cmu_cs = field_ranks["https://openalex.org/fields/17"].get(CMU_ID)

                elapsed = time.time() - t0
                row = {
                    "error_rate": error_rate, "trial": trial, "seed": seed,
                    "spearman_h2_institution": sp_h2, "top20_overlap_institution": ov_h2,
                    "spearman_h3_country": sp_h3, "top10_overlap_country": ov_h3,
                    "italy_h3": it[0] if it else None, "japan_h3": jp[0] if jp else None,
                    "wageningen_agbio_rank": wag_agbio, "wageningen_envsci_rank": wag_env,
                    "cmu_cs_rank": cmu_cs, "elapsed_s": round(elapsed, 1),
                }
                writer.writerow(row)
                f.flush()
                log(f"  p={error_rate:.2f} trial={trial}: spearman_h2={sp_h2:.4f} top20_ov={ov_h2:.2f} "
                    f"spearman_h3={sp_h3:.4f} top10_ov={ov_h3:.2f} IT/JP h3={it[0] if it else '-'}/"
                    f"{jp[0] if jp else '-'} wag_agbio={wag_agbio} wag_env={wag_env} cmu_cs={cmu_cs} "
                    f"({elapsed:.1f}s)")

    log(f"\nWrote results to {OUT_CSV}")


if __name__ == "__main__":
    main()
