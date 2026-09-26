#!/usr/bin/env python3
"""
Validate the efficiency metric epsilon_2 against Scimago Institutions
Rankings (SIR) 2026, "Overall Rank" export -- a genuinely independent
external ranking (Scopus-based, not OpenAlex-based), addressing the
reviewer's objection that the existing Leiden Ranking comparison shares
OpenAlex source infrastructure with this paper.

Caveats up front, because they materially limit what this comparison can
claim:
  - The SIR "Global Rank" is a composite of Research (50%), Innovation
    (30%), and Societal (20%) sub-scores, not a citation-normalized
    quality measure like MNCS. It is a different construct than what the
    Leiden comparison uses, not a stricter replication of it.
  - The downloaded file has no ROR ID or OpenAlex ID -- institutions are
    matched by normalized name (+ optional country), which is materially
    less reliable than the ID-based join leiden_validation.py performs.
    Match rate and a sample of unmatched/ambiguous names are reported so
    the join quality itself can be assessed.
  - SIR covers many non-university entities (ministries, academies,
    hospitals, companies); Sector is carried through so these can be
    filtered or reported separately.

Workflow
--------
  1. Load data/'ScimagoIR 2026 - Overall Rank.csv' (semicolon-delimited).
  2. Normalize institution names on both sides; join on normalized name
     (falling back to name+country if the plain name is ambiguous).
  3. Join to results/h2_efficiency.csv (h2_rank, efficiency_rank; the same
     >=100-author institution set the paper's efficiency table uses).
  4. Report Spearman rho(h2_rank, SIR rank) and rho(efficiency_rank, SIR
     rank), plus match-rate diagnostics.

Outputs
-------
  results/scimago_validation.csv  -- matched institutions with both ranks
  results/scimago_validation.log  -- verbose run log incl. match diagnostics

Usage
-----
  python3 src/scimago_validation.py
"""

import csv
import os
import re
import time

import duckdb
from scipy import stats

ROOT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCIMAGO_CSV = os.path.join(ROOT_DIR, "data", "ScimagoIR 2026 - Overall Rank.csv")
H2_EFF_CSV = os.path.join(ROOT_DIR, "results", "h2_efficiency.csv")
OUT_CSV    = os.path.join(ROOT_DIR, "results", "scimago_validation.csv")
LOG_PATH   = os.path.join(ROOT_DIR, "results", "scimago_validation.log")

STOPWORDS = {"the", "of", "and", "at", "de", "la", "le", "du", "for"}

_log_file = None


def log(msg):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def normalize_name(name):
    name = name.replace("*", "")
    name = name.lower()
    name = re.sub(r"[’'`]", "", name)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    tokens = [t for t in name.split() if t and t not in STOPWORDS]
    return " ".join(tokens)


