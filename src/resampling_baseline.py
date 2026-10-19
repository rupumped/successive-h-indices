#!/usr/bin/env python3
"""
Resampling baseline: tests whether empirical h₂ values exceed what would be
expected if each institution's author roster were a random draw from the full
13.3M-author pool.

Analytical method (primary): for a roster of S authors drawn at random, the
expected h₂ is the largest n satisfying S × SF(n) ≥ n, where SF is the
empirical survival function of h₁ across all authors.  This is the expected
number of authors with h₁ ≥ n (Binomial mean = S × SF(n)), so the result is
the expected h₂ under the random-draw null.

Monte Carlo cross-check: K random draws at a grid of institution sizes, used
to validate the analytical result and to obtain 95th-percentile thresholds.

Output:
  results/resampling_baseline.csv         — per-institution comparison
  results/resampling_baseline_summary.json — regression stats and ratios
  results/resampling_baseline_mc.csv       — MC grid (size, mean, p95)

Usage:
  python3 resampling_baseline.py

Runtime: ~5-10 min (dominated by sorting 500 samples at the largest sizes).
"""

import json
import os
import time

import duckdb
import numpy as np
from scipy import stats

ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR = os.path.join(ROOT_DIR, "data", "interim")
AUTHORS_CSV = os.path.join(INTERIM_DIR, "authors.csv")
H2_INST_CSV = os.path.join(INTERIM_DIR, "h2_by_institution.csv")
ALPHAS_JSON = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_CSV     = os.path.join(ROOT_DIR, "results", "resampling_baseline.csv")
OUT_JSON    = os.path.join(ROOT_DIR, "results", "resampling_baseline_summary.json")
OUT_MC_CSV  = os.path.join(ROOT_DIR, "results", "resampling_baseline_mc.csv")

RNG_SEED   = 42
MC_TRIALS  = 500   # Monte Carlo trials per size point
MC_N_SIZES = 25    # number of log-spaced sizes in the MC validation grid
MIN_AUTHORS = 100  # minimum roster size included in per-institution table


def h_index_rows(matrix: np.ndarray) -> np.ndarray:
    """h-index of each row of a K × S matrix sorted descending within rows.

    h = number of positions where value ≥ rank (1-indexed), which equals
    sum(row >= ranks) because the sorted-descending order makes the mask
    monotonically non-increasing.
    """
    ranks = np.arange(1, matrix.shape[1] + 1, dtype=matrix.dtype)
    return (matrix >= ranks).sum(axis=1).astype(np.int32)


def analytical_h2(S: int, sf_counts: np.ndarray) -> int:
    """Expected h₂ for a random draw of S from the pool.

    sf_counts[n] = number of pool authors with h₁ ≥ n+1 (0-indexed: index 0
    is count of h₁ ≥ 1, index k is count of h₁ ≥ k+1).

    Returns largest n such that S × SF(n) ≥ n, i.e. S * sf_counts[n-1] / N ≥ n.
    We store raw counts rather than fractions to avoid float precision issues.
    """
    N = sf_counts[0]  # total pool size = count of h₁ ≥ 1
    # iterate from large n down; first n satisfying the condition is the answer
    for n in range(len(sf_counts), 0, -1):
        if S * sf_counts[n - 1] >= n * N:
            return n
    return 0


