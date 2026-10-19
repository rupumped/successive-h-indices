#!/usr/bin/env python3
"""
Organizational granularity sensitivity check.

Rolls each institution up to its top-level parent system within the same
country, recomputes h₂ for each merged group from the pooled h₁ distribution,
then recomputes h₃ and ε₃ per country.

This tests whether OpenAlex's within-country institutional splitting choices
drive country-level rankings: if grouping campuses under their parent system
changes h₃ or ε₃ materially, the index is sensitive to organizational
granularity.

Root identification: an institution is a root if its own lineage is a
single-element list (just itself).  For every other institution we find the
element in its lineage that (a) is itself a root and (b) has the same country
code.  Cross-border roll-ups are suppressed: if no same-country root exists,
the institution acts as its own root.

Inputs (all local):
  data/interim/authors.csv                 h₁ per author with institution_id
  data/interim/institution_types.parquet   id, type, lineage[]
  data/interim/institution_country_map.csv id → country_code
  data/interim/h3_by_country.csv           original h₃ baseline
  results/lotka_exponents.json             beta_2 for ε₃

Output: results/granularity_check.csv
  country_code, h3_orig, h3_rolled, inst_count_orig, inst_count_rolled,
  eps3_orig, eps3_rolled, h3_rank_orig, h3_rank_rolled, eps3_rank_orig,
  eps3_rank_rolled

Usage:
  python3 src/granularity_check.py
"""

import csv
import json
import os

import duckdb

ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_DIR = os.path.join(ROOT_DIR, "data", "interim")
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

AUTHORS_CSV   = os.path.join(INTERIM_DIR, "authors.csv")
INST_TYPES    = os.path.join(INTERIM_DIR, "institution_types.parquet")
COUNTRY_MAP   = os.path.join(INTERIM_DIR, "institution_country_map.csv")
H3_ORIG_CSV   = os.path.join(INTERIM_DIR, "h3_by_country.csv")
ALPHAS_JSON   = os.path.join(RESULTS_DIR, "lotka_exponents.json")
OUT_CSV       = os.path.join(RESULTS_DIR, "granularity_check.csv")

MIN_INST = 5
TOP_N    = 30


def spearman(pairs):
    n = len(pairs)
    if n < 2:
        return float("nan")
    a_vals = [x[0] for x in pairs]
    b_vals = [x[1] for x in pairs]

    def ranks(lst):
        sorted_idx = sorted(range(n), key=lambda i: lst[i])
        r = [0.0] * n
        for rank, idx in enumerate(sorted_idx, 1):
            r[idx] = float(rank)
        return r

    ra = ranks(a_vals)
    rb = ranks(b_vals)
    mean_ra = sum(ra) / n
    mean_rb = sum(rb) / n
    num = sum((ra[i] - mean_ra) * (rb[i] - mean_rb) for i in range(n))
    den = (sum((ra[i] - mean_ra) ** 2 for i in range(n)) *
           sum((rb[i] - mean_rb) ** 2 for i in range(n))) ** 0.5
    return num / den if den else float("nan")


