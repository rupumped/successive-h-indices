#!/usr/bin/env python3
"""
Build a stress-test sample of authors for manual cross-validation of H2
against Google Scholar.

Rather than sampling randomly, this targets the places an OpenAlex-derived
h-index is most likely to be wrong AND most consequential if it is:

  1. Threshold authors  - sit exactly at an institution's H2 value, so a
     +/-1 h-index error there can change the institution's rank.
  2. Weak-coverage fields - top authors at a top institution in a field
     (humanities, social sciences) where OpenAlex topic classification is
     known to be thinner.
  3. Non-Anglophone institutions - Chinese/Arabic/Persian names, where
     author-name disambiguation errors are more common, plus institutions
     flagged for suspected affiliation-swapping (e.g. Saudi universities).
  4. Global top h-index - a sanity check at the very top of the
     distribution, where errors would be most visible.

Requires network access to the public OpenAlex API to resolve each
author_id to a display name and affiliation history.
"""

import csv
import json
import sys
import time
import urllib.request

import duckdb

DB_PATH = "openalex.duckdb"
OUT_CSV = "cross_validation_sample.csv"
MAILTO = "nicholas.s.selby@gmail.com"  # OpenAlex polite pool

# (bucket, institution_name, field_name_or_None, how_many_authors_at_threshold)
THRESHOLD_CONFIG = [
    ("Threshold @ top institution", "Harvard University", None, 2),
    ("Threshold @ top institution", "Johns Hopkins University", None, 1),
    ("Threshold @ top institution", "University of Oxford", None, 2),
    ("Weak-coverage field", "University of Oxford", "Arts and Humanities", 3),
    ("Weak-coverage field", "University of Michigan", "Social Sciences", 2),
]

# (bucket, institution_name, how_many_top_authors)
NON_ANGLOPHONE_CONFIG = [
    ("Non-Anglophone institution", "University of Science and Technology of China", 2),
    ("Non-Anglophone institution", "King Saud University", 1),
    ("Non-Anglophone institution", "King Abdulaziz University", 1),
    ("Non-Anglophone institution", "Sharif University of Technology", 1),
]

GLOBAL_TOP_N = 5


