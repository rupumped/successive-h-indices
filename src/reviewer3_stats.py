#!/usr/bin/env python3
"""
Statistics requested by Reviewer 3 (Round 3).

Computes:
1. Centered R² for h2 ~ S^(1/beta_1) (no-intercept regression)
2. Residual size test: regress log(epsilon_2) on log(S) to check size independence
3. OLS log-log regression of h2 on S as empirical alternative to Egghe's exponent
4. Same three things at the country level (h3 ~ R^(1/beta_2))
5. Multi-field pair count clarification (how does 288,300 reduce to 229,309)

Usage:
  conda activate base
  python3 src/reviewer3_stats.py
"""

import json
import os

import duckdb
import numpy as np
from scipy import stats

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INST_CSV = os.path.join(ROOT_DIR, "data", "interim", "h2_by_institution.csv")
H2_FIELD_CSV = os.path.join(ROOT_DIR, "data", "interim", "h2_by_institution_field.csv")
H3_CSV = os.path.join(ROOT_DIR, "results", "h3_efficiency.csv")
ALPHAS_JSON = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")

MIN_AUTHORS_INST = 10   # for regression (all institutions)
MIN_AUTHORS_EFF = 100   # for efficiency ranking (matches paper)
MIN_INST_COUNTRY = 5    # for country-level


def centered_r2(y, yhat):
    """Centered R²: 1 - SS_res / SS_tot where SS_tot uses deviations from mean(y)."""
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return 1.0 - ss_res / ss_tot


def uncentered_r2(y, yhat):
    """Uncentered R²: 1 - SS_res / sum(y²)."""
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot0 = np.sum(y ** 2)
    return 1.0 - ss_res / ss_tot0


