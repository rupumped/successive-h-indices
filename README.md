# Successive H-Indices
## Highlights
1. The US News and World Report ranking (closely aligned with H2 on overall ranking) is a biomedical ranking in disguise — so much so that even Harvard's own #1 spot doesn't survive excluding biomedical fields (it drops to #5, behind Cornell, Stanford, Berkeley, and UCLA). CMU (#80 overall), USTC (#270), and Wageningen (#137) are world leaders in their fields but structurally can't reach the top of the aggregate because they lack a large medical school. The overall number is measuring "how big is your medical school" more than it's measuring research excellence.
2. China's applied-science strength is real but several of its head-to-head races with the US are razor-thin. In the current snapshot the US wins 24 of 26 Academic Olympics golds to China's 2 (Energy, Materials Science), but three of those races are decided by a single institution's worth of H3 (Chemical Engineering: US 10 vs. China 9; Materials Science: China 25 vs. US 24), and this picture has already flipped substantially once — an earlier pull of this same pipeline had China at 5 golds. Read the exact medal count as a snapshot, not a verdict; the underlying pattern (zero Chinese medals in arts, humanities, social sciences, or business) is more stable than the count itself.
3. Brazil is *really* good at dentistry. This is the most genuinely counterintuitive single finding. A country that appears nowhere in elite research rankings has quietly built the university (Universidade de São Paulo) with the world's deepest bench of dental researchers.

**A note on reproducibility:** `s3://openalex/data/parquet/authors/` is a live, continuously-updated snapshot, not a versioned release. Every number below reflects our most recent pull; re-running this pipeline today will not reproduce them exactly, and several field-level leaders in earlier versions of this analysis (University of Antwerp in Physics and Astronomy, the University of Chinese Academy of Sciences in Chemical Engineering) have already been overtaken between pulls. See the paper's Conclusion for more on the size of this effect.

## Introduction
In 2007, András Schubert published a paper titled "Successive h-indices." It begins:
> Hirsch's *excessively discussed* h-index generated a long row of interpretations, applications and derivatives within a surprisingly short period. Symptomatically, Hirsch's paper in the *Proceedings of the National Academy of Sciences of the United States of America* became the second highest cited paper of the issue in which it had been published. In this note, attention is called to an apparently so far overlooked option: h-indices themselves may form the basis of a successive series of h-indices.

> Given, e.g., the h-indices of the researchers of an institute (which indices will be denoted by h<sub>1</sub> in what follows), an index, h<sub>2</sub>, of the institute can be determined: the institute has an index h<sub>2</sub> if h<sub>2</sub> of its N researchers have an h<sub>1</sub>-index of at least h<sub>2</sub> each, and the other (N−h<sub>2</sub>) researchers have h<sub>1</sub>-indices lower than h<sub>2</sub> each. The succession can then be continued, e.g., for networks of institutions or countries or other higher levels of aggregation.

> Since no sufficient data for testing the concept on the researcher–institute–country hierarchy were available, another example was chosen.

Fifteen years later, OpenAlex launched a FOSS bibliographic catalogue complete with citation indexing, authors, fields, and institutions. We now have the dataset for which Schubert wished in 2007. Schubert implied that computing the h<sub>2</sub> of institutes would be more interesting than that of journals. This is that analysis.

## Goal
Compute successive h-indices up the researcher → institution → country hierarchy using [OpenAlex](https://openalex.org/).

- **H1** (the ordinary h-index): *n* papers by an author have at least *n* citations.
- **H2**: *n* authors at an institution (in a given field) have an H1 of at least *n*.
- **H3**: *n* institutions in a country have an H2 of at least *n*.

H2 is computed per (institution, field) pair and also aggregated across all fields. H3 is computed per country.

## Data source
OpenAlex public snapshot on AWS S3 (`s3://openalex/data/parquet/authors/`, `us-east-1`). No credentials required. The snapshot is partitioned by `updated_date` into ~1,663 daily parquet files totalling ~53 GB.

Authors are filtered to those with:
- `h_index > 0`
- at least one affiliation with `institution.type = "education"`
- at least one OpenAlex topic with a non-null field classification

This yields **27.1 million authors** across **20,907 institutions** and OpenAlex's current list of 26 fields. Each author's `works_count` is carried through as well, purely to fit the Lotka exponent α<sub>1</sub> (see "Efficiency exponents" below).

Each author is assigned to a single institution: among their affiliations with `institution.type = "education"`, we pick the one with the latest publication year in that affiliation's `years[]` (OpenAlex's `affiliations` field lists an author's institutions together with the years they published while there). Ties are broken by the numerically smallest institution ID. We deliberately don't use `last_known_institutions` for this — despite the name, it's just the set of affiliations listed on an author's single most recent work, with no per-entry recency of its own, so it can't distinguish which of several co-affiliations is "most recent."

## Layout

```
src/           all Python scripts
data/          raw/intermediate pipeline artifacts (gitignored)
  parquet/, authors_staging/    downloaded OpenAlex parquet
  openalex.duckdb                working duckdb database
  interim/                       tables generated from data/ that are also
                                  read as inputs by other scripts
results/       terminal analysis outputs: final CSVs and plots (gitignored)
```

## How to run
Run the scripts in order (all from the repo root):

```bash
# 1. Download and pre-filter the OpenAlex authors snapshot from S3.
#    Writes one parquet file per partition to data/authors_staging/.
#    Resumable — safe to interrupt and re-run.
python3 src/prefetch.py

# 2. Build the per-author table and compute H2 by (institution, field).
#    Writes data/interim/authors.csv, data/interim/h2_by_institution_field.csv,
#    and data/openalex.duckdb.
python3 src/build.py

# 3. Split h2_by_institution_field.csv into one file per field.
#    Writes to results/h2_by_field/<field_name>.csv.
python3 src/split_by_field.py

# 4. Compute institution-level H2 (ignoring field).
#    Writes data/interim/h2_by_institution.csv.
python3 src/build_institution_h2.py

# 5. Download the institution id -> country_code lookup from the OpenAlex
#    institutions snapshot on S3, once. Writes
#    data/interim/institution_country_map.csv.
python3 src/fetch_country_codes.py

# 6. Compute H3 per country, using the local country map from step 5.
#    Writes data/interim/h3_by_country.csv.
python3 src/build_country_h3.py

# 7. Split h3_by_country.csv into one file per field.
#    Writes to data/interim/h3_by_field/<field_name>.csv.
python3 src/build_country_h3_by_field.py

# 8. Optional: sample cited_by_count from the OpenAlex works snapshot to
#    enable a direct alpha_0 fit (step 9 falls back to an indirect estimate
#    if this is skipped). Writes data/interim/citation_sample.csv.
python3 src/prefetch_citations.py

# 9. Fit the Lotka exponents (alpha_0, alpha_1, alpha_2) that the efficiency
#    metrics below are normalized by. Writes results/lotka_exponents.json.
python3 src/estimate_alphas.py

# 10. Efficiency metrics, normalized by the fitted exponents from step 9.
python3 src/h2_efficiency.py
python3 src/h3_efficiency.py
```

### Requirements

```
duckdb
boto3      # only needed indirectly; prefetch.py uses the AWS CLI (aws s3 ls)
numpy
powerlaw   # discrete power-law MLE fitting, used by estimate_alphas.py
```

The AWS CLI must be installed and `aws s3 ls --no-sign-request` must work (no credentials needed).

## Outputs

| File | Description |
|---|---|
| `data/interim/authors.csv` | 27.1M rows: author_id, h_index, works_count, institution_id, institution_name, field, field_name |
| `data/interim/h2_by_institution_field.csv` | 328,500 (institution, field) pairs with H2 and author count |
| `results/h2_by_field/` | One CSV per field, sorted by H2 descending |
| `data/interim/h2_by_institution.csv` | 20,907 institutions with institution-level H2 |
| `data/interim/institution_country_map.csv` | institution_id → country_code lookup, downloaded once by `fetch_country_codes.py` |
| `data/interim/h3_by_country.csv` | H3 index per country with institution count |
| `data/interim/h3_by_field/` | One CSV per field, sorted by H3 descending |
| `results/lotka_exponents.json` | Fitted α<sub>1</sub>, α<sub>2</sub>, β<sub>1</sub>=α<sub>0</sub>α<sub>1</sub>, β<sub>2</sub>=α<sub>0</sub>α<sub>1</sub>α<sub>2</sub>, derived α<sub>0</sub>, and per-fit diagnostics |
| `results/h2_efficiency.csv` | Institutions ranked by H2 / author_count^(1/β<sub>1</sub>) |
| `results/h3_efficiency.csv` | Countries ranked by H3 / institution_count^(1/β<sub>2</sub>) |

## Efficiency exponents

Egghe (2008) models successive h-indices as a chain of Lotkaian (power-law) Information Production Processes: citations-per-article (exponent α<sub>0</sub>), articles-per-author (α<sub>1</sub>), authors-per-institution (α<sub>2</sub>), and so on. His eq. 11 gives h<sub>2</sub> = author_count^(1/(α<sub>0</sub>α<sub>1</sub>)) and his eq. 18 gives h<sub>3</sub> = institution_count^(1/(α<sub>0</sub>α<sub>1</sub>α<sub>2</sub>)).

`estimate_alphas.py` fits each exponent as the discrete-MLE power-law tail (Clauset, Shalizi & Newman 2009, via the `powerlaw` package, with x<sub>min</sub> chosen by KS minimization) of the corresponding empirical distribution:

| Exponent | Fit from | Value |
|---|---|---|
| α<sub>1</sub> | `works_count` across authors (excluding 46 authors with works_count > 10,000 — an author-disambiguation artifact, see the script's docstring) | 2.996 |
| α<sub>2</sub> | `author_count` across institutions | 2.021 |
| β<sub>1</sub>=α<sub>0</sub>α<sub>1</sub> | `h1` (h_index) across authors | 1.833 |
| β<sub>2</sub>=α<sub>0</sub>α<sub>1</sub>α<sub>2</sub> | `h2` across institutions | 2.917 |
| α<sub>0</sub> | `cited_by_count` across a 718,299-work sample from `prefetch_citations.py` | 2.742 |

Taken globally, these four exponents are inconsistent with Egghe's own model: β<sub>1</sub>/α<sub>1</sub> = 0.612 and β<sub>2</sub>/(α<sub>1</sub>α<sub>2</sub>) = 0.482 both imply α<sub>0</sub> < 1, impossible under his eq. 4. Refitting within a single field resolves most of this at the author level — implied α<sub>0</sub> rises to 0.890 within Medicine and 0.981 within Physics and Astronomy, essentially consistent with the required boundary once cross-field heterogeneity is controlled for — but the analogous β<sub>2</sub> ≈ β<sub>1</sub>·α<sub>2</sub> check does not improve within a field (off by 21% globally, 42% within Medicine, 45% within Physics and Astronomy), and the h<sub>2</sub>-across-institutions distribution is consistently better described by an exponential than a power law at every level tested. We read this as evidence that Egghe's compounding-exponent model holds at the author level once field heterogeneity is accounted for, but breaks down specifically at the institution-aggregation step. See the paper's Section "Testing the compounding-exponent model" for the full derivation.

## Selected results

### Top institutions overall

| Institution | H2 | Authors |
|---|---|---|
| Harvard University | 71 | 92,274 |
| University of California, Los Angeles | 64 | 57,912 |
| Stanford University | 63 | 55,761 |
| University of California, San Francisco | 63 | 43,867 |
| University of Washington | 63 | 62,319 |

Harvard's 1st place still matches the US News list, but the rest of the ordering has drifted further from it since an earlier pull of this pipeline: Stanford (3rd in US News) still places highly, but Cambridge (5th in US News) is now 26th in our ranking ($\mathrm{H2}=55$), outside our own top 10 entirely.

Schubert and I now rank my alma mater, Georgia Tech, 96th, whereas US News ranks it 94th — much closer agreement than an earlier pull of this pipeline showed (132nd vs. 94th).

Field-specific results are more interesting.

### Harvard wins the overall ranking, but only leads 5 of 26 fields outright
Harvard tops Biochemistry/Genetics/Molecular Biology, Immunology and Microbiology, Health Professions, Economics/Econometrics/Finance, and Medicine. Unlike an earlier pull of this pipeline, Harvard does **not** remain #1 once you exclude the biomedical core (Medicine, Biochemistry/Genetics/Molecular Biology, Immunology and Microbiology, Neuroscience, Health Professions) — it drops to 5th, behind Cornell, Stanford, Berkeley, and UCLA. That's arguably a cleaner version of this section's point than a surviving #1 would have been: even Harvard's overall lead depends partly on medical-school scale.

### The university-level ranking hides real specialist powerhouses
- Wageningen University, not a famous "elite" name in the US News sense, is #1 globally in Agricultural & Biological Sciences (H2=40 field-specific). It's ranked 137th in the overall list (H2=46) because it's a specialized institution rather than a broad research university.
- University of Bologna: 153rd overall, 1st in Chemistry. A university outside any US News-style "Top 100" has the single deepest bench of high-impact chemistry researchers on Earth by this measure.
- Tohoku University: 103rd overall, 1st in Materials Science.
- University of Washington is the opposite case: #5 overall *and* #1 in Environmental Science. A broad powerhouse that also happens to be the best in a specific, non-biomedical field.
- Carnegie Mellon: 80th overall, #1 in Computer Science. CMU is famous for CS but is not a broad biomedical/everything powerhouse, so it sits outside the top 50 overall, yet it has the single deepest bench of high-impact CS researchers by this metric.

Two of these leads are thin enough to be worth flagging: USTC's Energy lead (270th overall) is by a single institution over Jiangsu University, and this whole picture has shifted meaningfully since an earlier pull of this pipeline — University of Antwerp no longer leads Physics and Astronomy (Caltech and Cornell now tie there), and the University of Chinese Academy of Sciences no longer leads Chemical Engineering (Universidad de Zaragoza now does). Field leadership at these margins moves between snapshots.

### Decision Sciences is the weakest field by far.
The University of Southern California's #1 score is h2=17 on just 219 USC authors, out of only 131,012 authors in the field worldwide. Compare to Medicine's h2=63 with 6.8M authors. Decision Sciences is clearly a thin OpenAlex topic category, not a deep, well-populated discipline. H2 isn't meaningfully comparable across fields, only within them, and Decision Sciences may be too sparse to be meaningful at all.

### Universidade de São Paulo leads Dentistry
Brazil appears to have an outsized concentration of dental research talent (São Paulo: 231st overall, 1st in Dentistry, H2=27), which is not something you'd intuit from any general-purpose ranking. A second Brazilian institution, UNICAMP, places in Dentistry's global top 15 (H2=21) but no longer top 6 as an earlier pull of this pipeline showed.

### The overall ranking is implicitly a biomedical ranking
Because medical fields have by far the largest, most cited author pools (Medicine's h2=63 dwarfs every other field), they dominate any university-wide aggregate — strongly enough that even Harvard's own #1 position doesn't survive excluding them (see above). A university like USTC or CMU, elite in non-medical fields, will structurally never reach the top of the overall list no matter how good they are, simply because they don't have a large medical school. The field-level breakdown matters more than the university-level number.

### Biochemistry is the most unequal field; Decision Sciences and Veterinary the most distributed
Biochemistry, Genetics and Molecular Biology is now the most unequal field (Gini=0.534), narrowly ahead of Neuroscience and Physics and Astronomy. Harvard's field-leading H2=50 there is 9.5× the field mean of 5.29. Decision Science and Veterinary are (in either order) the most distributed (Gini≈0.39, essentially tied). Medicine's Gini (0.484) sits mid-table despite Harvard's field-leading H2=63 there too, because Medicine has thousands of institutions with meaningful H2 rather than one dominant outlier.

### Minnesota and Wisconsin–Madison now have the greatest breadth
Minnesota and Wisconsin–Madison tie for the most top-50 field placements (20 of 26 each), edging out Harvard's 19, though each leads only 4 fields outright — almost all of their breadth comes from being solidly good everywhere rather than dominant anywhere. Harvard still leads the most fields outright (5 of 26).

### The most efficient universities have very few authors
H2 scales as author_count^(1/β₁), with β₁=1.833 fit directly from the h1 (h-index) distribution's Lotka tail rather than assumed (see "Efficiency exponents" above) — noticeably below the √N (i.e. exponent-2) heuristic an earlier version of this analysis used, R²=0.809 against the institutions with ≥10 authors. Parkway School District — a K-12 district, not a research institution, which is itself a caution about this metric at low author counts — has the greatest H2 per this normalization of any institution (H2=19 on 142 authors). Zero universities from the top 100 overall were in the top 100 when measured by efficiency.

### H3: Academic Olympics
| Country | H3 | Institutions |
|---|---|---|
| US | 49 | 4,239 |
| DE | 37 |   505 |
| GB | 37 |   547 |
| CN | 35 | 1,078 |
| IT | 34 |   228 |
| JP | 34 | 1,356 |
| ES | 31 |   156 |
| FR | 30 |   394 |
| CA | 29 |   304 |
| AU | 28 |   120 |
| KR | 28 |   358 |

A few things stand out:
- **US wins 24 of 26 golds:** dominant across every humanities, social science, biomedical, and prestige-science field. China holds the remaining 2 (Energy, Materials Science). This is a substantially different count from an earlier pull of this pipeline (US 22, China 5), and three of the flipped/close races are decided by a single institution's worth of H3 — Chemical Engineering (US 10 vs. China 9) and Materials Science (China 25 vs. US 24) are both photo finishes; only Chemistry (US 23 vs. China 20, no longer a tie) and Engineering (US 30 vs. China 28) moved by more than one point.
- **China's 2 golds are both applied/materials science** (Energy, Materials Science), with zero medals in arts, humanities, social sciences, or business — the qualitative pattern survives even though the medal count dropped.
- **Great Britain gets 14 silvers and 10 bronzes, but zero golds:** consistent with the UK having world-class institutions but being outgunned by US depth everywhere.
- **Germany and the UK tie for 2nd** (37 each) despite the UK having 42 more institutions (547 vs 505).
- **Italy and Japan tie for 4th** (34 each), even though Italy gets there with a fraction of the institutions (228 vs 1,356). H3 now scales as institution_count^(1/β₂) with β₂=2.917 fit directly (R²=0.937, replacing an earlier √N/log₂N heuristic) — and because that grows faster than log₂N for large countries, the US's efficiency rank falls all the way to 84th (efficiency 2.80) despite leading every country on raw H3. Spain (5.49), Australia (5.42), and Italy (5.29) are now the most efficient countries by this measure.
- **Australia and South Korea tie for 9th** (28 each) despite South Korea having exactly 3× the institutions (358 vs 120) — a starker version of the Italy/Japan pattern.
- **Saudi Arabia (H3=20, only 52 institutions)** still ranks surprisingly high for its size (5th by efficiency), likely an artifact of high-h-index researchers listing Saudi affiliations as secondary appointments in exchange for grants.

## Future work
Ranking university departments would be a natural next step. You'd need department-level affiliation data, which OpenAlex doesn't currently provide, but could be approximated with a few thousand dollars of Search API calls.