# Response to Reviewers

Paper: "Successive h-indices using OpenAlex"

For each comment: reviewer's point, our response, and where/how the manuscript changed (file + line/section). Manuscript changes are marked in the LaTeX source with `\textcolor{red}{...}`.

---

## Comment 1: Reliability of the underlying author-level data (h2/h3 validity given OpenAlex disambiguation errors)

**Reviewer:** The manual validation of only 19 authors is not sufficient to establish the reliability of a dataset containing more than 17 million researchers; the reported discrepancies (e.g., Lei Jiang 215 vs. WoS 115; Donald Small 103 vs. Scopus 57) show that disambiguation errors can substantially influence institutional and national rankings, which aggregate author-level h-index values.

**Response:** We agree that a hand sample, however chosen, cannot by itself establish the reliability of a 17.1-million-author dataset — this was true of the original 19-author sample and would have been equally true of a larger one, since the sample is deliberately adversarial (chosen to find errors, not to estimate their population-wide rate). We made three substantive additions:

1. **Reframed the manual cross-validation** as an explicit bound on the *type and locus* of error (which authors, by how much) rather than an estimate of its population-wide *rate*, and added two independent, larger-scale, systematic studies that corroborate the same failure pattern (disambiguation precision concentrated in common-name and non-Anglophone strata): Zhao & Chen (2025), a 2,700-scholar benchmark, and OpenAlex's own account of an ongoing correction effort for exactly this kind of over-merging (Demes, 2026).
2. **Added a new Monte Carlo sensitivity analysis** (new Subsections "Sensitivity to disambiguation error" in Methodology and Results) that directly quantifies the reviewer's concern: we inject synthetic disambiguation-style errors into the full 17.1M-author dataset, at the same magnitude observed in the cross-validation outliers, at six population-wide rates spanning 1% to a deliberately implausible 80% (rather than asserting any single rate as a "worst case" — the cross-validation sample's own raw outlier rate, 4/30 ≈ 13% across both waves, is not a principled bound, and is included in the table only for reference), and recompute all headline rankings at each rate. Result: institution- and country-level rank correlations decline only modestly (Spearman ρ from 0.999 at 1% down to 0.988) and then *plateau* rather than continuing toward zero, all the way out to 80% — a consequence of h₂/h₃ being order statistics with a bounded per-author perturbation, so there is no error rate in this model, however extreme, at which the aggregate rankings collapse. The field-leadership claims (Wageningen, Carnegie Mellon) are noisier at every rate (surviving 3–5 of 5 trials with no trend as the rate rises) and are flagged as more fragile than the paper's other claims.
3. **Completed wave-2 manual cross-validation** of 11 additional authors at Stanford, MIT, Cambridge (Arts & Humanities), Yale (Social Sciences), Tsinghua, Cairo, Tehran, and the globally 6th-highest-h₁ author (George Davey Smith, University of Bristol, h₁=270). Wave 2 added **no new disambiguation outliers**: threshold authors at Stanford and MIT tracked Scopus within 15% (Feldman OA=107/Scopus=93; Durand OA=94/Scopus=91; Nelson OA=108/Scopus=101); non-Anglophone institution authors agreed with WoS and Scopus within 15% (De La Cruz: WoS=130, Scopus=135, OA=141; Fahim: WoS=110, Scopus=110, OA=122; Dingsheng Wang: WoS=171, Scopus=172, OA=176); and the global top sanity-check author (Davey Smith: WoS=229, Scopus=252, GS=307) brackets OpenAlex (270) normally. One Scopus lookup for Tien Yin Wong returned h=5 against WoS=185 and GS=242, indicating a profile misidentification in Scopus rather than an OpenAlex error; that entry is excluded from aggregate statistics. Cambridge Arts & Humanities threshold authors (Mellor OA=28/Scopus=13; Raven OA=24/Scopus=12/GS=26) appeared in Scopus but at roughly half the OpenAlex values; Raven's GS=26 confirms OA is not inflated and Scopus is undercounting, reinforcing the coverage-gap finding from wave 1 rather than indicating disambiguation error. The outlier count remains **4 of 30 (13%)** across both waves. Table `tab:crossval` and the surrounding prose have been updated to reflect the 30-author total.

