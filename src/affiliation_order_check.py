#!/usr/bin/env python3
"""
Does the order of an author's affiliations on a paper separate their home
institution from secondary (demographic / funding) affiliations? Tests whether
"first-listed affiliation" is a usable definition of an author's primary
institution before building an attribution rule on it.

For samples of authors that build.py assigned to (a) the four flagged
community colleges, (b) the two large Saudi universities, and (c) Harvard as
a control, pulls from the OpenAlex API every work (up to MAX_WORKS per author)
on which the author lists the assigned institution, and records where that
institution falls in the author's per-paper affiliation list
(authorships[].affiliations[], deduplicated to distinct institutions in list
order).

Order fidelity: OpenAlex does not document that affiliations[] preserves the
order printed on the paper, so for a sample of multi-affiliation authorships
with DOIs the Crossref record (publisher-deposited affiliation order) is
pulled and the assigned institution's first/not-first status is compared.

Outputs
-------
results/affiliation_order_check.csv  — one row per (author, work) authorship
results/affiliation_order_check.log  — summaries by group and per author

Usage
-----
  python3 src/affiliation_order_check.py
"""

import hashlib
import json
import os
import random
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from statistics import median

import duckdb
from tqdm import tqdm

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHORS_CSV = os.path.join(ROOT_DIR, "data", "interim", "authors.csv")
CACHE_DIR = os.path.join(ROOT_DIR, "data", "api_cache")
OUT_CSV = os.path.join(ROOT_DIR, "results", "affiliation_order_check.csv")
LOG_PATH = os.path.join(ROOT_DIR, "results", "affiliation_order_check.log")

GROUPS = {
    "community_college": {
        "Bellevue University": "https://openalex.org/I58064216",
        "Imperial Valley College": "https://openalex.org/I2802000487",
        "City College of San Francisco": "https://openalex.org/I158404207",
        "Frederick Community College": "https://openalex.org/I138066346",
    },
    "saudi": {
        "King Abdulaziz University": "https://openalex.org/I185163786",
        "King Saud University": "https://openalex.org/I28022161",
    },
    "control": {
        "Harvard University": "https://openalex.org/I136199984",
    },
}
TOP_N = {"community_college": 25, "saudi": 30, "control": 30}  # per institution, by h_index
MAX_WORKS = 200          # works per author (one API page)
CROSSREF_SAMPLE = 400    # multi-affiliation authorships checked against Crossref

# Named case: Luque (El País, 2023) reportedly listed King Saud University
# as his primary affiliation under a paid arrangement.
NAMED_CASES = [("https://openalex.org/A5078421218", "https://openalex.org/I28022161", "Rafael Luque / KSU")]

_log_file = None


def log(msg=""):
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()


def get_json(url):
    """GET with on-disk cache and backoff on 429/5xx."""
    path = os.path.join(CACHE_DIR, hashlib.sha1(url.encode()).hexdigest() + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "successive-h-indices/affiliation_order_check"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            with open(path, "w") as f:
                json.dump(data, f)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 ** attempt)
    return None


def sample_authors(con):
    rows = []
    for group, insts in GROUPS.items():
        for name, iid in insts.items():
            for aid, h, wc in con.execute(f"""
                SELECT DISTINCT author_id, h_index, works_count
                FROM read_csv_auto('{AUTHORS_CSV}')
                WHERE institution_id = '{iid}'
                ORDER BY h_index DESC, author_id
                LIMIT {TOP_N[group]}
            """).fetchall():
                rows.append(dict(group=group, inst_name=name, inst_id=iid,
                                 author_id=aid, h_index=h, works_count=wc))
    for aid, iid, label in NAMED_CASES:
        rows.append(dict(group="named", inst_name=label, inst_id=iid,
                         author_id=aid, h_index=None, works_count=None))
    return rows


def short(oa_id):
    return oa_id.rsplit("/", 1)[-1]


def fetch_works(a):
    filt = f"author.id:{short(a['author_id'])},institutions.id:{short(a['inst_id'])}"
    select = "id,doi,publication_year,authorships"
    url = (f"https://api.openalex.org/works?filter={filt}&per_page={MAX_WORKS}"
           f"&select={select}&sort=publication_year:desc")
    data = get_json(url)
    if data is None:
        return a, None, []
    return a, data["meta"]["count"], data["results"]


