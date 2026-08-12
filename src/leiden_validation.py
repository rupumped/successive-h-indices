#!/usr/bin/env python3
"""
Validate efficiency metric ε₂ against CWTS Leiden Ranking Open Edition (2024).

Workflow:
  1. Stream-parse the Leiden 2024 Results ODS to extract MNCS for each
     university under "All sciences", period "2019–2022", full counting.
  2. Batch-query the OpenAlex API to get the OpenAlex institution ID for
     each ROR ID in the Leiden data.
  3. Join with h₂ / ε₂ data from DuckDB; compute institution author count S.
  4. Report:
       • Spearman ρ(raw h₂ rank, Leiden MNCS rank)   [h₂ vs quality]
       • Spearman ρ(ε₂ rank, Leiden MNCS rank)         [efficiency vs quality]
  5. Write results/leiden_validation.csv and results/leiden_validation.log.

Usage
-----
  conda run -n base python3 src/leiden_validation.py

Prerequisites
-------------
  data/leiden_results_2024.ods  — Zenodo 13868018 (CC0)
  data/openalex.duckdb          — local DuckDB with authors / h2 tables
"""

import json
import os
import time
import urllib.request
import xml.sax
import xml.sax.handler

from scipy import stats

ROOT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH      = os.path.join(ROOT_DIR, "data", "openalex.duckdb")
RESULTS_FILE = os.path.join(ROOT_DIR, "data", "leiden_results_2024.ods")
OUT_CSV      = os.path.join(ROOT_DIR, "results", "leiden_validation.csv")
LOG_PATH     = os.path.join(ROOT_DIR, "results", "leiden_validation.log")
ROR_MAP_JSON = os.path.join(ROOT_DIR, "data", "ror_to_openalex.json")

TARGET_FIELD  = "All sciences"
TARGET_PERIOD = "2019–2022"   # "2019–2022" (en-dash)
TARGET_FRAC   = "0"               # full counting

OPENALEX_API  = "https://api.openalex.org/institutions"
BATCH_SIZE    = 50
SLEEP_BETWEEN = 0.12   # ~8 req/s, within unauthenticated 10 req/s limit

_log_file = None


def log(msg):
    print(msg, flush=True)
    if _log_file:
        _log_file.write(msg + "\n")
        _log_file.flush()


# ── 1. Stream-parse ODS ──────────────────────────────────────────────────────

class LeidenResultHandler(xml.sax.handler.ContentHandler):
    """SAX handler: extract ROR ID and MNCS for matching rows."""

    TARGET_COLS = {0: "university", 1: "ror_id", 2: "country",
                   3: "field", 4: "period", 5: "frac_counting", 29: "mncs"}

    def __init__(self):
        self.in_table = False
        self.current_row = []
        self.in_cell = False
        self.cell_text = ""
        self.repeat_cols = 1
        self.row_count = 0
        self.records = []  # list of dicts

    def startElement(self, name, attrs):
        if name == "table:table":
            self.in_table = attrs.get("table:name", "") == "Results"
        elif self.in_table and name == "table:table-row":
            self.current_row = []
        elif self.in_table and name in ("table:table-cell",
                                        "table:covered-table-cell"):
            self.in_cell = True
            self.cell_text = ""
            try:
                self.repeat_cols = int(
                    attrs.get("table:number-columns-repeated", "1"))
            except ValueError:
                self.repeat_cols = 1

    def characters(self, content):
        if self.in_cell:
            self.cell_text += content

    def endElement(self, name):
        if name in ("table:table-cell",
                    "table:covered-table-cell") and self.in_table:
            for _ in range(min(self.repeat_cols, 300)):
                self.current_row.append(self.cell_text)
            self.in_cell = False
        elif name == "table:table-row" and self.in_table:
            self.row_count += 1
            if self.row_count > 1:   # skip header row
                row = self.current_row
                if (len(row) > 29
                        and row[3] == TARGET_FIELD
                        and row[4] == TARGET_PERIOD
                        and row[5] == TARGET_FRAC):
                    self.records.append({
                        "university":  row[0],
                        "ror_id":      row[1],
                        "country":     row[2],
                        "mncs":        row[29],
                    })
            self.current_row = []


def load_leiden_mncs():
    log("Streaming Leiden Results ODS …")
    handler = LeidenResultHandler()
    parser = xml.sax.make_parser()
    parser.setContentHandler(handler)
    with open(RESULTS_FILE, "rb") as raw:
        import zipfile, io
        with zipfile.ZipFile(raw) as zf:
            with zf.open("content.xml") as xml_file:
                parser.parse(xml_file)
    log(f"  Extracted {len(handler.records):,} rows "
        f"({handler.row_count - 1:,} total rows scanned).")
    return handler.records


# ── 2. ROR → OpenAlex institution ID ─────────────────────────────────────────