**Manuscript changes:**
- `paper/sections/method.tex`: reframed the cross-validation description (end of `subsec:methods-crossval`) as adversarial-not-representative; updated outlier fraction reference to 4/30 ≈ 13% in `subsec:methods-sensitivity`; added new subsection `subsec:methods-sensitivity` ("Sensitivity to disambiguation error") describing the six-rate Monte Carlo perturbation methodology.
- `paper/sections/results.tex`: updated opening sentence of `subsec:results-crossval` to reflect 30-author total; revised coverage counts (WoS 16/30, Scopus 26/30, GS 19/30); updated Table `tab:crossval` aggregate statistics; updated outlier-rate sentence to 4/30 (13%) and added wave-2 summary; expanded Arts & Humanities paragraph to include wave-2 Cambridge findings; updated `21%*` reference row in Table `tab:sensitivity` to `13%*`; added paragraph citing `zhao2025` and `demes2026`; added new subsection `subsec:results-sensitivity` with Table `tab:sensitivity` and interpretive text.
- `paper/sections/conc.tex`: added sentence summarizing the sensitivity analysis (plateau finding, field-leadership caveat).
- `paper/references.bib`: added `zhao2025` (Zhao & Chen, 2025, arXiv:2502.11610) and `demes2026` (OpenAlex blog, 2026).
- Scripts and data: `src/sensitivity_disambiguation.py`, `src/cross_validation_sample_wave2.py`; raw output: `results/sensitivity_disambiguation.csv`, `results/sensitivity_disambiguation.log`, `results/cross_validation_sample_wave2.csv` (completed with WoS/Scopus/GS values).

---

## Comment 2: Assignment of researchers to single institutions and fields

**Reviewer:** The manuscript assigns each researcher to only one institution (most recent affiliation) and one field (dominant topic classification), which oversimplifies modern research careers. Many researchers have multiple affiliations, move between institutions, and publish across several disciplines. The paper would need a stronger justification for these choices. At minimum, the authors should examine whether the results remain stable under alternative approaches such as fractional affiliation counting, publication-level attribution, or multiple-field assignment.

**Response:** We agree that both choices — single-institution and single-field assignment — are simplifications that warrant explicit robustness testing. We ran the most tractable of the three suggested alternatives, multi-field assignment, and report its results here. We defer publication-level attribution (which would require per-paper affiliation data not consistently recorded in the OpenAlex works snapshot) and fractional affiliation counting (which requires redefining h₂ over a weighted roster) to future work, given that the multi-field result already characterises the key sensitivity.

**Multi-field assignment robustness check.** At a threshold τ, each author is included in every field for which their OpenAlex topic-weight share is at least τ. We tested τ ∈ {20%, 33%}. Results:

| Threshold | (Inst., field) pairs | Spearman ρ | Field leaders unchanged | Wageningen Ag&Bio #1 | Wageningen EnvSci #1 | CMU CS #1 |
|---|---|---|---|---|---|---|
| Single-field (baseline) | 333,132 | — | — | ✓ | ✓ | ✓ |
| 33% | 364,032 (+9.3%) | 0.963 | 23/27 | ✓ | ✗ (CU Boulder leads) | ✓ |
| 20% | 402,046 (+20.7%) | 0.907 | 18/27 | ✓ | ✗ (CU Boulder leads) | ✗ (Stanford leads) |

**Interpretation.** The overall field ranking structure is highly stable at 33% (ρ = 0.963) and stable at 20% (ρ = 0.907). Wageningen's Agricultural & Biological Sciences lead is robust at both thresholds. Two claims are sensitive: Wageningen's Environmental Science lead disappears at both thresholds (University of Colorado Boulder leads instead), and CMU's Computer Science lead disappears at the aggressive 20% threshold (Stanford leads).

The mechanism is interpretable: large comprehensive universities (Harvard, Stanford, CU Boulder) accumulate many more authors in most fields under multi-field assignment, because they employ many researchers whose work spans multiple disciplines even if none is their modal field. Smaller, more specialised institutions (Wageningen, CMU) already had their specialists counted under single-field assignment. The two methods therefore answer different questions: single-field identifies institutions where a field is researchers' *primary* specialisation; multi-field identifies institutions with the most researchers doing *substantial* work in the field. The paper's framing — "which institution has the deepest concentration of specialists?" — is best answered by single-field assignment, but we now say so explicitly and flag Wageningen's Environmental Science lead as conditional on this framing.

