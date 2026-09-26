# Primary-institution attribution: run plan for the new machine

Status as of 2026-09-26. The code is written and tested on synthetic cases and on single real files. None of the full-scale runs below have been done with the current code.

## Background

Reviewer round 2 (issues 1, 3 and 6 in `paper/reviews-round-2.md`) objected to crediting each author's whole career h-index to their *most recent* education affiliation. That rule let secondary affiliations win: community colleges listed on a handful of papers, and Saudi affiliations held for funding.

The new rule in `src/build.py` (`--attribution primary`, the default) works as follows:

- **Primary institution.** The education institution credited on the most of the author's own authorships in their last 5 publishing years. That means their last publication year and the four before it; years after 2026 are ignored as data errors.
- **Credit (option 3, `--rollup`, on by default).** An authorship credits every education institution listed on it. It also credits the education-type ancestors of any *non*-education institution listed, using OpenAlex `lineage`: JPL gives Caltech, and the Ragon Institute gives Harvard and MIT. Education institutions are never rolled up to their own parents, so a Berkeley paper doesn't also credit the University of California System.
- **Thresholds.** At least 2 credited papers, and at least 10% of the window's works that credit *any* education institution (option 2, `--share-of edu`, the default). Authors below either threshold are excluded.
- **Ties.** The institution seen most recently wins, then the one seen most often over the whole career, then the smallest ID.

Evidence behind these choices:

- **Affiliation order is unusable.** OpenAlex's `authorships[].affiliations[]` order matched Crossref/Europe PMC only about 49% of the time (`src/affiliation_order_check.py`, `results/affiliation_order_check.log`).
- **The community-college authors are artifacts.** The top authors assigned to the flagged colleges list them on 0–2.6% of their works (all their works, not just recent ones).
- **The first full run was too strict.** It used direct credit only and a share of *all* works. It assigned just 43.7% of the old 30.0M-author population and excluded 23% of authors with h ≥ 30. The losses were mostly researchers based at hospitals and institutes that OpenAlex doesn't type as `education` (Dana-Farber, Broad, Scripps, MD Anderson, JPL, LBNL). Options 2 and 3 are the response.
- **Option 3 is a small effect.** On one test file it raised the number of works crediting any university by about 0.5%. Most affiliated hospitals and institutes (Dana-Farber, Broad, MGH, Brigham) have no education parent in OpenAlex. Option 2 is expected to do most of the recovery.

## 1. Commit (old machine) and pull (new machine)

Files that belong to this change:

```
src/prefetch_works.py          new: works snapshot -> per-author counts
src/build.py                   step 2 + attribution flags + --memory-gb
src/affiliation_order_check.py new: evidence that affiliation order is unreliable
requirements.txt               + tqdm
README.md                      How to run step 1b/2, Data source paragraph
docs/primary-affiliation-plan.md
```

Other modified and untracked files in the working tree are unrelated to this change: the paper sources, `src/prefetch.py`, and the other `*_check.py` scripts. Commit them separately or together as you see fit.

## 2. Set up the new machine

```bash
git pull
pip install -r requirements.txt
aws s3 ls s3://openalex/data/parquet/works/ --no-sign-request   # AWS CLI must work
```

`data/` is gitignored. Copy these from the old machine:

| Copy | Size | Why |
|---|---|---|
| `data/authors_staging/` | 3.6 GB | The August authors snapshot the paper's population is built from. Re-running `prefetch.py` would pull today's live snapshot and change the population. |
| `data/interim/institution_country_map.csv` | 4 MB | Country lookup (or rerun `fetch_country_codes.py`) |
| `data/interim/citation_sample.csv` | 25 MB | α₀ fit (or rerun `prefetch_citations.py`) |
| `data/interim/*.bkup`, `data/interim/h3_by_field.bkup/` | ~4.5 GB | Old-rule results, for before/after comparison |
| `data/external/`, `data/ScimagoIR 2026 - Overall Rank.csv` | 1.4 MB | Choropleth and Scimago validation |

Don't copy these:

- `data/works_staging/`: it uses the old schema, and `prefetch_works.py` would delete and redo it anyway.
- `data/openalex.duckdb`: it's rebuilt.
- `data/api_cache/`: only the affiliation-order check uses it.

Disk: plan for about 40 GB free. That covers ~10 GB of works staging, ~10 GB of author buckets kept by step 2, ~5 GB for `openalex.duckdb`, and ~9 GB for the interim CSVs plus backups.

## 3. Works prefetch (option 3 needs a fresh one)

```bash
python3 src/prefetch_works.py --workers 4 --memory-gb 24
```

- **Sizing.** Allow roughly 1.5 GB of RAM per worker beyond `--memory-gb`. On the 7 GB machine, one worker at 4 GB was fine, but three workers at 3 GB each were killed for running out of memory. As a guide, one worker per 6–8 GB of RAM.
- **Time.** One worker took about 57 s per 890 MB file (roughly 12 h for all 707 GB). Several workers should shorten this until network bandwidth becomes the limit.
- **Institution types.** It first writes `data/interim/institution_types.parquet` (136K institutions).
- **Resuming.** It's resumable: completed files are skipped, and old-schema files are redone. Disable sleep or idle suspend on the machine; the first run died overnight when the old machine idled out.
- **Snapshot drift.** The works snapshot is live. If OpenAlex publishes a new release partway through, the file list changes between restarts. Check that the number of files in the "N/M files already done" line doesn't jump between runs.