def fetch_ror_batch(ror_ids):
    filter_str = "|".join(ror_ids)
    url = (f"{OPENALEX_API}"
           f"?filter=ror:{filter_str}"
           f"&select=id,ror&per_page={BATCH_SIZE}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent":
                 "leiden-validation/1.0 (mailto:nicholas.s.selby@gmail.com)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    result = {}
    for item in data.get("results", []):
        oa_id = item.get("id", "")
        ror   = item.get("ror", "")
        if oa_id and ror:
            bare_ror = ror.rstrip("/").split("/")[-1]
            result[bare_ror] = oa_id
    return result


def build_ror_map(ror_ids):
    if os.path.exists(ROR_MAP_JSON):
        with open(ROR_MAP_JSON) as f:
            cached = json.load(f)
        log(f"Loaded {len(cached):,} cached ROR→OA mappings.")
    else:
        cached = {}

    missing = [r for r in ror_ids if r not in cached]
    log(f"{len(missing):,} ROR IDs need API lookup.")

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i: i + BATCH_SIZE]
        try:
            batch_result = fetch_ror_batch(batch)
            cached.update(batch_result)
        except Exception as e:
            log(f"  Warning: batch {i // BATCH_SIZE} failed: {e}")
        time.sleep(SLEEP_BETWEEN)
        if (i // BATCH_SIZE) % 10 == 0:
            log(f"  {i + len(batch)}/{len(missing)} …")

    with open(ROR_MAP_JSON, "w") as f:
        json.dump(cached, f)
    log(f"ROR→OA map: {len(cached):,} entries saved.")
    return cached


# ── 3. Load precomputed h₂ / ε₂ data ────────────────────────────────────────

EFF_CSV = os.path.join(ROOT_DIR, "results", "h2_efficiency.csv")
LOTKA_JSON = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")


def load_h2_efficiency(openalex_ids):
    """
    Return a dict {openalex_id: {"h2": int, "author_count": int, "eps2": float}}
    from the precomputed h2_efficiency.csv (uses the paper's actual β₁).
    """
    import csv
    with open(LOTKA_JSON) as f:
        lotka = json.load(f)
    beta1 = lotka["beta_1"]

    result = {}
    with open(EFF_CSV) as f:
        for row in csv.DictReader(f):
            oid = row["institution_id"]
            if oid in openalex_ids:
                result[oid] = {
                    "h2":           int(row["h2"]),
                    "author_count": int(row["author_count"]),
                    "eps2":         float(row["efficiency"]),
                }
    return result, beta1


# ── 4. Main ───────────────────────────────────────────────────────────────────

def main():
    global _log_file
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

    with open(LOG_PATH, "w") as lf:
        _log_file = lf
        log("=== Leiden Ranking Validation ===\n")

        # Step 1 — parse ODS
        records = load_leiden_mncs()

        # Step 2 — ROR → OpenAlex ID
        ror_ids = [r["ror_id"] for r in records if r["ror_id"]]
        log(f"\nTotal Leiden universities (all-sciences 2019-22, full counting): {len(records):,}")
        ror_map = build_ror_map(ror_ids)

        for rec in records:
            rec["openalex_id"] = ror_map.get(rec["ror_id"])

        matched = [r for r in records if r["openalex_id"] and r["mncs"]]
        log(f"Universities matched to OpenAlex IDs: {len(matched):,} of {len(records):,}")

        # Step 3 — load h₂ / ε₂
        oa_ids = set(r["openalex_id"] for r in matched)
        h2_data, beta1 = load_h2_efficiency(oa_ids)
        log(f"β₁ used for ε₂: {beta1:.4f}")

        # Build joined dataset
        joined = []
        for rec in matched:
            oid = rec["openalex_id"]
            if oid not in h2_data:
                continue
            try:
                mncs = float(rec["mncs"])
            except (ValueError, TypeError):
                continue
            hd = h2_data[oid]
            joined.append({
                "university":     rec["university"],
                "ror_id":         rec["ror_id"],
                "country":        rec["country"],
                "openalex_id":    oid,
                "mncs":           mncs,
                "h2":             hd["h2"],
                "author_count":   hd["author_count"],
                "eps2":           hd["eps2"],
            })

        log(f"\nJoined dataset size: {len(joined):,} universities")

        # Step 4 — Spearman correlations
        mncs_vals = [r["mncs"]  for r in joined]
        h2_vals   = [r["h2"]    for r in joined]
        eps2_vals = [r["eps2"]  for r in joined if r["eps2"] is not None]
        mncs_for_eps = [r["mncs"] for r in joined if r["eps2"] is not None]

        rho_h2,   p_h2   = stats.spearmanr(mncs_vals, h2_vals)
        rho_eps2, p_eps2 = stats.spearmanr(mncs_for_eps, eps2_vals)

        log(f"\n{'='*55}")
        log(f"Spearman ρ(MNCS, raw h₂):          {rho_h2:+.4f}  (p={p_h2:.2e})")
        log(f"Spearman ρ(MNCS, ε₂):              {rho_eps2:+.4f}  (p={p_eps2:.2e})")
        log(f"{'='*55}")
        log(f"\nInterpretation:")
        log(f"  ε₂ {'better' if abs(rho_eps2) > abs(rho_h2) else 'worse'} aligns "
            f"with MNCS than raw h₂ "
            f"(Δρ = {rho_eps2 - rho_h2:+.4f}).")

        # Write CSV
        import csv
        with open(OUT_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "university", "ror_id", "country", "openalex_id",
                "mncs", "h2", "author_count", "eps2"])
            writer.writeheader()
            writer.writerows(joined)
        log(f"\nWrote {OUT_CSV}")

        # Summary row for response_to_reviewers
        log("\n--- Summary for paper ---")
        log(f"N institutions compared: {len(joined)}")
        log(f"ρ(h₂, MNCS) = {rho_h2:.3f}; ρ(ε₂, MNCS) = {rho_eps2:.3f}")


if __name__ == "__main__":
    main()