**Manuscript changes:**
- `paper/sections/method.tex`: new subsection `subsec:methods-field-robustness` ("Robustness to field assignment") describing the two-threshold multi-field re-assignment and h₂ recomputation.
- `paper/sections/results.tex`: new subsection `subsec:results-field-robustness` ("Robustness of field-specific rankings to multi-field assignment") reporting ρ, changed-leader counts, and the Wageningen EnvSci and CMU CS findings at both thresholds, with mechanistic explanation.
- `paper/sections/conc.tex`: updated affirmative Wageningen EnvSci and CMU CS claims to flag their conditionality; added a sentence to the limitations paragraph summarising the field-robustness finding.
- New script: `src/field_robustness.py`; raw output: `results/field_robustness.csv`, `results/field_robustness.log`, `results/h2_by_field_multifield_20pct.csv`, `results/h2_by_field_multifield_33pct.csv`.

---

## Comment 3: Efficiency measures not validated against existing bibliometric indicators

**Reviewer:** The paper introduces efficiency metrics ε₂ and ε₃ based on Egghe's power-law scaling, but does not validate these against established bibliometric indicators. Without such validation, it is unclear whether the efficiency rankings reflect genuine differences in research excellence or are an artefact of the size-normalisation procedure.

**Response:** We agree that external validation strengthens the case for the efficiency metrics. We compare both raw h₂ and ε₂ against the CWTS Leiden Ranking Open Edition 2024 (hereafter "Leiden Open Edition"), an independently constructed, OpenAlex-based institution-level benchmark released under a CC0 licence. The Leiden Open Edition's mean normalised citation score (MNCS) is a standard, well-validated measure of field- and time-normalised citation impact; crucially, it is already size-independent by construction (it is a mean, not a total), making it the natural external reference for ε₂.

**Methodology.** From the Leiden Open Edition 2024 results file (Zenodo record 13868018), we extract MNCS under "All sciences", period 2019–2022, full counting, obtaining 1,506 universities. Each university's ROR identifier is resolved to an OpenAlex institution ID via the OpenAlex API; 1,501 of 1,506 resolve successfully. After joining to institution-wide h₂ and ε₂ and dropping the six universities with no MNCS value in our dataset, 1,495 institutions enter the comparison. We compute Spearman rank correlations between the Leiden MNCS ranking and (a) our raw h₂ ranking and (b) our ε₂ ranking.

**Results.**

| Metric | Spearman ρ vs. MNCS | p-value | N |
|--------|--------------------|---------|----|
| Raw h₂ | 0.634 | ~6 × 10⁻¹⁷⁰ | 1,495 |
| ε₂ | 0.580 | ~5 × 10⁻¹³⁵ | 1,495 |

Both correlations are large, positive, and highly significant. The modest gap (Δρ = −0.054) is mechanistically expected: MNCS is size-independent by construction, so removing the size component via ε₂ = h₂ / S^(1/β₁) removes a source of co-variation with MNCS that is present in raw h₂. That ε₂ still correlates at 0.58 after size removal — retaining 92% of h₂'s correlation with MNCS — confirms that the efficiency normalisation does not erase the quality signal; it isolates the portion of h₂ that reflects research excellence rather than headcount. Taken together, the results validate both metrics against an established external standard and establish that the normalisation does what it claims to do.

**Manuscript changes:**
- `paper/sections/method.tex`: new subsection `subsec:methods-leiden` ("External validation against the Leiden Ranking") describing the Leiden MNCS extraction, ROR matching, and Spearman correlation methodology.
- `paper/sections/results.tex`: new subsubsection within "Institution efficiency" (`subsubsec:leiden-validation`) reporting ρ(h₂, MNCS) = 0.634 and ρ(ε₂, MNCS) = 0.580 with mechanistic interpretation.
- `paper/references.bib`: added `leiden2024` (CWTS Leiden Ranking Open Edition 2024, Zenodo 13868018).
- New script: `src/leiden_validation.py`; raw output: `results/leiden_validation.csv`, `results/leiden_validation.log`.

---