def compute_h2_threshold(con, institution_name, field_name):
    """Recompute the H2 value for (institution[, field]) directly from the
    authors table, deduping authors so multi-affiliation rows don't double
    count."""
    where = "institution_name = ?"
    params = [institution_name]
    if field_name is not None:
        where += " AND field_name = ?"
        params.append(field_name)
    row = con.execute(
        f"""
        WITH ranked AS (
            SELECT DISTINCT author_id, h_index
            FROM authors
            WHERE {where}
        ), r AS (
            SELECT h_index, ROW_NUMBER() OVER (ORDER BY h_index DESC) AS rnk
            FROM ranked
        )
        SELECT MAX(rnk) FROM r WHERE h_index >= rnk
        """,
        params,
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def authors_at_h_index(con, institution_name, field_name, h_index, limit):
    where = "institution_name = ? AND h_index = ?"
    params = [institution_name, h_index]
    if field_name is not None:
        where += " AND field_name = ?"
        params.append(field_name)
    return con.execute(
        f"SELECT DISTINCT author_id, h_index FROM authors WHERE {where} LIMIT {limit}",
        params,
    ).fetchall()


def top_authors_at_institution(con, institution_name, limit):
    return con.execute(
        """
        SELECT DISTINCT author_id, h_index
        FROM authors
        WHERE institution_name = ?
        ORDER BY h_index DESC
        LIMIT ?
        """,
        [institution_name, limit],
    ).fetchall()


def global_top_authors(con, limit):
    return con.execute(
        """
        SELECT DISTINCT author_id, h_index, institution_name
        FROM authors
        ORDER BY h_index DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()


def collect_candidates(con):
    """Returns a list of dicts: bucket, institution, field, author_id, h_index_openalex_local, reason."""
    candidates = []

    for bucket, institution, field, n in THRESHOLD_CONFIG:
        h2 = compute_h2_threshold(con, institution, field)
        if h2 is None:
            print(f"  [skip] no H2 found for {institution} / {field}", file=sys.stderr)
            continue
        rows = authors_at_h_index(con, institution, field, h2, n)
        for author_id, h_index in rows:
            candidates.append(
                {
                    "bucket": bucket,
                    "institution": institution,
                    "field": field or "(overall)",
                    "author_id": author_id,
                    "h_index_local": h_index,
                    "reason": f"sits exactly at the H2={h2} threshold",
                }
            )

    for bucket, institution, n in NON_ANGLOPHONE_CONFIG:
        rows = top_authors_at_institution(con, institution, n)
        for author_id, h_index in rows:
            candidates.append(
                {
                    "bucket": bucket,
                    "institution": institution,
                    "field": "(overall)",
                    "author_id": author_id,
                    "h_index_local": h_index,
                    "reason": "top h-index at this institution",
                }
            )

    for author_id, h_index, institution in global_top_authors(con, GLOBAL_TOP_N):
        candidates.append(
            {
                "bucket": "Global top h-index (sanity check)",
                "institution": institution,
                "field": "(overall)",
                "author_id": author_id,
                "h_index_local": h_index,
                "reason": "among the highest h-index authors in the dataset",
            }
        )

    return candidates


def fetch_author_details(author_id, retries=3):
    """Look up display name, ORCID and affiliation history from the public
    OpenAlex API for a single author_id (e.g. 'https://openalex.org/A123')."""
    short_id = author_id.rsplit("/", 1)[-1]
    url = f"https://api.openalex.org/authors/{short_id}?mailto={MAILTO}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.load(resp)
            affiliations = [
                a.get("institution", {}).get("display_name")
                for a in data.get("affiliations", [])[:3]
            ]
            return {
                "name": data.get("display_name"),
                "h_index_openalex": data.get("summary_stats", {}).get("h_index"),
                "works_count": data.get("works_count"),
                "orcid": data.get("orcid"),
                "affiliations": affiliations,
            }
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [error] {author_id}: {e}", file=sys.stderr)
                return {
                    "name": None,
                    "h_index_openalex": None,
                    "works_count": None,
                    "orcid": None,
                    "affiliations": [],
                }
            time.sleep(1.5 * (attempt + 1))


def print_markdown_table(rows):
    header = [
        "#",
        "Bucket",
        "Institution",
        "Field",
        "Name",
        "OpenAlex ID",
        "ORCID",
        "Why sampled",
        "Career affiliations (per OpenAlex)",
        "h-index (OpenAlex)",
    ]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for i, r in enumerate(rows, 1):
        affs = "; ".join(a for a in r["affiliations"] if a) or "-"
        print(
            "| "
            + " | ".join(
                str(x)
                for x in [
                    i,
                    r["bucket"],
                    r["institution"],
                    r["field"],
                    r["name"] or "(lookup failed)",
                    r["author_id"],
                    r["orcid"] or "-",
                    r["reason"],
                    affs,
                    r["h_index_openalex"],
                ]
            )
            + " |"
        )


def write_csv(rows, path):
    fieldnames = [
        "bucket",
        "institution",
        "field",
        "name",
        "author_id",
        "orcid",
        "reason",
        "affiliations",
        "h_index_openalex",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "bucket": r["bucket"],
                    "institution": r["institution"],
                    "field": r["field"],
                    "name": r["name"],
                    "h_index_openalex": r["h_index_openalex"],
                    "author_id": r["author_id"],
                    "orcid": r["orcid"],
                    "reason": r["reason"],
                    "affiliations": "; ".join(a for a in r["affiliations"] if a),
                }
            )


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("PRAGMA disable_progress_bar")

    print("Selecting candidates from local data...", file=sys.stderr)
    candidates = collect_candidates(con)

    print(f"Resolving {len(candidates)} authors via the OpenAlex API...", file=sys.stderr)
    for c in candidates:
        details = fetch_author_details(c["author_id"])
        c.update(details)
        time.sleep(0.15)  # be polite to the shared API

    print_markdown_table(candidates)
    write_csv(candidates, OUT_CSV)
    print(f"\nWrote {len(candidates)} rows to {OUT_CSV}", file=sys.stderr)


if __name__ == "__main__":
    main()
