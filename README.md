# Successive H-Indices
## Highlights
1. The US News and World Report ranking (closely aligned with H2 on overall ranking) is a biomedical ranking in disguise. Harvard ranks #1 not because it's the best university in the world at everything, but because it has a 56,000-author medical school. CMU (#175), USTC (#39), and Wageningen (#172) are world leaders in their fields but structurally can't reach the top of the aggregate because they lack that medical tail. The overall number is measuring "how big is your medical school" more than it's measuring research excellence.
2. China has already won STEM, not "catching up." Five gold medals (one shared with the US), all in applied science and engineering fields. Zero medals in arts, humanities, social sciences, or business. This is a present-tense fact buried under Western prestige rankings that weight the fields where the US still leads.
3. Brazil is *really* good at dentistry. This is the most genuinely counterintuitive single finding. A country that appears nowhere in elite research rankings has quietly built the university with the world's deepest bench of dental researchers.

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

This yields **17.1 million authors** across **20,669 institutions** and OpenAlex's current list of 26 fields.

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

# 5. Compute H3 per country. Fetches country codes from the OpenAlex
#    institutions snapshot on S3 (no local download needed).
#    Writes data/interim/h3_by_country.csv.
python3 src/build_country_h3.py

# 6. Split h3_by_country.csv into one file per field.
#    Writes to data/interim/h3_by_field/<field_name>.csv.
python3 src/build_country_h3_by_field.py
```

### Requirements

```
duckdb
boto3   # only needed indirectly; prefetch.py uses the AWS CLI (aws s3 ls)
```

The AWS CLI must be installed and `aws s3 ls --no-sign-request` must work (no credentials needed).

## Outputs

| File | Description |
|---|---|
| `data/interim/authors.csv` | 17.1M rows: author_id, h_index, institution_id, institution_name, field, field_name |
| `data/interim/h2_by_institution_field.csv` | 288,300 (institution, field) pairs with H2 and author count |
| `results/h2_by_field/` | One CSV per field, sorted by H2 descending |
| `data/interim/h2_by_institution.csv` | 20,669 institutions with institution-level H2 |
| `data/interim/h3_by_country.csv` | H3 index per country with institution count |
| `data/interim/h3_by_field/` | One CSV per field, sorted by H3 descending |

## Selected results

### Top institutions overall

| Institution | H2 | Authors |
|---|---|---|
| Harvard University | 137 | 110,979 |
| Stanford University | 107 | 65,197 |
| University of Cambridge | 105 | 52,307 |
| Cornell University | 104 | 70,718 |
| Johns Hopkins University | 103 | 80,028 |

The overall ranking aligns with the US News list, where Harvard ranks 1st, Stanford 3rd, and Cambridge 5th. The only thing close to a substantive disagrement between their list and that of Schubert and me is that they rank Johns Hopkins 17th instead of 5th, and we rank MIT 25th instead of 2nd.

Schubert and I rank my alma mater, Georgia Tech, 132nd, whereas US News ranks it 94th.

Field-specific results are more interesting.

### Harvard wins the overall ranking, but only dominates some fields
Harvard tops Biochemistry, Health Professions, Immunology, Mathematics, Medicine, Neuroscience, Business, Economics, Psychology, and Social Sciences. But it misses the top 100 for Chemical Engineering, Veterinary, Energy, and Agricultural Sciences. That said, even if you exclude the biomedical core (Medicine, Biochemistry, Genetics and Molecular Biology, Immunology and Microbiology, Neuroscience, and Health Professions), Harvard remains #1. It is genuinely excellent.

### The university-level ranking hides real specialist powerhouses
- Wageningen University, not a famous "elite" name in the US News sense, is #1 globally in both Agricultural & Biological Sciences and Environmental Science. It's ranked 172nd in the overall list because it's a specialized institution rather than a broad research university. The university-level H2 obscures genuine excellence that the field-level H2 reveals.
- Shenyang Pharmaceutical University: 535th overall, 1st in Pharmacology. A university you'd never see in a US News-style "Top 100" has the single deepest bench of high-impact pharmacology researchers on Earth by this measure.
- University of Antwerp is the opposite case: #14 overall and #1 in Physics. A broad powerhouse that also happens to be the best in a specific, non-biomedical field.
- Carnegie Mellon: 175th overall, #1 in Computer Science. CMU is famous for CS but is not a broad biomedical/everything powerhouse, so it sits outside the top 100 overall, yet it has the single deepest bench of high-impact CS researchers by this metric. This is the metric correctly capturing reputation that everyone already "knows" but that the broad ranking would never surface, since CMU lacks Harvard's massive medical school tail. In contrast, US News ranks CMU at 112th overall and 14th in CS.

### Decision Sciences is the weakest field by far.
Stanford's #1 score is h2=22 on just 285 Stanford authors, out of only 139,954 authors in the field worldwide. Compare to Medicine's h2=119 with over 7.5M authors. Decision Sciences is clearly a thin OpenAlex topic category, not a deep, well-populated discipline. H2 isn't meaningfully comparable across fields, only within them, and Decision Sciences may be too sparse to be meaningful at all.

### Universidade de São Paulo leads Dentistry, with a fellow Brazilian institution (UNICAMP) in 6th.
Brazil appears to have an outsized concentration of dental research talent, which is not something you'd intuit from any general-purpose ranking.

### Materials Science, Chemical Engineering, Energy, and Engineering are led by Chinese institutions
University of Science and Technology of China (USTC) and the University of Chinese Academy of Sciences top those fields, not Western institutions, and not the usual US News top 10. This tracks with broader trends in Chinese investment in materials/engineering research, but it's notable that it shows up this cleanly in a depth-of-talent metric, not just a publication-count metric. USTC leads three of these fields (Materials Science, Energy, Engineering) outright while sitting at #39 overall; its sister institution, the University of Chinese Academy of Sciences, leads the fourth (Chemical Engineering) from #97 overall. That's a different pattern from CMU: not a single specialty, but a cluster of related applied-science/engineering fields where one institution has built unusually deep strength across the board. If you exclude biomedical fields, USTC ranks 8th in the world and the University of Chinese Academy of Sciences ranks 23rd.

### The overall ranking is implicitly a biomedical ranking
Because medical fields have by far the largest, most cited author pools (Medicine's h2=119 dwarfs every other field), they dominate any university-wide aggregate. A university like USTC or CMU, elite in non-medical fields, will structurally never reach the top of the overall list no matter how good they are, simply because they don't have a 56,000-author medical school. The field-level breakdown matters more than the university-level number.

### Physics & Astronomy is dominated by a few institutions; Veterinary is most distributed
Physics & Astronomy is the most unequal field (Gini=0.605). University of Antwerp dominates at 15.7× the field H2 mean. Decision Science and Veterinary are the most distributed (Gini≈0.42). Counter-intuitively, Medicine's Gini (0.528) is quite middle despite Harvard's 13.9× ratio, because Medicine has more institutions with meaningful H2.

### UCLA has the greatest breadth
UCLA appears in the top 50 across more fields (20 of 26) than anyone else, and they're in the top 10 in 8. Harvard makes the top 10 in 13 of 26 fields (most of any institution) and has 19 in the top 50.

### The most efficient universities have very few authors
H2 scales roughly as the square root of output. If doubling the number of researchers doubles their collective output, H2 grows as √(2N) (r<sup>2</sup>=0.80). So an institution twice the size would naturally have an H2 that's √2× larger. Germany's Center for Behavioral Brain Sciences, ranked 1,908th overall, has the greatest H2 per sqrt(author_count) of any university. Zero universities from the top 100 overall were in the top 100 when measured by efficiency. 

### H3: Acadmic Olympics
| Country | H3 | Institutions |
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
- **US wins 22 of 26 golds:** dominant across every humanities, social science, biomedical, and prestige-science field. Its only silvers are the four fields where China wins outright: Chemical Engineering, Energy, Engineering, Materials Science. Chemistry is a tie, so the US and China share that gold.
- **China's 5 golds are in STEM:** Chemical Engineering, Chemistry (tied with the US), Energy, Engineering, and Materials Science. A clean sweep of applied and materials sciences, with no medals in arts, humanities, social sciences, or business.
- **Great Britain gets 10 silvers and 9 bronzes, but zero golds:** consistent with the UK having world-class institutions but being outgunned by the US sheer depth everywhere.
- **Germany (49) beats the UK (47)** despite a similar institution count (505 vs 548), consistent with Germany's distributed research university system where excellence isn't concentrated in two flagship universities.
- **Italy (45) almost ties Japan (46)**, even though Italy gets there with a fraction of the institutions (229 vs 1,358). Across all countries, H3 scales roughly with the logarithm of the quantity of institutions in its borders (r<sup>2</sup>=0.76). By H3/log2(institution_count), the US only narrowly edges out Italy as the most efficient country (5.81 vs 5.74).
- **South Korea (37) outranks India (34)** with less than a third the institutions (358 vs 1,154). Same pattern as Italy/Japan.
- **Saudi Arabia (H3=25, only 52 institutions)** ranks surprisingly high for its size, likely an artifact of high-h-index researchers listing Saudi affiliations as secondary appointments in exchange for grants.

## Future work
Ranking university departments would be a natural next step. You'd need department-level affiliation data, which OpenAlex doesn't currently provide, but could be approximated with a few thousand dollars of Search API calls.