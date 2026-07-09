#!/usr/bin/env python3
"""
H2 efficiency: H2 / author_count^(1/beta_1).

A large institution can achieve high H2 simply by having many researchers, even if most are mediocre. Normalizing by author_count^(1/beta_1) adjusts for size and surfaces institutions whose talent is unusually concentrated relative to how many people they employ.

beta_1 = alpha_0*alpha_1 is the compound Lotka exponent from Egghe (2008), eq. 11: h2 = author_count^(1/(alpha_0*alpha_1)). It is fit empirically by estimate_alphas.py (the tail exponent of the h1 distribution across authors, his eq. 7) and read from results/lotka_exponents.json here. Run estimate_alphas.py first.

Also shows the most efficient institution per field.

Output: h2_efficiency.csv

Usage:
  python3 estimate_alphas.py   # once, to produce lotka_exponents.json
  python3 h2_efficiency.py
"""

import json
import duckdb
import os

ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR = os.path.join(ROOT_DIR, "data", "interim")
INST_CSV    = os.path.join(INTERIM_DIR, "h2_by_institution.csv")
FIELD_CSV   = os.path.join(INTERIM_DIR, "h2_by_institution_field.csv")
ALPHAS_JSON = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_CSV     = os.path.join(ROOT_DIR, "results", "h2_efficiency.csv")

TOP_N       = 30
MIN_AUTHORS = 100   # exclude institutions too small to be meaningful


def main():
    for p in (INST_CSV, FIELD_CSV, ALPHAS_JSON):
        if not os.path.exists(p):
            raise SystemExit(f"ERROR: {p} not found." + (
                " Run estimate_alphas.py first." if p == ALPHAS_JSON else ""
            ))

    with open(ALPHAS_JSON) as f:
        beta_1 = json.load(f)["beta_1"]
    inv_beta_1 = 1.0 / beta_1
    print(f"Using beta_1 = alpha_0*alpha_1 = {beta_1:.4f}  (efficiency = h2 / author_count^{inv_beta_1:.4f})\n")

    con = duckdb.connect()
    con.execute("SET threads=4;")

    con.execute(f"""
        COPY (
            WITH deduped AS (
                SELECT institution_id,
                       arg_max(institution_name, h2) AS institution_name,
                       MAX(h2)            AS h2,
                       MAX(author_count)  AS author_count
                FROM read_csv_auto('{INST_CSV}')
                GROUP BY institution_id
            )
            SELECT institution_id, institution_name, h2, author_count,
                   ROUND(h2 / POWER(author_count, {inv_beta_1}), 4) AS efficiency,
                   ROW_NUMBER() OVER (ORDER BY h2 DESC, institution_name)                                AS h2_rank,
                   ROW_NUMBER() OVER (ORDER BY h2 / POWER(author_count, {inv_beta_1}) DESC, institution_name) AS efficiency_rank
            FROM deduped
            WHERE author_count >= {MIN_AUTHORS}
            ORDER BY efficiency DESC, institution_name
        ) TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{OUT_CSV}')").fetchone()[0]
    print(f"{n:,} institutions (author_count ≥ {MIN_AUTHORS}) → {OUT_CSV}\n")

    hdr = f"  {'Institution':<45} {'EffRk':>6} {'Eff':>6} {'H2Rk':>6} {'H2':>4} {'Authors':>8} {'Δrank':>6}"
    sep = "  " + "-" * (len(hdr) - 2)

    print(f"Top {TOP_N} by efficiency (H2 / author_count^{inv_beta_1:.3f}):")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, efficiency_rank, efficiency, h2_rank, h2, author_count,
               (h2_rank - efficiency_rank) AS rank_change
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY efficiency_rank
        LIMIT {TOP_N}
    """).fetchall()
    for name, eff_rk, eff, h2_rk, h2, auth, delta in rows:
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {str(name)[:44]:<45} {eff_rk:>6} {eff:>6.2f} {h2_rk:>6} {h2:>4} {auth:>8,} {ds:>6}")

    print(f"\nTop {TOP_N} by raw H2 for comparison:")
    print(hdr); print(sep)
    rows = con.execute(f"""
        SELECT institution_name, efficiency_rank, efficiency, h2_rank, h2, author_count,
               (h2_rank - efficiency_rank) AS rank_change
        FROM read_csv_auto('{OUT_CSV}')
        ORDER BY h2_rank
        LIMIT {TOP_N}
    """).fetchall()
    for name, eff_rk, eff, h2_rk, h2, auth, delta in rows:
        ds = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {str(name)[:44]:<45} {eff_rk:>6} {eff:>6.2f} {h2_rk:>6} {h2:>4} {auth:>8,} {ds:>6}")

    # Most efficient institution per field
    print(f"\nMost efficient institution per field (author_count ≥ {MIN_AUTHORS}):")
    print(f"  {'Field':<45} {'Institution':<35} {'Eff':>6} {'H2':>4} {'Authors':>8} {'H2Rk':>6}")
    print("  " + "-" * 112)
    rows = con.execute(f"""
        WITH ranked AS (
            SELECT field_name, institution_name, h2, author_count,
                   ROUND(h2 / POWER(author_count, {inv_beta_1}), 2) AS eff,
                   ROW_NUMBER() OVER (PARTITION BY field ORDER BY h2 DESC, institution_name) AS h2_rank,
                   ROW_NUMBER() OVER (PARTITION BY field ORDER BY h2 / POWER(author_count, {inv_beta_1}) DESC, institution_name) AS eff_rank
            FROM read_csv_auto('{FIELD_CSV}')
            WHERE author_count >= {MIN_AUTHORS}
        )
        SELECT field_name, institution_name, eff, h2, author_count, h2_rank
        FROM ranked
        WHERE eff_rank = 1
        ORDER BY field_name
    """).fetchall()
    for fname, inst, eff, h2, auth, h2_rk in rows:
        print(f"  {str(fname)[:44]:<45} {str(inst)[:34]:<35} {eff:>6.2f} {h2:>4} {auth:>8,} {h2_rk:>6}")


if __name__ == "__main__":
    main()
