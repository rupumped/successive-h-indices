# Successive H-Indices
![CMU ranks #1 in CS but 175th overall; Wageningen ranks #1 in Agricultural and Environmental Sciences but 172nd overall; and Shenyang Pharmaceutical University ranks #1 in Pharmacology but 535th overall](https://rupumped.github.io/blog-posts/h2-cover.png)
## Highlights
1. The overall institution-level ranking is, in substance, a ranking of medical school size: Medicine accounts for 44% of the global author pool and structurally dominates any university-wide aggregate. Harvard is the exception: it places #1 even after removing all five core biomedical fields. But the table below it reshuffles dramatically: Antwerp rises to 2nd (+12 places), Caltech to 3rd (+12), MIT to 6th (+19), USTC to 8th (+31), while Stanford barely moves (−2) and Cambridge falls to 10th (−7). CMU (175th overall), USTC (39th), and Wageningen (172nd) are world leaders in their fields but structurally can't reach the top of the aggregate because they lack large medical schools.
2. China's applied-science strength is real. In the current snapshot the US wins 22 of 26 Academic Olympics golds; China wins 5 (Chemical Engineering, Energy, Engineering, Materials Science outright, plus a tied gold in Chemistry). China holds zero medals in arts, humanities, social sciences, or business.
3. Brazil holds two of the world's six deepest dental-research benches. Universidade de São Paulo and UNICAMP give Brazil a concentration of dental talent you'd never find by looking at any general-purpose ranking.

**A note on reproducibility:** `s3://openalex/data/parquet/authors/` is a live, continuously-updated snapshot, not a versioned release. Every number below reflects our most recent pull; re-running this pipeline today will not reproduce them exactly, and several field-level leaders in earlier versions of this analysis may have already been overtaken.

## Introduction
In 2007, András Schubert published a paper titled "Successive h-indices." It begins:
> Hirsch's *excessively discussed* h-index generated a long row of interpretations, applications and derivatives within a surprisingly short period. Symptomatically, Hirsch's paper in the *Proceedings of the National Academy of Sciences of the United States of America* became the second highest cited paper of the issue in which it had been published. In this note, attention is called to an apparently so far overlooked option: h-indices themselves may form the basis of a successive series of h-indices.

> Given, e.g., the h-indices of the researchers of an institute (which indices will be denoted by h<sub>1</sub> in what follows), an index, h<sub>2</sub>, of the institute can be determined: the institute has an index h<sub>2</sub> if h<sub>2</sub> of its N researchers have an h<sub>1</sub>-index of at least h<sub>2</sub> each, and the other (N−h<sub>2</sub>) researchers have h<sub>1</sub>-indices lower than h<sub>2</sub> each. The succession can then be continued, e.g., for networks of institutions or countries or other higher levels of aggregation.

> Since no sufficient data for testing the concept on the researcher–institute–country hierarchy were available, another example was chosen.

Fifteen years later, OpenAlex launched a FOSS bibliographic catalogue complete with citation indexing, authors, fields, and institutions. We now have the dataset for which Schubert wished in 2007. Schubert implied that computing the h<sub>2</sub> of institutes would be more interesting than that of journals. This is that analysis.

## Goal
Compute successive h-indices up the researcher → institution → country hierarchy using [OpenAlex](https://openalex.org/).

- **H1** (the ordinary h-index): *n* papers by an author have at least *n* citations.
- **h<sub>2</sub>**: *n* authors at an institution (in a given field) have an H1 of at least *n*.
- **h<sub>3</sub>**: *n* institutions in a country have an h<sub>2</sub> of at least *n*.

h<sub>2</sub> is computed per (institution, field) pair and also aggregated across all fields. h<sub>3</sub> is computed per country.

## Data source
OpenAlex public snapshot on AWS S3 (`s3://openalex/data/parquet/authors/`, `us-east-1`). No credentials required. The snapshot is partitioned by `updated_date` into ~1,663 daily parquet files totalling ~53 GB.

Authors are filtered to those with:
- `h_index > 0`
- at least one affiliation with `institution.type = "education"`
- at least one OpenAlex topic with a non-null field classification

This yields **17.1 million authors** across **20,669 institutions** and OpenAlex's current list of 26 fields. Each author's `works_count` is carried through as well, purely to fit the Lotka exponent α<sub>1</sub> (see "Efficiency exponents" below).

Each author is assigned to a single institution: among their affiliations with `institution.type = "education"`, we pick the one with the latest publication year in that affiliation's `years[]` (OpenAlex's `affiliations` field lists an author's institutions together with the years they published while there). Ties are broken by the numerically smallest institution ID. We deliberately don't use `last_known_institutions` for this — despite the name, it's just the set of affiliations listed on an author's single most recent work, with no per-entry recency of its own, so it can't distinguish which of several co-affiliations is "most recent."

Each author is also assigned to a single field: OpenAlex tags each author with a set of topics, each carrying a `count` (roughly, the number of the author's works classified under that topic) and a parent field. We sum `count` within each field and assign the author to whichever field carries the largest total weight — their modal field by publication volume, not simply their single most granular topic.

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

# 1a. Optional: merge per-partition staging files into a single parquet for
#     faster I/O in step 2. Writes data/authors_filtered.parquet.
#     Skip this if disk space is tight; build.py reads staging files directly.
python3 src/consolidate.py

# 2. Build the per-author table and compute h<sub>2</sub> by (institution, field).
#    Writes data/interim/authors.csv, data/interim/h<sub>2</sub>_by_institution_field.csv,
#    and data/openalex.duckdb.
python3 src/build.py

# 3. Split h<sub>2</sub>_by_institution_field.csv into one file per field.
#    Writes to results/h<sub>2</sub>_by_field/<field_name>.csv.
python3 src/split_by_field.py

# 4. Compute institution-level h<sub>2</sub> (ignoring field).
#    Writes data/interim/h<sub>2</sub>_by_institution.csv.
python3 src/build_institution_h<sub>2</sub>.py

# 5. Download the institution id -> country_code lookup from the OpenAlex
#    institutions snapshot on S3, once. Writes
#    data/interim/institution_country_map.csv.
python3 src/fetch_country_codes.py

# 6. Compute h<sub>3</sub> per country, using the local country map from step 5.
#    Writes data/interim/h<sub>3</sub>_by_country.csv.
python3 src/build_country_h<sub>3</sub>.py

# 7. Split h<sub>3</sub>_by_country.csv into one file per field.
#    Writes to data/interim/h<sub>3</sub>_by_field/<field_name>.csv.
python3 src/build_country_h<sub>3</sub>_by_field.py

# 8. Optional: sample cited_by_count from the OpenAlex works snapshot to
#    enable a direct alpha_0 fit (step 9 falls back to an indirect estimate
#    if this is skipped). Writes data/interim/citation_sample.csv.
python3 src/prefetch_citations.py

# 9. Fit the Lotka exponents (alpha_0, alpha_1, alpha_2) that the efficiency
#    metrics below are normalized by. Writes results/lotka_exponents.json.
python3 src/estimate_alphas.py

# 10. Efficiency metrics, normalized by the fitted exponents from step 9.
#     Writes results/h<sub>2</sub>_efficiency.csv and results/h<sub>3</sub>_efficiency.csv.
python3 src/h<sub>2</sub>_efficiency.py
python3 src/h<sub>3</sub>_efficiency.py

# 11. Total author count per field.
#     Writes results/authors_by_field.csv.
python3 src/authors_by_field.py

# 12. Gini coefficient of h<sub>2</sub> within each field (inequality of research strength
#     across institutions). Writes results/field_gini.csv.
python3 src/field_gini.py

# 13. Breadth score: for each institution, count its top-10/50/100 field
#     placements. Writes results/breadth_score.csv.
python3 src/breadth_score.py

# 14. Re-rank institutions excluding the five core biomedical fields
#     (Medicine, Biochemistry/Genetics/Molecular Biology, Immunology and
#     Microbiology, Neuroscience, Health Professions).
#     Writes results/nonbiomedical_h<sub>2</sub>.csv.
python3 src/nonbiomedical_ranking.py

# 15. Specialization index: how much higher an institution ranks in its best
#     single field than it does in the overall list.
#     Writes results/specialization_index.csv.
python3 src/specialization_index.py

# 16. Academic Olympics: gold/silver/bronze medals per country per field
#     based on h<sub>3</sub>. Writes results/academic_olympics.png.
python3 src/academic_olympics.py

# 17. Country specialization index: overall h<sub>3</sub> rank minus best-field h<sub>3</sub> rank.
#     Writes results/country_specialization.csv.
python3 src/country_specialization.py

# 18. World choropleth of h<sub>3</sub> by country. Downloads the Natural Earth 50m
#     shapefile on first run. Writes results/h<sub>3</sub>_choropleth.png.
python3 src/plot_h<sub>3</sub>_choropleth.py

# 19. Scatter plot of h<sub>2</sub> vs author_count^(1/β₁) with linear trendline and R².
#     Requires step 9. Writes results/h<sub>2</sub>_vs_size.png.
python3 src/plot_h<sub>2</sub>_vs_size.py

# 20. Scatter plot of h<sub>3</sub> vs institution_count^(1/β₂) with linear trendline
#     and R². Requires step 9. Writes results/h<sub>3</sub>_vs_size.png.
python3 src/plot_h<sub>3</sub>_vs_size.py

# 21. Same scatter but using √institution_count (the √N heuristic, for
#     comparison with step 20). Writes results/h<sub>3</sub>_vs_size_sqrt.png.
python3 src/plot_h<sub>3</sub>_vs_size_sqrt.py

# 22. Histogram of works_count across authors — diagnostic for the
#     disambiguation-artifact cap used in step 9.
#     Writes results/works_count_histogram.png.
python3 src/plot_works_count_hist.py

# 23. Optional: build a stress-test sample of authors for manual cross-
#     validation against Google Scholar. Requires OpenAlex API access.
#     Writes results/cross_validation_sample.csv.
python3 src/cross_validation_sample.py
```

### Requirements

Install Python dependencies from the repo root:

```bash
pip install -r requirements.txt
```

The AWS CLI must also be installed and `aws s3 ls --no-sign-request` must work (no credentials needed): [AWS CLI documentation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

## Outputs

| File | Description |
|---|---|
| `data/authors_filtered.parquet` | Consolidated single parquet (optional; created by `consolidate.py`) |
| `data/interim/authors.csv` | 17.1M rows: author_id, h_index, works_count, institution_id, institution_name, field, field_name |
| `data/interim/h<sub>2</sub>_by_institution_field.csv` | 288,300 (institution, field) pairs with h<sub>2</sub> and author count |
| `results/h<sub>2</sub>_by_field/` | One CSV per field, sorted by h<sub>2</sub> descending |
| `data/interim/h<sub>2</sub>_by_institution.csv` | 20,669 institutions with institution-level h<sub>2</sub> |
| `data/interim/institution_country_map.csv` | institution_id → country_code lookup, downloaded once by `fetch_country_codes.py` |
| `data/interim/h<sub>3</sub>_by_country.csv` | h<sub>3</sub> index per country with institution count |
| `data/interim/h<sub>3</sub>_by_field/` | One CSV per field, sorted by h<sub>3</sub> descending |
| `results/lotka_exponents.json` | Fitted α<sub>1</sub>, α<sub>2</sub>, β<sub>1</sub>, β<sub>2</sub>, α<sub>0</sub>, and per-fit diagnostics |
| `results/h<sub>2</sub>_efficiency.csv` | Institutions ranked by h<sub>2</sub> / author_count^(1/β<sub>1</sub>) |
| `results/h<sub>3</sub>_efficiency.csv` | Countries ranked by h<sub>3</sub> / institution_count^(1/β<sub>2</sub>) |
| `results/authors_by_field.csv` | Author count per field |
| `results/field_gini.csv` | Gini coefficient of h<sub>2</sub> across institutions within each field |
| `results/breadth_score.csv` | Per-institution count of top-10/50/100 field placements |
| `results/nonbiomedical_h<sub>2</sub>.csv` | Institution h<sub>2</sub> recomputed excluding the five core biomedical fields |
| `results/specialization_index.csv` | Institution specialization index (overall rank minus best single-field rank) |
| `results/academic_olympics.png` | Medal table: gold/silver/bronze per country per field |
| `results/country_specialization.csv` | Country specialization index (overall h<sub>3</sub> rank minus best-field h<sub>3</sub> rank) |
| `results/h<sub>3</sub>_choropleth.png` | World choropleth of h<sub>3</sub> by country |
| `results/h<sub>2</sub>_vs_size.png` | Scatter plot of h<sub>2</sub> vs author_count^(1/β<sub>1</sub>) with trendline and R² |
| `results/h<sub>3</sub>_vs_size.png` | Scatter plot of h<sub>3</sub> vs institution_count^(1/β<sub>2</sub>) with trendline and R² |
| `results/h<sub>3</sub>_vs_size_sqrt.png` | Scatter plot of h<sub>3</sub> vs √institution_count (√N heuristic baseline) |
| `results/works_count_histogram.png` | works_count histogram, diagnostic for the disambiguation-artifact cap |
| `results/cross_validation_sample.csv` | Sample of authors for manual Google Scholar cross-validation |

## Efficiency exponents

Egghe (2008) models successive h-indices as a chain of Lotkaian (power-law) Information Production Processes: citations-per-article (exponent α<sub>0</sub>), articles-per-author (α<sub>1</sub>), authors-per-institution (α<sub>2</sub>), and so on. His eq. 11 gives h<sub>2</sub> = author_count^(1/(α<sub>0</sub>α<sub>1</sub>)) and his eq. 18 gives h<sub>3</sub> = institution_count^(1/(α<sub>0</sub>α<sub>1</sub>α<sub>2</sub>)).

`estimate_alphas.py` fits each exponent as the discrete-MLE power-law tail (Clauset, Shalizi & Newman 2009, via the `powerlaw` package, with x<sub>min</sub> chosen by KS minimization) of the corresponding empirical distribution:

| Exponent | Fit from | Value |
|---|---|---|
| α<sub>1</sub> | `works_count` across authors (excluding 46 authors with works_count > 10,000 — an author-disambiguation artifact, see the script's docstring) | 2.996 |
| α<sub>2</sub> | `author_count` across institutions | 1.994 |
| β<sub>1</sub> | `h1` (h_index) across authors | 2.963 |
| β<sub>2</sub> | `h<sub>2</sub>` across institutions | 2.998 |
| α<sub>0</sub> | `cited_by_count` across a 718,299-work sample from `prefetch_citations.py` | 2.742 |

Egghe's functional form is empirically well-supported: S^(1/β<sub>1</sub>) alone explains 91% of the variance in h<sub>2</sub> (R²=0.911, no-intercept regression across all institutions with ≥10 authors), and R^(1/β<sub>2</sub>) explains 92% of the variance in h<sub>3</sub> across countries. The compounding-exponent cross-check fails sharply, however: α<sub>0</sub>α<sub>1</sub>=2.742×2.996=8.21, against the directly-measured β<sub>1</sub>=2.963 (a 177% discrepancy), and β<sub>1</sub>×α<sub>2</sub>=2.963×1.994=5.909 against the directly-measured β<sub>2</sub>=2.998 (a 97% discrepancy). The model is empirically useful; the underlying theory needs a different reading.

## Selected results

### Top institutions overall

| Institution | h<sub>2</sub> | Authors |
|---|---|---|
| Harvard University | 137 | 110,979 |
| Stanford University | 107 | 65,197 |
| University of Cambridge | 105 | 52,307 |
| Cornell University | 104 | 70,718 |
| Johns Hopkins University | 103 | 80,028 |
| University of Oxford | 103 | 57,110 |
| University of Washington | 102 | 71,270 |
| University of North Carolina at Chapel Hill | 101 | 64,478 |
| University College London | 100 | 77,482 |
| University of California, San Francisco | 100 | 50,351 |

This broadly tracks the US News and World Report ranking, where Harvard also places 1st, Stanford 3rd, and Cambridge 5th. The overall ranking is, however, a considerably less interesting object than it first appears.

### Harvard wins the overall ranking, and leads 13 of 26 fields outright
Harvard leads 13 of the 26 fields outright, more than any other institution, including Medicine, Biochemistry/Genetics/Molecular Biology, and Economics/Econometrics/Finance. Harvard remains #1 even after you exclude the biomedical core (Medicine, Biochemistry/Genetics/Molecular Biology, Immunology and Microbiology, Neuroscience, Health Professions). But the table below it reshuffles substantially: Antwerp rises to 2nd (+12), Caltech to 3rd (+12), MIT to 6th (+19), USTC to 8th (+31), ETH Zurich to 9th (+27), while Stanford falls slightly (−2) and Cambridge falls to 10th (−7). Harvard's overall lead reflects genuine breadth, not just medical-school scale.

### The university-level ranking hides real specialist powerhouses
- Wageningen University (#172 overall, h<sub>2</sub>=71): #1 globally in both Agricultural & Biological Sciences and Environmental Science (field h<sub>2</sub>=56 in each). A specialized institution that never appears near the top of any broad ranking.
- Shenyang Pharmaceutical University (#535 overall, h<sub>2</sub>=53): #1 globally in Pharmacology, Toxicology & Pharmaceutics (field h<sub>2</sub>=24).
- Carnegie Mellon (#175 overall, h<sub>2</sub>=70): #1 in Computer Science (field h<sub>2</sub>=56). CMU is world-renowned for CS but lacks a large medical school, placing it outside the overall top 100.
- University of Science and Technology of China (USTC, #39 overall, h<sub>2</sub>=89): leads three fields simultaneously — Materials Science (h<sub>2</sub>=59), Engineering (h<sub>2</sub>=62), and Energy (h<sub>2</sub>=52). Its sister institution, the University of Chinese Academy of Sciences (#97 overall, h<sub>2</sub>=80), leads Chemical Engineering (h<sub>2</sub>=23).
- University of Antwerp (#14 overall, h<sub>2</sub>=98): #1 in Physics and Astronomy (field h<sub>2</sub>=96) is the counterexample that the rule holds both ways: a field leader that also ranks highly overall, because it is broadly excellent rather than narrowly specialized.
- Universidade de São Paulo (#235 overall, h<sub>2</sub>=66): #1 in Dentistry (field h<sub>2</sub>=34), with UNICAMP placing 6th globally in the same field. Brazil holds two of the world's six deepest dental-research benches.

### Decision Sciences is the weakest field by far
Stanford's #1 score is h<sub>2</sub>=22 on just 285 Stanford authors, out of only 139,954 authors in the field worldwide. Compare to Medicine's h<sub>2</sub>=119 built on 7.58 million authors. Decision Sciences is clearly a thin OpenAlex topic category, not a deep, well-populated discipline. h<sub>2</sub> isn't meaningfully comparable across fields, only within them, and Decision Sciences may be too sparse to be meaningful at all.

### The overall ranking is implicitly a biomedical ranking
Medicine alone accounts for 7.58 million of the dataset's 17.1 million authors (44%), and together with Biochemistry/Genetics/Molecular Biology, Immunology and Microbiology, Neuroscience, and Health Professions, the five core biomedical fields dwarf every other field's author pool. A university like USTC or CMU, elite in non-medical fields, will structurally never reach the top of the overall list no matter how good it is, simply because it lacks a large medical school. Harvard is the exception: it ranks #1 even with biomedical fields removed, confirming genuine breadth. For almost every other institution, the field-level breakdown matters more than the university-level number.

### Physics and Astronomy is the most unequal field; Decision Sciences and Veterinary the most distributed
Physics and Astronomy is the most concentrated field (Gini=0.605): University of Antwerp's field-leading h<sub>2</sub>=96 is 15.7× the field mean of 6.1. Biochemistry, Genetics and Molecular Biology is second (Gini=0.577), narrowly ahead of Neuroscience (0.574). Decision Sciences and Veterinary are the most evenly distributed (Gini≈0.42, essentially tied). Medicine's Gini (0.528) sits mid-table despite Harvard's field-leading h<sub>2</sub>=119, because Medicine has thousands of institutions with meaningful h<sub>2</sub> rather than one dominant outlier.

### UCLA has the greatest breadth
UCLA places in the global top 50 in 20 of 26 fields, more than any other institution, despite leading only 8 outright. Harvard places in 19 fields' global top 50 and leads 13 outright, the most of any institution. Oxford also has 19 top-50 placements; Toronto, Cornell, Michigan, UNC Chapel Hill, and Cambridge each have 17. At the other extreme, several high-ranked institutions achieve strong overall h<sub>2</sub> without ever leading a single field: UC San Diego (rank 17, h<sub>2</sub>=97), the University of Melbourne (rank 23, h<sub>2</sub>=95), and Boston University (rank 25, h<sub>2</sub>=94) all have zero top-10 field placements, achieving their overall strength through scale and consistency rather than fielding the single best group in any discipline.

### The most efficient universities have very few authors
h<sub>2</sub> scales as author_count^(1/β<sub>1</sub>), with β<sub>1</sub>=2.963 fit directly from the h<sub>1</sub> (h-index) distribution's Lotka tail (R²=0.911 among institutions with ≥10 authors). Among the 12,026 institutions with at least 100 authors, the most efficient are focused or specialized institutions: Bellevue University (ε<sub>2</sub>=6.27, h<sub>2</sub>=54, 590 authors), Augustana University (ε<sub>2</sub>=5.65), and Germany's Center for Behavioral Brain Sciences (ε<sub>2</sub>=5.50). Among the 1,317 institutions with at least 5,000 authors, the most efficient are Rockefeller University, the Institute of Cancer Research, and University of Antwerp. Zero universities from the top 50 overall appear in the top 50 when measured by efficiency.

### h<sub>3</sub>: Academic Olympics
| Country | h<sub>3</sub> | Institutions |
|---|---|---|
| US | 70 | 4,242 |
| CN | 55 | 1,078 |
| DE | 49 |   505 |
| GB | 47 |   548 |
| JP | 46 | 1,358 |
| IT | 45 |   229 |
| FR | 41 |   394 |
| ES | 39 |   156 |
| KR | 37 |   358 |
| AU | 36 |   120 |

A few things stand out:
- **US wins 22 of 26 golds:** dominant across every humanities, social science, biomedical, and prestige-science field. China wins 4 outright (Chemical Engineering, Energy, Engineering, Materials Science) and ties the US for gold in Chemistry. China's five total golds form a clean sweep of applied and materials science, with zero medals in arts, humanities, social sciences, or business, an unambiguously present-tense structural result rather than a catching-up story.
- **Great Britain gets 10 silvers and 9 bronzes, but zero golds:** consistent with world-class institutions that are nonetheless outgunned by US depth in every single field.
- **Italy (45) and Japan (46) nearly tie** despite Japan having roughly 6× the institutions (1,358 vs. 229). h<sub>3</sub> scales as institution_count^(1/β<sub>2</sub>) with β<sub>2</sub>=2.998 fit directly (R²=0.922). Italy's efficiency score is the highest of any country; Japan's is far lower despite nearly the same raw h<sub>3</sub>.
- **Australia (h<sub>3</sub>=36, only 120 institutions)** achieves the 2nd highest efficiency. Spain is 3rd. Germany, the UK, and France are the only countries that rank in the top 10 on both raw h<sub>3</sub> and efficiency, confirming that their research depth is genuine rather than a scale artifact.
- **Saudi Arabia (h<sub>3</sub>=25, only 52 institutions)** ranks 4th by efficiency, likely an artifact of high-h-index researchers listing Saudi affiliations as secondary appointments in exchange for grants rather than a genuine concentration of resident research talent.
- **The US falls to efficiency rank 34** despite its raw h<sub>3</sub> lead. With 4,242 qualifying institutions, the size denominator absorbs most of its advantage. China (rank 10 by efficiency) appears above the US on this metric.

## Future work
Ranking university departments would be a natural next step. The hierarchy would extend naturally to researcher → department → institution → country, with successive indices h<sub>1</sub> through h<sub>4</sub>. Departments are field-specialized by construction, so the step of inferring each author's modal field from topic weights may become unnecessary at the departmental level. OpenAlex does not currently provide departmental affiliation data; this is the single most valuable addition OpenAlex could make for scientometric work of this kind.