def classify(a, work):
    """Locate the assigned institution in this author's ordered affiliations."""
    au = next((x for x in work["authorships"] if x["author"]["id"] == a["author_id"]), None)
    if au is None:
        return None
    # Rank by affiliation *string* order: one raw string (e.g. "MGH, Harvard
    # Medical School") can match several institution_ids whose order within
    # the string's id list is not the printed order. Identical strings
    # (modulo parser artifacts like a trailing "#TAB#") are collapsed, and
    # strings matching no institution are skipped.
    strings = []   # distinct matched affiliation strings, in list order
    for aff in au.get("affiliations") or []:
        key = re.sub(r"#TAB#|\s+", " ", aff.get("raw_affiliation_string") or "").strip().lower()
        ids = aff.get("institution_ids") or []
        if ids and key not in [k for k, _ in strings]:
            strings.append((key, ids))
    n = len(strings)
    hits = [i for i, (_, ids) in enumerate(strings) if a["inst_id"] in ids]
    if not hits:
        status = "not_in_affiliations"   # only matched via institutions[]
        rank = None
    else:
        rank = hits[0] + 1
        status = "sole" if n == 1 else ("first" if rank == 1 else "not_first")
    return dict(
        group=a["group"], inst_name=a["inst_name"], author_id=a["author_id"],
        h_index=a["h_index"], work_id=work["id"], doi=work.get("doi"),
        year=work.get("publication_year"),
        author_index=work["authorships"].index(au),
        raw_author_name=au.get("raw_author_name"),
        n_affiliation_strings=n, rank=rank, status=status,
        raw_affiliations=[x.get("raw_affiliation_string") for x in au.get("affiliations") or []],
        target_raw=next((x.get("raw_affiliation_string") for x in au.get("affiliations") or []
                         if a["inst_id"] in (x.get("institution_ids") or [])), None),
    )


def norm_tokens(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z]{3,}", s))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def crossref_check(r):
    """Compare first/not-first status of the target affiliation against Crossref."""
    doi = r["doi"].replace("https://doi.org/", "")
    data = get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    if not data:
        return dict(outcome="no_crossref_record")
    authors = data["message"].get("author") or []
    i = r["author_index"]
    if i >= len(authors):
        return dict(outcome="author_not_matched")
    fam = norm_tokens(authors[i].get("family", ""))
    if not fam or not fam & norm_tokens(r["raw_author_name"]):
        return dict(outcome="author_not_matched")
    cr_affs = [x.get("name", "") for x in authors[i].get("affiliation") or []]
    if not cr_affs:
        return dict(outcome="no_crossref_affiliations")
    if len(cr_affs) == 1 and len(r["raw_affiliations"]) > 1:
        # Some publishers deposit all affiliations as one concatenated string.
        return dict(outcome="crossref_single_string")
    tgt = norm_tokens(r["target_raw"])
    scores = [jaccard(tgt, norm_tokens(c)) for c in cr_affs]
    best = max(range(len(scores)), key=scores.__getitem__)
    if scores[best] < 0.5:
        return dict(outcome="target_not_found_in_crossref")
    oa_first = r["status"] == "first"
    cr_first = best == 0
    return dict(outcome="agree" if oa_first == cr_first else "disagree",
                oa_first=oa_first, cr_first=cr_first)


def pmap(fn, items, desc):
    """Thread-pooled map with a tqdm bar (terminal only; not written to the log)."""
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(tqdm(ex.map(fn, items), total=len(items), desc=desc))


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "   n/a"


def summarize(rows, label):
    c = {k: sum(r["status"] == k for r in rows) for k in ("sole", "first", "not_first", "not_in_affiliations")}
    multi = c["first"] + c["not_first"]
    log(f"  {label:<34} authorships={len(rows):>6}  sole={pct(c['sole'], len(rows))}  "
        f"multi={pct(multi, len(rows))}  | of multi: first={pct(c['first'], multi)} "
        f"not_first={pct(c['not_first'], multi)}  | unmatched={c['not_in_affiliations']}")


