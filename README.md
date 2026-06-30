# Successive H-Indices
## Highlights
1. The US News and World Report ranking (closely aligned with H2 on overall ranking) is a biomedical ranking in disguise. Harvard ranks #1 not because it's the best university in the world at everything, but because it has a 29,000-author medical school. CMU (#175), USTC (#31), and Wageningen (#148) are world leaders in their fields but structurally can't reach the top of the aggregate because they lack that medical tail. The overall number is measuring "how big is your medical school" more than it's measuring research excellence.
2. China has already won STEM, not "catching up." Seven gold medals, all in applied science and engineering fields. Zero medals in arts, humanities, social sciences, or business. This is a present-tense fact buried under Western prestige rankings that weight the fields where the US still leads.
3. Brazil is *really* good at dentistry. This is the most genuinely counterintuitive single finding. A country that appears nowhere in elite research rankings has quietly built the world's deepest bench of dental researchers.

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
- at least one affiliated institution with `type = "education"`
- at least one OpenAlex topic with a non-null field classification

This yields **17.1 million authors** across **20,669 institutions** and OpenAlex's current list of 26 fields.

## How to run
Run the scripts in order:

```bash
# 1. Download and pre-filter the OpenAlex authors snapshot from S3.
#    Writes one parquet file per partition to data/authors_staging/.
#    Resumable — safe to interrupt and re-run.
python3 prefetch.py

# 2. Build the per-author table and compute H2 by (institution, field).
#    Writes authors.csv, h2_by_institution_field.csv, and openalex.duckdb.
python3 build.py

# 3. Split h2_by_institution_field.csv into one file per field.
#    Writes to h2_by_field/<field_name>.csv.
python3 split_by_field.py

# 4. Compute institution-level H2 (ignoring field).
#    Writes h2_by_institution.csv.
python3 build_institution_h2.py

# 5. Compute H3 per country. Fetches country codes from the OpenAlex
#    institutions snapshot on S3 (no local download needed).
#    Writes h3_by_country.csv.
python3 build_country_h3.py

# 6. Split h3_by_country.csv into one file per field.
#    Writes to h3_by_field/<field_name>.csv.
python3 build_country_h3_by_field.py
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
| `authors.csv` | 17.1M rows: author_id, h_index, institution_id, institution_name, field, field_name |
| `h2_by_institution_field.csv` | 288,300 (institution, field) pairs with H2 and author count |
| `h2_by_field/` | One CSV per field, sorted by H2 descending |
| `h2_by_institution.csv` | 20,669 institutions with institution-level H2 |
| `h3_by_country.csv` | H3 index per country with institution count |
| `h3_by_field/` | One CSV per field, sorted by H3 descending |

## Selected results

### Top institutions overall

| Institution | H2 | Authors |
|---|---|---|
| Harvard University | 132 | 57,567 |
| Stanford University | 101 | 34,610 |
| Johns Hopkins University | 100 | 46,020 |
| University of Oxford | 100 | 31,730 |
| University of Cambridge | 99 | 28,016 |

The overall ranking aligns with the US News list, where Harvard ranks 1st, Stanford 3rd, Oxford 4th, and Cambridge 5th. The only thing close to a substantive disagrement between their list and that of Schubert and me is that they rank Johns Hopkins 17th instead of 3rd, and we rank MIT 23rd instead of 2nd.

Schubert and I rank my alma mater, Georgia Tech, 125th, whereas US News ranks it 94th.

Field-specific results are more interesting.

### Harvard wins the overall ranking, but only dominates some fields
Harvard tops Biochemistry, Health Professions, Immunology, Mathematics, Medicine, Neuroscience, and Psychology: basically the biomedical core plus math. But it doesn't appear in the top listings for Agricultural Sciences, Chemistry, Materials Science, Physics, Business, or Veterinary. That said, even if you exclude Medicine, Biochemistry, Immunology, Neuroscience, and Health Professions, Harvard remains #1. It is genuinely excellent.

### The university-level ranking hides real specialist powerhouses
- Wageningen University, not a famous "elite" name in the US News sense, is #1 globally in both Agricultural & Biological Sciences and Environmental Science. It's ranked 148th in the overall list because it's a specialized institution rather than a broad research university. The university-level H2 obscures genuine excellence that the field-level H2 reveals.
- Shenyang Pharmaceutical University: 490th overall, 1st in Pharmacology. A university you'd never see in a US News-style "Top 100" has the single deepest bench of high-impact pharmacology researchers on Earth by this measure.
- East China University of Science and Technology: 314th overall, but tied for 1st in Chemical Engineering. Same pattern: a mid-tier-by-reputation institution with genuine world-leading depth in one discipline.
- Université Paris-Saclay is the opposite case: #16 overall and #1 in Physics. A broad powerhouse that also happens to be the best in a specific, non-biomedical field. That's the "everything-is-consistent" case, useful as a contrast.
- Carnegie Mellon: 175th overall, #1 in Computer Science. CMU is famous for CS but is not a broad biomedical/everything powerhouse, so it sits outside the top 100 overall, yet it has the single deepest bench of high-impact CS researchers by this metric. This is the metric correctly capturing reputation that everyone already "knows" but that the broad ranking would never surface, since CMU lacks Harvard's massive medical school tail. In contrast, US News ranks CMU at 112th overall and 14th in CS.

### Decision Sciences is the weakest field by far.
Northwestern's #1 score is h2=20 with only 82 authors total in the field. Compare to Medicine's h2=113 with 29,159 authors. Decision Sciences is clearly a thin OpenAlex topic category, not a deep, well-populated discipline. H2 isn't meaningfully comparable across fields, only within them, and Decision Sciences may be too sparse to be meaningful at all.

### Universidade de São Paulo leads Dentistry, with a fellow Brazilian institution (UNICAMP) in 2nd.
Brazil appears to have an outsized concentration of dental research talent, which is not something you'd intuit from any general-purpose ranking.

### Materials Science, Chemical Engineering, Energy, and Engineering are led by Chinese institutions
University of Science and Technology of China and East China University of Science and Technology top those fields, not Western institutions, and not the usual US News top 10. This tracks with broader trends in Chinese investment in materials/engineering research, but it's notable that it shows up this cleanly in a depth-of-talent metric, not just a publication-count metric. USTC leads three of these fields while sitting at #31 overall. That's a different pattern from CMU: not a single specialty, but a cluster of related applied-science/engineering fields where one institution has built unusually deep strength across the board. If you exclude biomedical fields, USTC ranks 3rd in the world and the Chinese Academy of Sciences ranks 13th.

### The overall ranking is implicitly a biomedical ranking
Because medical fields have by far the largest, most cited author pools (Medicine's h2=113 dwarfs every other field), they dominate any university-wide aggregate. A university like USTC or CMU, elite in non-medical fields, will structurally never reach the top of the overall list no matter how good they are, simply because they don't have a 29,000-author medical school. The field-level breakdown matters more than the university-level number.

### Physics & Astronomy is dominated by a few institutions; Nursing is most distributed
Physics & Astronomy is the most unequal field (Gini=0.60). Paris-Saclay dominates at 14.6× the field H2 mean. Nursing and Veterinary are the most distributed (Gini=0.41). Counter-intuitively, Medicine's Gini (0.55) is lower than Physics despite Harvard's 15.2× ratio, because Medicine has more institutions with meaningful H2.

### Oxford has the greatest breadth
Oxford appears in the top 50 across more fields (19 of 26) than anyone else, and they're in the top 10 in 7. In contrast, Harvard makes the top 10 in 10 of 26 fields (most of any institution) but has only 15 in the top 50.

### The most efficient universities have very few authors
H2 scales roughly as the square root of output. If doubling the number of researchers doubles their collective output, H2 grows as √(2N) (r<sup>2</sup>=0.82). So an institution twice the size would naturally have an H2 that's √2× larger. Germany's Center for Behavioral Brain Sciences, ranked 1,954th overall, has the greatest H2 per sqrt(author_count) of any university. Zero universities from the top 100 overall were in the top 100 when measured by efficiency. 

### H3: Acadmic Olympics
| Country | H3 | Institutions |
|---|---|---|
| US | 66 | 4,159 |
| CN | 53 | 1,075 |
| DE | 47 | 497 |
| GB | 44 | 529 |
| IT | 43 | 220 |
| JP | 43 | 1,270 |
| ES | 38 | 155 |
| FR | 38 | 390 |
| KR | 36 | 351 |
| AU | 35 | 119 |

A few things stand out:
- **US wins 19 of 26 golds:** dominant across every humanities, social science, biomedical, and prestige-science field. Its only silvers are the six fields where China leads.
- **China's 7 golds are in STEM:** Agricultural Sciences, Chemical Engineering, Chemistry, Energy, Engineering, Materials Science, and Pharmacology. A clean sweep of applied and materials sciences, with no medals in arts, humanities, social sciences, or business.
- **Great Britain gets 8 silvers and 1 shared gold:** consistent with the UK having world-class institutions but being outgunned by the US sheer depth everywhere. The one gold is Arts and Humanities, which it shares with the US.
- **Germany (47) beats the UK (44)** despite a similar institution count, consistent with Germany's distributed research university system where excellence isn't concentrated in two flagship universities.
- **Italy and Japan tie at 43**, but Italy achieves that with 221 institutions to Japan's 1,281. Across all countries, H3 scales roughly with the logarithm of the quantity of institutions in its borders (r<sup>2</sup>=0.75), and Italy is the most efficient country measured by H3/log2(institution_count).
- **South Korea (36) outranks India (33)** with less than a third the institutions (352 vs 1,156). Same pattern as Italy/Japan.
- **Saudi Arabia (H3=24, only 54 institutions)** ranks surprisingly high for its size, likely an artifact of high-h-index researchers listing Saudi affiliations as secondary appointments in exchange for grants.

## Future work
Ranking university departments would be a natural next step. You'd need department-level affiliation data, which OpenAlex doesn't currently provide, but could be approximated with a few thousand dollars of Search API calls.