def main():
    for path in (AUTHORS_CSV, INST_TYPES, COUNTRY_MAP, H3_ORIG_CSV, ALPHAS_JSON):
        if not os.path.exists(path):
            raise SystemExit(f"ERROR: missing {path}")

    with open(ALPHAS_JSON) as f:
        beta_2 = json.load(f)["beta_2"]
    inv_beta_2 = 1.0 / beta_2
    print(f"beta_2 = {beta_2:.4f}  (ε₃ = h₃ / N^{inv_beta_2:.4f})\n")

    con = duckdb.connect()
    con.execute("SET threads=8; SET enable_progress_bar=true;")

    # ------------------------------------------------------------------
    # 1. Build same-country institution → root mapping
    # ------------------------------------------------------------------
    print("Building institution → same-country root mapping...")
    con.execute(f"""
        CREATE TABLE inst_types AS
        SELECT id, lineage FROM read_parquet('{INST_TYPES}')
    """)
    con.execute(f"""
        CREATE TABLE country_map AS
        SELECT id, country_code FROM read_csv_auto('{COUNTRY_MAP}')
    """)

    # Institutions that are roots of their own lineage tree
    con.execute("""
        CREATE TABLE roots AS
        SELECT id AS root_id FROM inst_types WHERE len(lineage) = 1
    """)

    # For each institution, map to the same-country root if one exists,
    # otherwise keep the institution itself as its own root.
    # The correlated subquery is fine at ~136k rows.
    con.execute("""
        CREATE TABLE inst_root AS
        SELECT i.id AS institution_id,
               COALESCE(
                   -- same-country root: a root whose country matches the institution's country
                   (SELECT r.root_id
                    FROM roots r
                    WHERE array_contains(i.lineage, r.root_id)
                      AND (SELECT cm_r.country_code FROM country_map cm_r
                           WHERE cm_r.id = r.root_id LIMIT 1)
                          = (SELECT cm_i.country_code FROM country_map cm_i
                             WHERE cm_i.id = i.id LIMIT 1)
                    LIMIT 1),
                   i.id
               ) AS root_id
        FROM inst_types i
    """)

    n_merged = con.execute("""
        SELECT COUNT(*) FROM inst_root
        WHERE institution_id != root_id
          AND institution_id IN (SELECT institution_id FROM read_csv_auto('data/interim/h2_by_institution.csv'))
    """).fetchone()[0]
    print(f"  {n_merged:,} h₂ institutions rolled into a same-country parent\n")

    # ------------------------------------------------------------------
    # 2. Load authors and map to same-country root
    # ------------------------------------------------------------------
    print("Loading authors and mapping to parent systems...")
    con.execute(f"""
        CREATE TABLE authors AS
        SELECT author_id, h_index AS h1, institution_id
        FROM read_csv_auto('{AUTHORS_CSV}')
        WHERE institution_id IS NOT NULL
    """)

    # Restrict to institutions that appear in h2_by_institution.csv,
    # ensuring we match the original pipeline's scope exactly.
    con.execute("""
        CREATE TABLE h2_scope AS
        SELECT institution_id
        FROM read_csv_auto('data/interim/h2_by_institution.csv')
    """)

    con.execute("""
        CREATE TABLE authors_rolled AS
        SELECT a.h1,
               COALESCE(ir.root_id, a.institution_id) AS root_id
        FROM authors a
        JOIN h2_scope s USING (institution_id)
        LEFT JOIN inst_root ir ON ir.institution_id = a.institution_id
    """)

    n_authors = con.execute("SELECT COUNT(*) FROM authors_rolled").fetchone()[0]
    print(f"  {n_authors:,} authors in scope\n")

    # ------------------------------------------------------------------
    # 3. Compute h₂ per parent system from pooled h₁ distribution
    # ------------------------------------------------------------------
    print("Computing h₂ per parent system...")
    con.execute("""
        CREATE TABLE h2_rolled AS
        WITH ranked AS (
            SELECT root_id, h1,
                   ROW_NUMBER() OVER (
                       PARTITION BY root_id ORDER BY h1 DESC
                   ) AS rk
            FROM authors_rolled
        )
        SELECT root_id, MAX(rk) FILTER (WHERE h1 >= rk) AS h2
        FROM ranked
        GROUP BY root_id
        HAVING MAX(rk) FILTER (WHERE h1 >= rk) IS NOT NULL
    """)

    # ------------------------------------------------------------------
    # 4. Map parent systems to countries (use root's own country code)
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE h2_country AS
        SELECT h.root_id, h.h2, c.country_code
        FROM h2_rolled h
        JOIN country_map c ON c.id = h.root_id
    """)

    n_roots = con.execute("SELECT COUNT(*) FROM h2_country").fetchone()[0]
    print(f"  {n_roots:,} parent systems with h₂ > 0 and a country code\n")

    # ------------------------------------------------------------------
    # 5. Compute h₃ and institution count per country (rolled-up)
    # ------------------------------------------------------------------
    print("Computing h₃ per country (rolled up)...")
    con.execute("""
        CREATE TABLE h3_rolled AS
        WITH ranked AS (
            SELECT country_code, h2,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_code ORDER BY h2 DESC
                   ) AS rk
            FROM h2_country
        ),
        h3_cands AS (
            SELECT country_code, MAX(rk) FILTER (WHERE h2 >= rk) AS h3
            FROM ranked
            GROUP BY country_code
        ),
        counts AS (
            SELECT country_code, COUNT(*) AS inst_count_rolled
            FROM h2_country
            GROUP BY country_code
        )
        SELECT h.country_code, h.h3 AS h3_rolled, c.inst_count_rolled
        FROM h3_cands h JOIN counts c USING (country_code)
    """)

    # ------------------------------------------------------------------
    # 6. Load original h₃ and merge
    # ------------------------------------------------------------------
    print("Loading original h₃ results...")
    result = con.execute(f"""
        SELECT o.country_code,
               o.h3    AS h3_orig,
               r.h3_rolled,
               o.institution_count AS inst_count_orig,
               r.inst_count_rolled
        FROM read_csv_auto('{H3_ORIG_CSV}') o
        JOIN h3_rolled r USING (country_code)
        ORDER BY o.h3 DESC, o.country_code
    """).fetchall()

    # ------------------------------------------------------------------
    # 7. Compute ε₃ and ranks
    # ------------------------------------------------------------------
    def eps(h3, n):
        return h3 / (n ** inv_beta_2)

    rows = []
    for cc, h3_o, h3_r, ic_o, ic_r in result:
        if ic_o < MIN_INST or ic_r < MIN_INST:
            continue
        rows.append({
            "country_code":      cc,
            "h3_orig":           h3_o,
            "h3_rolled":         h3_r,
            "inst_count_orig":   ic_o,
            "inst_count_rolled": ic_r,
            "inst_delta":        ic_o - ic_r,
            "eps3_orig":         eps(h3_o, ic_o),
            "eps3_rolled":       eps(h3_r, ic_r),
        })

    rows_by_h3_orig = sorted(rows, key=lambda x: (-x["h3_orig"],  x["country_code"]))
    rows_by_h3_roll = sorted(rows, key=lambda x: (-x["h3_rolled"], x["country_code"]))
    rows_by_ep_orig = sorted(rows, key=lambda x: (-x["eps3_orig"], x["country_code"]))
    rows_by_ep_roll = sorted(rows, key=lambda x: (-x["eps3_rolled"], x["country_code"]))

    for i, r in enumerate(rows_by_h3_orig, 1):
        r["h3_rank_orig"]   = i
    for i, r in enumerate(rows_by_h3_roll, 1):
        r["h3_rank_rolled"] = i
    for i, r in enumerate(rows_by_ep_orig, 1):
        r["eps3_rank_orig"]  = i
    for i, r in enumerate(rows_by_ep_roll, 1):
        r["eps3_rank_rolled"] = i

    rows.sort(key=lambda x: x["h3_rank_orig"])

    # ------------------------------------------------------------------
    # 8. Write output
    # ------------------------------------------------------------------
    fieldnames = [
        "country_code", "h3_orig", "h3_rolled", "h3_rank_orig", "h3_rank_rolled",
        "inst_count_orig", "inst_count_rolled", "inst_delta",
        "eps3_orig", "eps3_rolled", "eps3_rank_orig", "eps3_rank_rolled",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["eps3_orig"]   = round(r["eps3_orig"],   4)
            r["eps3_rolled"] = round(r["eps3_rolled"], 4)
            w.writerow(r)
    print(f"\n{len(rows)} countries → {OUT_CSV}\n")

    # ------------------------------------------------------------------
    # 9. Summary statistics
    # ------------------------------------------------------------------
    rho_h3  = spearman([(r["h3_rank_orig"],  r["h3_rank_rolled"])  for r in rows])
    rho_eps = spearman([(r["eps3_rank_orig"], r["eps3_rank_rolled"]) for r in rows])

    total_orig   = sum(r["inst_count_orig"]   for r in rows)
    total_rolled = sum(r["inst_count_rolled"] for r in rows)

    print(f"Global institution count:  {total_orig:,} → {total_rolled:,}  "
          f"(−{total_orig - total_rolled:,} after same-country roll-up)\n")
    print(f"Spearman ρ  h₃ rank:  {rho_h3:.4f}")
    print(f"Spearman ρ  ε₃ rank:  {rho_eps:.4f}\n")

    def fmt_delta(a, b):
        d = b - a
        return f"{'+' if d > 0 else ''}{d}"

    big_h3 = sorted(rows, key=lambda x: abs(x["h3_rank_orig"] - x["h3_rank_rolled"]), reverse=True)
    big_ep = sorted(rows, key=lambda x: abs(x["eps3_rank_orig"] - x["eps3_rank_rolled"]), reverse=True)

    print("Largest h₃ rank shifts (top 10):")
    print(f"  {'CC':>4}  {'h₃↑':>4} {'h₃↓':>4}  {'Δrk':>5}  "
          f"{'N↑':>7} {'N↓':>7}  {'ΔN':>5}")
    print("  " + "-" * 52)
    for r in big_h3[:10]:
        print(f"  {r['country_code']:>4}  {r['h3_orig']:>4} {r['h3_rolled']:>4}  "
              f"{fmt_delta(r['h3_rank_orig'], r['h3_rank_rolled']):>5}  "
              f"{r['inst_count_orig']:>7,} {r['inst_count_rolled']:>7,}  "
              f"{r['inst_delta']:>5,}")

    print(f"\nLargest ε₃ rank shifts (top 10):")
    print(f"  {'CC':>4}  {'ε↑':>6} {'ε↓':>6}  {'Δrk':>5}  "
          f"{'N↑':>7} {'N↓':>7}  {'ΔN':>5}")
    print("  " + "-" * 52)
    for r in big_ep[:10]:
        print(f"  {r['country_code']:>4}  {r['eps3_orig']:>6.3f} {r['eps3_rolled']:>6.3f}  "
              f"{fmt_delta(r['eps3_rank_orig'], r['eps3_rank_rolled']):>5}  "
              f"{r['inst_count_orig']:>7,} {r['inst_count_rolled']:>7,}  "
              f"{r['inst_delta']:>5,}")

    print(f"\nTop {TOP_N} by original h₃ rank (with rolled-up comparison):")
    hdr = (f"  {'CC':>4}  {'h₃↑':>4} {'h₃↓':>4} {'Δrk':>5}  "
           f"{'ε₃↑':>6} {'ε₃↓':>6} {'Δεrk':>5}  "
           f"{'N↑':>6} {'N↓':>6} {'ΔN':>5}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows[:TOP_N]:
        print(
            f"  {r['country_code']:>4}  "
            f"{r['h3_orig']:>4} {r['h3_rolled']:>4} "
            f"{fmt_delta(r['h3_rank_orig'], r['h3_rank_rolled']):>5}  "
            f"{r['eps3_orig']:>6.3f} {r['eps3_rolled']:>6.3f} "
            f"{fmt_delta(r['eps3_rank_orig'], r['eps3_rank_rolled']):>5}  "
            f"{r['inst_count_orig']:>6,} {r['inst_count_rolled']:>6,} "
            f"{r['inst_delta']:>5,}"
        )


if __name__ == "__main__":
    main()