## 4. Main build

```bash
cp data/interim/authors.csv data/interim/authors.csv.bkup   # only if not already copied over
python3 src/build.py --memory-gb 16
```

Step 2 partitions about 1.6B staging rows into 64 author buckets in `data/works_buckets/`, which are kept for later sensitivity runs, then aggregates each bucket. Its summary prints how many authors fail each threshold. Keep that output; the paper needs it.

## 5. Check exclusions before going downstream

Rerun the exclusion breakdown against the old population. The same query was used for the first-run numbers above:

```python
import duckdb
c = duckdb.connect("data/openalex.duckdb", read_only=True)
c.execute("""CREATE TEMP TABLE x AS
  SELECT p.author_id, p.h_index, p.institution_name AS old_name, q.institution_id AS new_inst,
         p.institution_id AS old_inst, q.passes,
         CASE WHEN q.author_id IS NULL THEN 'no works' WHEN q.institution_id IS NULL THEN 'no edu'
              WHEN q.n_inst < 2 THEN '<2 papers' WHEN NOT q.passes THEN '<10% share'
              ELSE 'assigned' END AS reason
  FROM read_csv('data/interim/authors.csv.bkup') p
  LEFT JOIN primary_institution q USING (author_id)""")
print(c.execute("SELECT reason, COUNT(*), COUNT(*) FILTER (WHERE h_index >= 30) FROM x GROUP BY 1").fetchall())
print(c.execute("""SELECT old_name, COUNT(*) n, round(100*AVG((reason <> 'assigned')::INT)) pct_excl
  FROM x WHERE h_index >= 30 GROUP BY 1 HAVING n >= 300 ORDER BY pct_excl DESC LIMIT 20""").fetchall())
```

What to look for, compared with the first run:

- **Excluded share of h ≥ 30.** The first run excluded 23%. The "<10% share" group, which was 6% of h ≥ 50, should mostly disappear. "No edu" and "<2 papers" will shrink only by what the hierarchy credit recovers.
- **Harvard (29%), Caltech (44%) and Berkeley (40%) excluded** in the first run. Caltech should improve through JPL. Harvard mostly won't, because Dana-Farber, MGH and Brigham have no education parent.
- **Top excluded authors by h.** Spot-check a few in the API. Genuine non-university researchers (Scripps, NIH, companies) are fine to exclude.
- **Community colleges** (Bellevue, Imperial Valley, City College of San Francisco, Frederick) should collapse to realistic author counts and h2.

If exclusions are still too heavy, the parameters to revisit are the constants at the top of `build.py`: `PRIMARY_WINDOW`, `PRIMARY_MIN_PAPERS` and `PRIMARY_MIN_SHARE`.

## 6. Sensitivity runs, then restore the default

Each build overwrites the `authors` and `h2_*` tables inside `data/openalex.duckdb`, and several downstream and check scripts read that database. So run the variants first and the default **last**:

```bash
python3 src/build.py --memory-gb 16 --no-rollup            # -> *_norollup.csv
python3 src/build.py --memory-gb 16 --share-of all         # -> *_shareall.csv
python3 src/build.py --memory-gb 16 --attribution recent   # -> *_recent.csv (old rule)
python3 src/build.py --memory-gb 16                        # default, last
```

Variants reuse the author buckets, so only the aggregation and step 3 rerun.

## 7. Downstream

Run README "How to run" steps 3–24 in order on the default outputs. Then compare against the `.bkup` files: top-20 institutions overall and by field, the h3 country ranking, and the efficiency tables. Give particular attention to Saudi Arabia (4th by efficiency under the old rule) and the flagged community colleges.

## 8. Paper and README

- **Methods** (`paper/sections/method.tex`): the attribution rule, why affiliation order isn't used, and the exclusion counts from step 2.
- **Sensitivity table:** default vs. `--no-rollup` vs. `--share-of all` vs. `--attribution recent`. This answers the reviewer's request to test other attribution methods.
- **Limitations:**
  - Faculty based in hospitals and institutes with no education parent in OpenAlex are under-credited, which affects Harvard in particular.
  - The hierarchy credit gives some labs to a *system* rather than a campus (LBNL goes to the University of California System, MD Anderson to the University of Texas System).
  - The authors snapshot (2026-08-11) and the works snapshot (whenever step 3 runs) come from different dates.
- `paper/response_to_reviewers_2.md`: the reviewer's issues 1, 3 and 6.
- README "Selected results": replace the numbers, including the Saudi Arabia efficiency caveat.

## Known limitations of the code

- `MAX_YEAR = 2026` in `build.py` is tied to the works snapshot year. Update it if the snapshot rolls into 2027.
- The works staging only records education institutions and their education ancestors. Anything more (for example crediting hospitals to universities through a hand-made mapping) needs another prefetch.
- `check_works_staging_complete()` lists S3, so `build.py` needs network access whenever step 2 recomputes. `--allow-incomplete-works` skips the check.