def main():
    with open(ALPHAS_JSON) as f:
        alphas = json.load(f)
    beta_1 = alphas["beta_1"]
    beta_2 = alphas["beta_2"]
    inv_b1 = 1.0 / beta_1
    inv_b2 = 1.0 / beta_2

    con = duckdb.connect()
    con.execute("SET threads=4;")

    # ── Institution level ─────────────────────────────────────────────────────
    print("=" * 70)
    print("INSTITUTION LEVEL  (h2 ~ S^(1/beta_1),  beta_1 = {:.4f})".format(beta_1))
    print("=" * 70)

    rows = con.execute(f"""
        SELECT MAX(h2) AS h2, MAX(author_count) AS S
        FROM read_csv_auto('{INST_CSV}')
        WHERE author_count >= {MIN_AUTHORS_INST}
        GROUP BY institution_id
    """).fetchall()
    h2 = np.array([r[0] for r in rows], dtype=float)
    S  = np.array([r[1] for r in rows], dtype=float)

    x_egghe = S ** inv_b1
    # No-intercept OLS: slope = sum(x*y) / sum(x²)
    c2 = np.dot(x_egghe, h2) / np.dot(x_egghe, x_egghe)
    yhat_egghe = c2 * x_egghe
    r2_unc = uncentered_r2(h2, yhat_egghe)
    r2_cen = centered_r2(h2, yhat_egghe)
    print(f"No-intercept regression  h2 = c * S^(1/beta_1):")
    print(f"  Fitted slope c2            = {c2:.4f}")
    print(f"  Uncentered R²              = {r2_unc:.4f}")
    print(f"  Centered R²                = {r2_cen:.4f}")

    # OLS log-log: log(h2) = a + b*log(S)
    log_h2 = np.log(h2)
    log_S  = np.log(S)
    slope, intercept, r_val, p_val, se = stats.linregress(log_S, log_h2)
    print(f"\nOLS log-log  log(h2) = a + b*log(S):")
    print(f"  Slope b (empirical 1/beta)  = {slope:.4f}   (vs. 1/beta_1 = {inv_b1:.4f})")
    print(f"  Intercept a                 = {intercept:.4f}")
    print(f"  R² (centered, OLS)          = {r_val**2:.4f}")
    print(f"  p-value for slope           = {p_val:.2e}")
    print(f"  Implied beta from slope     = {1/slope:.4f}   (vs. beta_1 = {beta_1:.4f})")

    # Size-independence test for epsilon_2
    epsilon2 = h2 / x_egghe          # raw ε₂ (not normalized by c2)
    epsilon2_norm = h2 / (c2 * x_egghe)  # normalized by full fitted value
    log_eps2 = np.log(epsilon2)
    log_eps2_norm = np.log(epsilon2_norm)

    # Restrict to MIN_AUTHORS_EFF for the efficiency ranking
    mask = S >= MIN_AUTHORS_EFF
    s_eff, eps2_eff, eps2n_eff = log_S[mask], log_eps2[mask], log_eps2_norm[mask]

    slope_raw, _, rv_raw, pv_raw, _ = stats.linregress(s_eff, eps2_eff)
    slope_norm, _, rv_norm, pv_norm, _ = stats.linregress(s_eff, eps2n_eff)
    print(f"\nSize-independence test for ε₂ (institutions with ≥{MIN_AUTHORS_EFF} authors, n={mask.sum():,}):")
    print(f"  log(ε₂ raw)  ~ log(S): slope={slope_raw:.4f}, R²={rv_raw**2:.4f}, p={pv_raw:.2e}")
    print(f"  log(ε₂ norm) ~ log(S): slope={slope_norm:.4f}, R²={rv_norm**2:.4f}, p={pv_norm:.2e}")
    if abs(slope_raw) < 0.05:
        print("  → Near-zero slope: normalization successfully removes size dependence.")
    else:
        print(f"  → Residual size association: slope = {slope_raw:.4f} (size still explains some variance).")

    # ── Country level ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("COUNTRY LEVEL  (h3 ~ R^(1/beta_2),  beta_2 = {:.4f})".format(beta_2))
    print("=" * 70)

    rows3 = con.execute(f"""
        SELECT h3, institution_count AS R
        FROM read_csv_auto('{H3_CSV}')
        WHERE institution_count >= {MIN_INST_COUNTRY}
    """).fetchall()
    h3 = np.array([r[0] for r in rows3], dtype=float)
    R  = np.array([r[1] for r in rows3], dtype=float)

    x_egghe3 = R ** inv_b2
    c3 = np.dot(x_egghe3, h3) / np.dot(x_egghe3, x_egghe3)
    yhat3 = c3 * x_egghe3
    r2_unc3 = uncentered_r2(h3, yhat3)
    r2_cen3 = centered_r2(h3, yhat3)
    print(f"No-intercept regression  h3 = c * R^(1/beta_2):")
    print(f"  Fitted slope c3            = {c3:.4f}")
    print(f"  Uncentered R²              = {r2_unc3:.4f}")
    print(f"  Centered R²                = {r2_cen3:.4f}")

    log_h3 = np.log(h3)
    log_R  = np.log(R)
    slope3, intercept3, r_val3, p_val3, se3 = stats.linregress(log_R, log_h3)
    print(f"\nOLS log-log  log(h3) = a + b*log(R):")
    print(f"  Slope b (empirical 1/beta)  = {slope3:.4f}   (vs. 1/beta_2 = {inv_b2:.4f})")
    print(f"  Intercept a                 = {intercept3:.4f}")
    print(f"  R² (centered, OLS)          = {r_val3**2:.4f}")
    print(f"  p-value for slope           = {p_val3:.2e}")
    print(f"  Implied beta from slope     = {1/slope3:.4f}   (vs. beta_2 = {beta_2:.4f})")

    epsilon3 = h3 / x_egghe3
    epsilon3_norm = h3 / (c3 * x_egghe3)
    log_eps3 = np.log(epsilon3)
    log_eps3_norm = np.log(epsilon3_norm)
    slope3r, _, rv3r, pv3r, _ = stats.linregress(log_R, log_eps3)
    slope3n, _, rv3n, pv3n, _ = stats.linregress(log_R, log_eps3_norm)
    print(f"\nSize-independence test for ε₃ (n={len(h3):,}):")
    print(f"  log(ε₃ raw)  ~ log(R): slope={slope3r:.4f}, R²={rv3r**2:.4f}, p={pv3r:.2e}")
    print(f"  log(ε₃ norm) ~ log(R): slope={slope3n:.4f}, R²={rv3n**2:.4f}, p={pv3n:.2e}")

    # ── Multi-field pair count clarification ──────────────────────────────────
    print()
    print("=" * 70)
    print("MULTI-FIELD PAIR COUNT CLARIFICATION")
    print("=" * 70)
    total_pairs = con.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT institution_id, field FROM read_csv_auto('{H2_FIELD_CSV}')
            GROUP BY institution_id, field
        )
    """).fetchone()[0]
    pairs_h2_gt0 = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{H2_FIELD_CSV}') WHERE h2 > 0
    """).fetchone()[0]
    pairs_min10 = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{H2_FIELD_CSV}') WHERE author_count >= 10
    """).fetchone()[0]
    pairs_min1 = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{H2_FIELD_CSV}') WHERE author_count >= 1
    """).fetchone()[0]
    print(f"Total (institution, field) pairs in field CSV:  {total_pairs:,}")
    print(f"  with author_count ≥  1:  {pairs_min1:,}")
    print(f"  with author_count ≥ 10:  {pairs_min10:,}")
    print(f"  with h2 > 0:             {pairs_h2_gt0:,}")
    print(f"Paper states 288,300 in Sec 2.4 and 229,309 as robustness baseline in Sec 3.4.")

    # ── 18% vs 21.5% percentage fix ───────────────────────────────────────────
    print()
    print("=" * 70)
    print("MULTI-INSTITUTION PERCENTAGE FIX")
    print("=" * 70)
    multi_count = 2858984
    total_authors = 13300000  # approximate
    print(f"2,858,984 / 13,300,000 = {multi_count/total_authors*100:.1f}%  (text says 18.0%, should be ~21.5%)")
    # Get actual total author count from data
    actual_total = con.execute(f"""
        SELECT COUNT(*) FROM read_csv_auto('{os.path.join(ROOT_DIR, "data", "interim", "authors.csv")}')
    """).fetchone()[0]
    print(f"Actual author count in authors.csv: {actual_total:,}")
    print(f"2,858,984 / {actual_total:,} = {multi_count/actual_total*100:.1f}%")


if __name__ == "__main__":
    main()