def main():
    global _log_file
    with open(LOG_PATH, "w") as _log_file:
        t0 = time.time()

        log(f"Loading Scimago export: {SCIMAGO_CSV}")
        sir_rows = []
        with open(SCIMAGO_CSV, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                sir_rows.append({
                    "sir_rank": int(row["Global Rank"]),
                    "institution": row["Institution"].strip(),
                    "country": row["Country"].strip(),
                    "sector": row["Sector"].strip(),
                    "norm_name": normalize_name(row["Institution"]),
                })
        log(f"  {len(sir_rows):,} SIR institutions loaded")
        by_sector = {}
        for r in sir_rows:
            by_sector[r["sector"]] = by_sector.get(r["sector"], 0) + 1
        log(f"  Sector breakdown: {dict(sorted(by_sector.items(), key=lambda kv: -kv[1]))}\n")

        # Flag normalized names that are ambiguous within SIR itself (same
        # normalized name mapping to >1 SIR row) so they can be excluded from
        # the name-only join rather than silently mismatched.
        name_counts = {}
        for r in sir_rows:
            name_counts[r["norm_name"]] = name_counts.get(r["norm_name"], 0) + 1
        ambiguous_names = {n for n, c in name_counts.items() if c > 1}
        log(f"  {len(ambiguous_names):,} normalized SIR names are ambiguous (collide with "
            f"another SIR institution) and are excluded from the join\n")

        con = duckdb.connect()
        con.execute("SET threads=4; SET memory_limit='4GB';")
        con.execute("""
            CREATE TABLE sir (
                sir_rank INTEGER, institution VARCHAR, country VARCHAR,
                sector VARCHAR, norm_name VARCHAR
            )
        """)
        con.executemany(
            "INSERT INTO sir VALUES (?, ?, ?, ?, ?)",
            [(r["sir_rank"], r["institution"], r["country"], r["sector"], r["norm_name"])
             for r in sir_rows],
        )

        log(f"Loading paper's efficiency table: {H2_EFF_CSV}")
        con.execute(f"""
            CREATE TABLE h2eff AS
            SELECT *, regexp_replace(lower(institution_name), '[^a-z0-9 ]', ' ', 'g') AS raw_norm
            FROM read_csv_auto('{H2_EFF_CSV}')
        """)
        n_h2 = con.execute("SELECT COUNT(*) FROM h2eff").fetchone()[0]
        log(f"  {n_h2:,} institutions ({os.path.basename(H2_EFF_CSV)})\n")

        # Re-normalize OpenAlex names in Python (same stopword logic as SIR) via UDF-free approach:
        rows = con.execute("SELECT institution_id, institution_name FROM h2eff").fetchall()
        con.execute("CREATE TABLE _norm_map (institution_id VARCHAR, norm_name VARCHAR)")
        con.executemany("INSERT INTO _norm_map VALUES (?, ?)",
                         [(iid, normalize_name(name)) for iid, name in rows])
        con.execute("""
            CREATE TABLE h2eff_norm AS
            SELECT h.*, n.norm_name
            FROM h2eff h JOIN _norm_map n USING (institution_id)
        """)

        con.execute("CREATE TABLE _ambiguous (norm_name VARCHAR)")
        con.executemany("INSERT INTO _ambiguous VALUES (?)", [(n,) for n in ambiguous_names])

        log("Joining on normalized institution name (excluding SIR-side ambiguous names)...")
        con.execute("""
            CREATE TABLE matched AS
            SELECT s.sir_rank, s.institution AS sir_institution, s.country, s.sector,
                   h.institution_id, h.institution_name,
                   h.h2, h.h2_rank, h.efficiency, h.efficiency_rank
            FROM sir s
            JOIN h2eff_norm h ON s.norm_name = h.norm_name
            WHERE s.norm_name NOT IN (SELECT norm_name FROM _ambiguous)
        """)
        n_matched = con.execute("SELECT COUNT(*) FROM matched").fetchone()[0]
        n_dupe = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT sir_rank FROM matched GROUP BY sir_rank HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        log(f"  {n_matched:,} matched rows ({n_matched / len(sir_rows):.1%} of SIR institutions, "
            f"{n_matched / n_h2:.1%} of the paper's {n_h2:,}-institution efficiency table)")
        log(f"  {n_dupe:,} SIR institutions matched to >1 OpenAlex institution_name "
            f"(kept; these inflate n slightly and are visible in the output CSV)\n")

        h2_rho, h2_p = stats.spearmanr(
            *zip(*con.execute("SELECT h2_rank, sir_rank FROM matched").fetchall())
        )
        eff_rho, eff_p = stats.spearmanr(
            *zip(*con.execute("SELECT efficiency_rank, sir_rank FROM matched").fetchall())
        )
        log(f"Spearman rho(raw h2_rank, SIR Global Rank)         = {h2_rho:.4f}  (p={h2_p:.2e}, n={n_matched:,})")
        log(f"Spearman rho(efficiency_rank, SIR Global Rank)     = {eff_rho:.4f}  (p={eff_p:.2e}, n={n_matched:,})")
        log("(Both ranks use the convention 1 = best, so positive rho means agreement.)\n")

        log("Sample of unmatched top-200 SIR institutions (name-join failures / coverage gaps):")
        unmatched = con.execute("""
            SELECT s.sir_rank, s.institution, s.country
            FROM sir s
            WHERE s.sir_rank <= 200
              AND s.norm_name NOT IN (SELECT norm_name FROM _ambiguous)
              AND NOT EXISTS (SELECT 1 FROM h2eff_norm h WHERE h.norm_name = s.norm_name)
            ORDER BY s.sir_rank
            LIMIT 25
        """).fetchall()
        for rank, name, country in unmatched:
            log(f"  SIR#{rank:<5} {name} ({country})")
        log("")

        con.execute(f"""
            COPY (SELECT * FROM matched ORDER BY sir_rank)
            TO '{OUT_CSV}' (FORMAT CSV, HEADER TRUE)
        """)
        log(f"Wrote {OUT_CSV}")
        log(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