def main():
    global _log_file
    os.makedirs(CACHE_DIR, exist_ok=True)
    random.seed(0)
    with open(LOG_PATH, "w") as _log_file:
        t0 = time.time()
        con = duckdb.connect()
        con.execute("SET enable_progress_bar=false;")
        authors = sample_authors(con)
        log(f"Sampled {len(authors)} authors; fetching up to {MAX_WORKS} works each "
            f"that list the assigned institution...")

        fetched = pmap(fetch_works, authors, "OpenAlex")

        rows, per_author = [], []
        for a, total, works in fetched:
            rs = [r for r in (classify(a, w) for w in works) if r]
            rows.extend(rs)
            per_author.append((a, total, rs))
        log(f"  {len(rows):,} authorships from {len(per_author)} authors ({time.time()-t0:.0f}s)")

        # --- Authorship-level position of the assigned institution ---
        log("\n=== Position of the assigned institution on the author's own papers ===")
        log("  (sole = only matched affiliation string on that authorship; first/not_first = rank of the\n"
            "   first string matching the assigned institution among >1 distinct matched strings)")
        for group in list(GROUPS) + ["named"]:
            g = [r for r in rows if r["group"] == group]
            summarize(g, f"[{group}]")
            for name in sorted({r["inst_name"] for r in g}):
                summarize([r for r in g if r["inst_name"] == name], "  " + name)

        # --- Per-author view: is the assigned institution a real home or a side listing? ---
        log("\n=== Per author: share of works listing the assigned institution, and position ===")
        log(f"  {'group':<18}{'institution':<30}{'author':<13}{'h':>4}{'works':>7}{'w/inst':>8}"
            f"{'share':>7}{'multi':>7}{'1st|multi':>10}")
        for a, total, rs in per_author:
            multi = [r for r in rs if r["status"] in ("first", "not_first")]
            first = sum(r["status"] == "first" for r in multi)
            wc = a["works_count"]
            log(f"  {a['group']:<18}{a['inst_name'][:29]:<30}{short(a['author_id']):<13}"
                f"{a['h_index'] if a['h_index'] is not None else '-':>4}{wc if wc else '-':>7}"
                f"{total if total is not None else '-':>8}"
                f"{pct(total, wc) if wc and total is not None else '    -':>7}"
                f"{len(multi):>7}{pct(first, len(multi)):>10}")

        for group in GROUPS:
            shares = [s for s in (
                sum(r["status"] == "first" for r in rs) / m
                for a, _, rs in per_author if a["group"] == group
                for m in [sum(r["status"] in ("first", "not_first") for r in rs)] if m >= 5
            )]
            if shares:
                log(f"  [{group}] authors with >=5 multi-institution works: {len(shares)}; "
                    f"median share listing assigned inst first = {100*median(shares):.0f}%; "
                    f"share of authors where it is first on a majority = "
                    f"{pct(sum(s > 0.5 for s in shares), len(shares))}")

        # --- Crossref order-fidelity check ---
        cand = [r for r in rows if r["status"] in ("first", "not_first") and r["doi"]]
        sample = random.sample(cand, min(CROSSREF_SAMPLE, len(cand)))
        log(f"\n=== Order fidelity vs. Crossref ({len(sample)} multi-institution authorships sampled) ===")
        checks = pmap(crossref_check, sample, "Crossref")
        outcomes = {}
        for c in checks:
            outcomes[c["outcome"]] = outcomes.get(c["outcome"], 0) + 1
        for k, v in sorted(outcomes.items(), key=lambda kv: -kv[1]):
            log(f"  {k:<32}{v:>5}")
        comp = [c for c in checks if c["outcome"] in ("agree", "disagree")]
        if comp:
            agree = sum(c["outcome"] == "agree" for c in comp)
            log(f"  Agreement on first/not-first where comparable: {agree}/{len(comp)} ({pct(agree, len(comp)).strip()})")
            for lab, want in (("OpenAlex first", True), ("OpenAlex not-first", False)):
                sub = [c for c in comp if c["oa_first"] == want]
                ok = sum(c["cr_first"] == want for c in sub)
                log(f"    {lab:<20} -> Crossref agrees {ok}/{len(sub)}")
        for r, c in zip(sample, checks):
            r["crossref"] = c["outcome"]

        con.execute("CREATE TABLE out AS SELECT * FROM read_json_auto(?)", [
            _dump_rows(rows)])
        con.execute(f"COPY out TO '{OUT_CSV}' (HEADER, DELIMITER ',')")
        log(f"\nWrote {OUT_CSV}")
        log(f"Total runtime: {time.time()-t0:.0f}s")


def _dump_rows(rows):
    path = os.path.join(CACHE_DIR, "_rows.json")
    with open(path, "w") as f:
        json.dump([{**r, "raw_affiliations": " | ".join(x or "" for x in r["raw_affiliations"]),
                    "crossref": r.get("crossref")} for r in rows], f)
    return path


if __name__ == "__main__":
    main()
