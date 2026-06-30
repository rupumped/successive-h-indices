# Successive H-Indices
In 2007, Andras Schubert published a paper titled "Successive h-indices." It begins:
> Hirsch's *excessively discussed* h-index generated a long row of interpretations, applications and derivatives within a surprisingly short period. Symptomatically, Hirsch's paper in the *Proceedings of the National Academy of Sciences of the United States of America* became the second highest cited paper of the issue in which it had been published. In this note, attention is called to an apparently so far overlooked option: h-indices themselves may form the basis of a successive series of h-indices.

> Given, e.g., the h-indices of the researchers of an institute (which indices will be denoted by h<sub>1</sub> in what follows), an index, h<sub>2</sub>, of the institute can be determined: the institute has an index h<sub>2</sub> if h<sub>2</sub> of its N researchers have an h<sub>1</sub>-index of at least h<sub>2</sub> each, and the other (N−h<sub>2</sub>) researchers have h<sub>1</sub>-indices lower than h<sub>2</sub> each. The succession can then be continued, e.g., for networks of institutions or countries or other higher levels of aggregation.

> Since no sufficient data for testing the concept on the researcher–institute–country hierarchy were available, another example was chosen.

Fifteen years later, OpenAlex launched a FOSS bibliographic catalogue complete with citation indexing, authors, fields, and institutions. We now have the dataset for which Schubert wished in 2007. Schubert implied that computing the h<sub>2</sub> of institutes would be more interesting than that of journals. This is that analysis.

## Goal
Compute the **H2 index** for every (institution, field) pair in [OpenAlex](https://openalex.org/).

**H2 = n** means *n* authors affiliated with that institution, working in that field, have an h-index of at least *n*. It is the h-index applied one level up, to a group of researchers rather than a group of papers.

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

## Selected results

### Top institutions overall

| Institution | H2 | Authors |
|---|---|---|
| Harvard University | 132 | 57,567 |
| Stanford University | 101 | 34,610 |
| Johns Hopkins University | 100 | 46,020 |
| University of Oxford | 100 | 31,730 |
| University of Cambridge | 99 | 28,016 |

To be honest, this isn't super surprising. In the US News list, Harvard ranks 1st, Stanford 3rd, Oxford 4th, and Cambridge 5th. The only thing close to a substantive disagrement between their list and ours is that they rank Johns Hopkins 17th instead of 3rd, and I rank MIT 23rd instead of 2nd.

My alma mater, Georgia Tech, ranks 94th according to US News and 125th according to ours.

How about field-specific results?

### Harvard wins the overall ranking, but only dominates some fields
Harvard tops Biochemistry, Health Professions, Immunology, Mathematics, Medicine, Neuroscience, and Psychology: basically the biomedical core plus math. But it doesn't appear once in the top listings for Agricultural Sciences, Chemistry, Materials Science, Physics, Business, or Veterinary. Its overall #1 ranking is really a story about the breadth and depth of its medical school, not universal excellence.

### The university-level ranking hides real specialist powerhouses
- Wageningen University, not a famous "elite" name in the US News sense, is #1 globally in both Agricultural & Biological Sciences and Environmental Science. It's ranked 148th in the overall list because it's a specialized institution rather than a broad research university. The university-level H2 obscures genuine excellence that the field-level H2 reveals.
- Shenyang Pharmaceutical University: 493rd overall, 1st in Pharmacology. A university you'd never see in a US News-style top 500 has the single deepest bench of high-impact pharmacology researchers on Earth by this measure.
- East China University of Science and Technology: 314th overall, #1 in Chemical Engineering. Same pattern: a mid-tier-by-reputation institution with genuine world-leading depth in one discipline.
- Université Paris-Saclay is the opposite case: #16 overall and #1 in Physics. A broad powerhouse that also happens to be the best in a specific field. That's the "everything-is-consistent" case, useful as a contrast.
- Carnegie Mellon: 175th overall, #1 in Computer Science. CMU is famous for CS but is not a broad biomedical/everything powerhouse, so it sits outside the top 100 overall, yet it has the single deepest bench of high-impact CS researchers by this metric. This is the metric correctly capturing reputation that everyone already "knows" but that the broad ranking would never surface, since CMU lacks Harvard's massive medical school tail. In contrast, US News ranks CMU at 112th overall and 14th in CS.

### Decision Sciences is the weakest field by far.
Northwestern's #1 score is h2=20 with only 82 authors total in the field. Compare to Medicine's h2=113 with 29,193 authors. Decision Sciences is clearly a thin OpenAlex topic category (probably a niche subfield like operations research / management science), not a deep, well-populated discipline. Worth flagging in methodology: H2 isn't comparable across fields, only within them, and Decision Sciences may be too sparse to be meaningful at all.

### Universidade de São Paulo leads Dentistry, with a fellow Brazilian institution (UNICAMP) in 2nd.
Brazil appears to have an outsized concentration of dental research talent, which is not something you'd intuit from any general-purpose ranking.

### Materials Science, Chemical Engineering, Energy, and Engineering are led by Chinese institutions
University of Science and Technology of China, East China University of Science and Technology top those fields, not Western institutions, and not the usual US News top 10. This tracks with broader trends in Chinese investment in materials/engineering research, but it's notable that it shows up this cleanly in a depth-of-talent metric, not just a publication-count metric. USTC leads three of these fields while sitting at #31 overall. That's a different pattern from CMU: not a single specialty, but a cluster of related applied-science/engineering fields where one institution has built unusually deep strength across the board.

### The overall ranking is implicitly a biomedical ranking
Because medical fields have by far the largest, most cited author pools (Medicine's h2=113 dwarfs every other field), they dominate any university-wide aggregate. A university like USTC or CMU, elite in non-medical fields, will structurally never reach the top of the overall list no matter how good they are, simply because they don't have a 29,000-author medical school. The field-level breakdown matters more than the university-level number.

## Future work
I think it would be cool to rank university departments using this metric, and you'd probably only need a few thousand dollars to spend on Search APIs to do it. I also think it would be cool to compute Schubert's h<sub>3</sub> metric for countries.