def main():
    for p in (AUTHORS_CSV, H2_INST_CSV, ALPHAS_JSON):
        if not os.path.exists(p):
            raise SystemExit(f"ERROR: {p} not found.")

    with open(ALPHAS_JSON) as f:
        exponents = json.load(f)
    beta_1   = exponents["beta_1"]
    inv_b1   = 1.0 / beta_1
    c2_empirical = 2.422  # from h2_efficiency.py no-intercept regression

    con = duckdb.connect()
    con.execute("SET threads=4;")

    # ------------------------------------------------------------------ #
    # 1. Load h₁ values                                                   #
    # ------------------------------------------------------------------ #
    t0 = time.time()
    print("Loading h₁ values...", end=" ", flush=True)
    h1 = con.execute(
        f"SELECT h_index FROM read_csv_auto('{AUTHORS_CSV}') WHERE h_index > 0"
    ).fetchnumpy()["h_index"].astype(np.uint16)
    N_pool = len(h1)
    max_h1 = int(h1.max())
    print(f"{N_pool:,} authors, max h₁ = {max_h1}  ({time.time()-t0:.0f}s)")

    # ------------------------------------------------------------------ #
    # 2. Empirical survival function  SF[n] = #{h₁ ≥ n}                  #
    # ------------------------------------------------------------------ #
    print("Computing empirical survival function...", end=" ", flush=True)
    # sf_counts[n-1] = #{h₁ ≥ n}  for n = 1 .. max_h1
    value_counts = np.bincount(h1, minlength=max_h1 + 1)  # index = h₁ value
    # cumulative from the right: sf_counts[n] = sum of value_counts[n:]
    sf_counts = np.cumsum(value_counts[::-1])[::-1]       # sf_counts[n] = #{h₁ ≥ n}
    # sf_counts[0] = total (all h₁ ≥ 0, but h1 > 0 so = N_pool)
    # sf_counts[n] = #{h₁ ≥ n}  for n = 0..max_h1
    # For the formula we need sf_counts[n] for n = 1..max_h1
    # analytical_h2 uses 0-indexed: sf_counts[n-1] = #{h₁ ≥ n}
    sf_for_analytical = sf_counts[1:]  # sf_for_analytical[n-1] = #{h₁ ≥ n}
    print(f"done  (SF[1]={sf_counts[1]:,}/{N_pool:,} = {sf_counts[1]/N_pool:.4f})")

    # ------------------------------------------------------------------ #
    # 3. Load institution data                                             #
    # ------------------------------------------------------------------ #
    print("Loading institution data...", end=" ", flush=True)
    rows = con.execute(f"""
        SELECT institution_id, arg_max(institution_name, h2) AS institution_name,
               MAX(h2) AS h2, MAX(author_count) AS author_count
        FROM read_csv_auto('{H2_INST_CSV}')
        GROUP BY institution_id
        HAVING MAX(author_count) >= {MIN_AUTHORS}
        ORDER BY MAX(author_count) DESC
    """).fetchall()
    print(f"{len(rows):,} institutions (≥{MIN_AUTHORS} authors)")

    # ------------------------------------------------------------------ #
    # 4. Analytical expected h₂ for every institution                     #
    # ------------------------------------------------------------------ #
    print("Computing analytical random-draw baseline...", end=" ", flush=True)
    t0 = time.time()
    results = []
    for inst_id, inst_name, h2_emp, S in rows:
        h2_rand = analytical_h2(S, sf_for_analytical)
        ratio   = h2_emp / h2_rand if h2_rand > 0 else float("nan")
        results.append((inst_id, inst_name, S, h2_emp, h2_rand, ratio))
    print(f"done  ({time.time()-t0:.1f}s)")

    # ------------------------------------------------------------------ #
    # 5. Fit c_random: no-intercept regression h₂_random ~ c × S^(1/β₁) #
    # ------------------------------------------------------------------ #
    S_arr       = np.array([r[2] for r in results], dtype=float)
    h2_emp_arr  = np.array([r[3] for r in results], dtype=float)
    h2_rand_arr = np.array([r[4] for r in results], dtype=float)
    ratio_arr   = np.array([r[5] for r in results], dtype=float)
    scale_arr   = S_arr ** inv_b1    # S^(1/β₁)

    valid = np.isfinite(ratio_arr) & (h2_rand_arr > 0)
    # no-intercept OLS: c = Σ(y·x) / Σ(x²)
    c_random = float(np.dot(h2_rand_arr[valid], scale_arr[valid]) /
                     np.dot(scale_arr[valid], scale_arr[valid]))
    c_ratio  = c2_empirical / c_random   # quality-sorting factor

    print(f"\nAnalytical results:")
    print(f"  c_random  (random-draw no-intercept coeff) = {c_random:.4f}")
    print(f"  c2_empirical                               = {c2_empirical:.4f}")
    print(f"  c2 / c_random  (quality-sorting factor)    = {c_ratio:.3f}")
    print(f"  Fraction of institutions with h₂ > h₂_random: "
          f"{(h2_emp_arr[valid] > h2_rand_arr[valid]).mean():.3f}")
    print(f"  Median ratio h₂_empirical / h₂_random:        "
          f"{np.median(ratio_arr[valid]):.3f}")
    print(f"  Mean   ratio h₂_empirical / h₂_random:        "
          f"{ratio_arr[valid].mean():.3f}")
    print(f"  Pct of institutions with ratio > 2.0:          "
          f"{(ratio_arr[valid] > 2.0).mean()*100:.1f}%")

    # ------------------------------------------------------------------ #
    # 6. Monte Carlo cross-check on a size grid                           #
    # ------------------------------------------------------------------ #
    rng = np.random.default_rng(RNG_SEED)
    size_min = int(S_arr.min())
    size_max = int(S_arr.max())
    mc_sizes = np.unique(
        np.round(np.logspace(np.log10(size_min), np.log10(size_max),
                             MC_N_SIZES)).astype(int)
    )
    print(f"\nMonte Carlo cross-check: {MC_TRIALS} trials at {len(mc_sizes)} sizes "
          f"({size_min}–{size_max})...")

    mc_rows = []
    for i, S_mc in enumerate(mc_sizes, 1):
        t0 = time.time()
        # Draw K × S matrix of h₁ values; sort each row descending
        idx     = rng.integers(0, N_pool, size=(MC_TRIALS, S_mc))
        samples = np.sort(h1[idx], axis=1)[:, ::-1]
        h2_mc   = h_index_rows(samples)
        h2_analytical = analytical_h2(S_mc, sf_for_analytical)
        mc_rows.append((
            int(S_mc),
            float(h2_mc.mean()),
            float(np.percentile(h2_mc, 5)),
            float(np.percentile(h2_mc, 95)),
            int(h2_analytical),
        ))
        print(f"  [{i:2d}/{len(mc_sizes)}] S={S_mc:6,d}  "
              f"MC mean={h2_mc.mean():.2f}  p5={np.percentile(h2_mc,5):.1f}  "
              f"p95={np.percentile(h2_mc,95):.1f}  "
              f"analytical={h2_analytical}  ({time.time()-t0:.1f}s)")

    # c_random from MC (more accurate than analytical due to Jensen's inequality)
    mc_S    = np.array([r[0] for r in mc_rows], dtype=float)
    mc_mean = np.array([r[1] for r in mc_rows], dtype=float)
    c_random_mc = float(np.dot(mc_mean, mc_S ** inv_b1) /
                        np.dot(mc_S ** inv_b1, mc_S ** inv_b1))
    print(f"\nMC c_random = {c_random_mc:.4f}  "
          f"(analytical c_random = {c_random:.4f}  —  "
          f"{'agree' if abs(c_random_mc - c_random) < 0.02 else 'DISCREPANCY'})")

    # MC-model-based fraction: compare each institution to c_random_mc × S^(1/β₁)
    h2_rand_mc_model = c_random_mc * scale_arr
    frac_above_mc = float((h2_emp_arr[valid] > h2_rand_mc_model[valid]).mean())
    median_ratio_mc = float(np.median(h2_emp_arr[valid] / h2_rand_mc_model[valid]))
    print(f"\nMC-model comparison (h₂ vs. c_random_mc × S^(1/β₁)):")
    print(f"  Fraction above MC-model baseline:  {frac_above_mc:.3f}")
    print(f"  Median ratio h₂_emp / h₂_null_mc:  {median_ratio_mc:.3f}")

    # ------------------------------------------------------------------ #
    # 7. Write outputs                                                     #
    # ------------------------------------------------------------------ #
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

    # per-institution CSV
    with open(OUT_CSV, "w") as f:
        f.write("institution_id,institution_name,author_count,"
                "h2_empirical,h2_random,ratio\n")
        for inst_id, inst_name, S, h2_emp, h2_rand, ratio in results:
            safe_name = str(inst_name).replace('"', '""')
            f.write(f'"{inst_id}","{safe_name}",{S},{h2_emp},{h2_rand},'
                    f'{ratio:.4f}\n')
    print(f"\nWrote {OUT_CSV}")

    # MC grid CSV
    with open(OUT_MC_CSV, "w") as f:
        f.write("size,mc_mean,mc_p5,mc_p95,analytical\n")
        for row in mc_rows:
            f.write(",".join(str(v) for v in row) + "\n")
    print(f"Wrote {OUT_MC_CSV}")

    # summary JSON
    summary = {
        "beta_1":                  beta_1,
        "c2_empirical":            c2_empirical,
        "c_random_analytical":     c_random,
        "c_random_mc":             c_random_mc,
        "n_institutions":          int(valid.sum()),
        "frac_above_random_analytical": float((h2_emp_arr[valid] > h2_rand_arr[valid]).mean()),
        "frac_above_random_mc":    frac_above_mc,
        "median_ratio_analytical": float(np.median(ratio_arr[valid])),
        "median_ratio_mc":         median_ratio_mc,
        "mean_ratio_analytical":   float(ratio_arr[valid].mean()),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
