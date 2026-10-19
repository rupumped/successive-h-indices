# Response to Reviewers — Round 3

I thank the reviewer for their comments. All new text is in red.

## Comment 1

**Reviewer:** The author should explain how this paper differs from Yang et al. (2023), The k-step h-index in citation networks at the paper, author, and institution levels, Journal of Informetrics, 17(4), 101456, https://doi.org/10.1016/j.joi.2023.101456. This is directly relevant prior work on extending h-type indicators across scientific entities and is missing from the manuscript's discussion. The central distinction concerns what is extended. Here, the succession moves through an organizational hierarchy: author h₁ values are aggregated into institutional h₂, and institutional h₂ values into country h₃. Yang et al.'s k-step approach incorporates higher generations of citation information in networks at the paper, author, and institution levels. Thus, the successive level in this manuscript and the citation-generation parameter k in Yang et al. have different meanings. The author should make this distinction explicit, compare the information inputs and interpretation of the two approaches, and explain what the present implementation adds. A worked example would help prevent readers from treating these indices as equivalent. The contribution should be framed as a large-scale application and assessment of an established successive-index construction. Where feasible, a comparison on a common institutional sample would clarify whether the approaches provide complementary information.

**Response:**

The reviewer is correct, and I thank them for the pointer. Yang et al. (2023) was missing from the manuscript and I add it to the introduction.

The two families differ in which dimension "successive" extends. Yang et al.'s k-step h-index extends the *citation graph* at a fixed organizational level: their k=2 h-index for an author counts a set of papers that includes papers that cite the author's papers (one additional citation hop outward), and the h-index is taken over that augmented set; the construction is defined at the paper, author, and institution levels, with k controlling citation-chain depth. The present paper's subscript extends the *organizational hierarchy*: h₂ for an institution counts how many of its authors have h₁ ≥ n, and h₃ for a country counts how many of its institutions have h₂ ≥ n. The parameter k and the subscript both generate families of indices, but they extend orthogonal dimensions: citation depth within a level versus organizational level of aggregation.

A worked example clarifies the distinction. Suppose institution X has 100 authors, 60 of whom have h₁ ≥ 60; then X has h₂ = 60 in this paper's framework. Under Yang et al., institution X's k=1 h-index is its standard institutional h-index over all papers produced by its researchers, and its k=2 h-index expands the paper set to include all papers that cite those. This produces a different number that answers a different question: *how deep a citation chain does institution X anchor?* The present paper's h₂ = 60 answers: *how concentrated is high-h₁ talent at institution X?* The information inputs also differ: Yang et al. require traversal of the full citation graph; this paper requires only each author's scalar h₁ value, which enabled computation at 13.3-million-author scale directly from the OpenAlex authors snapshot without traversing citation links.

The reviewer is correct: the primary contribution of this paper is a large-scale empirical application and assessment of Schubert's (2007) successive-index hierarchy, and I make this explicit in the introduction. A numerical comparison on a common institutional sample would require reimplementing Yang et al.'s k-step algorithm over OpenAlex's full citation graph at institutional scale, which is beyond the scope of this paper; I flag it as a natural direction for future work.

**Manuscript change:** Sentences distinguishing the two families are added at the end of the related-work paragraph in Section 1 (Introduction). The worked example above is provided here for the reviewer's convenience; the manuscript keeps the treatment brief given that the two indices extend orthogonal dimensions and are not in direct competition. One paragraph in the conclusion addresses comparison as future work.

---

## Comment 2

**Reviewer:** Sections 3.9 and 3.11 report uncentered R² values of 0.909 and 0.900 from regressions through the origin, then describe these as explaining 91% and 90% of variance. Uncentered R² uses deviations from zero rather than deviations from the outcome mean; it does not support this usual interpretation of explained variance. The abstract and conclusion should be corrected. Please report centered goodness-of-fit measures, residual diagnostics, and uncertainty, and compare the prescribed exponents with exponents estimated directly from the relationship between group size and the successive index. A zero index at zero group size does not by itself establish that a regression through the origin adequately describes the observed positive-size range. The fitted coefficients also matter. Equation (1) presents a unit-amplitude prediction, but the fitted institution coefficient is 2.422; the country coefficient is 3.534. Consequently, ε₂ > 1 does not indicate above-average performance relative to the fitted empirical baseline. Normalizing by the full fitted expectation would retain the ranking within a model while giving the benchmark a clearer interpretation. More fundamentally, dividing by a size power does not establish that the result is size-independent. Please test whether the normalized scores retain associations with size, field composition, and career age. Until this is demonstrated, "size-adjusted index" is a more defensible term than "efficiency," which implies an assessment of outputs relative to meaningful resource inputs.

**Response:**

The reviewer raises several valid technical points, which I address in turn.

**(a) Uncentered R² language.** "Explains X% of the variance" is indeed imprecise for uncentered R². The forced-through-origin regression is correct on physical grounds. Zero authors necessarily implies h₂ = 0, so the no-intercept form is appropriate. I replace "explains X% of the variance" with "uncentered R² = X" and add the centered R². Recomputing: the institution-level fit gives uncentered R² = 0.909 (centered R² = 0.810); the country-level fit gives uncentered R² = 0.900 (centered R² = 0.753).

**(b) Fitted coefficients and normalization baseline.** The reviewer correctly identifies that the empirical baseline is c₂ · S^(1/β₁) ≈ 2.422 · S^(1/β₁), not the unit-amplitude prediction S^(1/β₁). Under the current definition ε₂ = h₂ / S^(1/β₁), an institution at the empirical average has ε₂ ≈ 2.422, so ε₂ > 1 indicates above-average performance relative to the *theoretical* Egghe prediction, not the empirical one. I update the definition to normalize by the full fitted expectation: ε₂ = h₂ / (c₂ · S^(1/β₁)) with c₂ = 2.422, and analogously ε₃ = h₃ / (c₃ · R^(1/β₂)) with c₃ = 3.534. All rankings are preserved (c₂ and c₃ are constants), but now ε₂ > 1 means the institution is above the empirical regression line for its headcount. Size-adjusted values in all tables are updated accordingly.

**(c) Size-independence test.** I regressed log(ε₂) on log(S) across institutions with ≥ 100 authors (n = 8,118) and log(ε₃) on log(R) across countries with ≥ 5 institutions (n = 150). Because dividing by the constant c₂ shifts the log-space intercept but not the slope, this test gives identical results under either the old or the updated ε₂ definition. Results: institution-level residual slope = 0.073, R² = 0.062; country-level residual slope = 0.151, R² = 0.260. Both retain a statistically significant positive association with size after normalization, a genuine limitation I report and discuss.

I flag field-specific ε₂ computation and regression as future work and add it explicitly as an uncontrolled confound alongside career age, which OpenAlex does not expose.

**(d) OLS log-log comparison.** I ran an OLS regression of log(h₂) on log(S) as an empirical alternative to Egghe's model. The estimated slope is 0.404 (implying an effective β ≈ 2.47), versus Egghe's β₁ = 2.991 (implied slope 0.334). Egghe's β₁ implies a steeper power-law decay of the h₁ tail than the log-log regression suggests, meaning the normalization slightly under-adjusts for size (consistent with the positive residual slope above). At the country level, the OLS slope is 0.502 (implied β ≈ 1.99) versus Egghe's β₂ = 2.847 (slope 0.351); the discrepancy is larger here, consistent with the larger residual R² (0.260). I report both exponents in the manuscript. Please note that the log-log centered R² is, coincidentally, 0.795 at both the institution and country levels.

**(e) Terminology.** I accept "size-adjusted index" as the primary term throughout the manuscript.

**Manuscript changes:** Abstract, Methods, Results, and the Conclusion updated with corrected language, centered R², residual test, and OLS comparison.

---

## Comment 3

**Reviewer:** The manuscript acknowledges that the compounding-exponent predictions fail substantially. This is useful, but the alternative justification needs stronger evidence. A tail exponent estimated from the pooled h₁ distribution does not automatically determine the scaling of h₂ with institutional headcount across heterogeneous institutions. Please explain the assumptions linking the pooled distribution to each institution's threshold, including the role of the distribution's amplitude and the selected tail cutoff. Institutions whose h₂ falls below that cutoff may lie outside the fitted tail's domain. Report the fitted cutoffs, tail sample sizes, exponent uncertainty, goodness-of-fit tests, and comparisons with plausible alternative distributions. Clarify the probability-mass versus survival-exponent convention. Separate failure of the original model's assumptions from evidence against its derivation, and compare the proposed normalization with an empirical size model or a resampling baseline. The current high uncentered R² cannot alone validate the chosen theoretical exponent.

**Response:**

The reviewer's request for fuller diagnostic reporting is well-founded. I add the following to the manuscript.

**(a) Fitted cutoffs, tail sizes, uncertainty, and goodness-of-fit.** The discrete MLE tail fits (Clauset et al., 2009), already computed but not fully reported, yield:

- **β₁** (h₁ across authors): x_min = 18, n_tail = 199,953 (fit on 2M-point subsample of 13.3M population), KS D = 0.063. SE(β₁) ≈ (β₁ − 1)/√n_tail ≈ 0.004, so β₁ = 2.991 ± 0.004. Loglikelihood-ratio test (LRT) of power-law vs. exponential within the tail: R = −25.3, favoring exponential above x_min = 18.
- **β₂** (h₂ across institutions): x_min = 18, n_tail = 3,918 (of 19,103 institutions), KS D = 0.064. SE(β₂) ≈ 0.030, so β₂ = 2.847 ± 0.030. LRT: R = −9.0, again favoring exponential above x_min = 18.

I now report the LRT results, exponential favored over power-law in the upper tail for both h₁ and h₂: R = −25.3 for h₁ and R = −9.0 for h₂. The exponential provides a better fit than a strict power law within the fitted tail. The LRT concerns the tail-distribution shape; the question relevant to size scaling is whether the power-law functional form h₂ ∝ S^α holds across the full institution-size range, which the regression addresses separately.

**(b) Linking pooled distribution to institutional scaling.** I add an explicit discussion of the key assumption: the normalization treats each institution's author roster as a draw from the pooled h₁ distribution, so the pooled β₁ approximates the within-institution tail exponent. This fails to the extent that institutions selectively recruit high-h₁ talent (a self-fulfilling bias), which is exactly what the amplitude c₂ = 2.422 and the positive residual size slope (0.073) reflect.

**(c) Resampling baseline.** The reviewer's objection that the regression validates the power-law *form* but not the specific *exponent* β₁ is correct, and the manuscript now makes this distinction explicit. The regression supports the form; the exponent β₁ = 2.991 comes from the h₁ fit, not from the regression. Using the empirical OLS exponent instead would remove the residual size association by construction, but would also sever the connection to the underlying h₁ distribution that Egghe's theory provides. The Egghe exponent is chosen because it is grounded in the distribution of the objects being counted, not because the regression validates it; the mismatch between OLS slope (0.404) and implied Egghe slope (0.334) is the source of the residual size association, which is reported and discussed.

To test the random-draw assumption directly, as the reviewer requested, I implement a resampling baseline: for a log-spaced grid of institution sizes, I draw 500 independent random rosters by sampling individual h₁ values from the 13.3-million-author pool and apply the same h-index algorithm used for real institutions. Fitting the no-intercept regression on the simulated mean h₂ values gives a random-draw coefficient c_random = 2.64, versus the empirical c₂ = 2.422. The empirical amplitude is lower than the random-draw expectation because the global h₁ pool is right-skewed by elite-institution authors; a random sample naturally includes some of these authors by chance. About 30% of institutions exceed the random-draw expectation; the median institution achieves approximately 84% of it. The ε₂ normalization anchors at the empirical regression, so ε₂ = 1 corresponds to the average empirical institution, which sits about 8% below the random-draw null; an institution must reach ε₂ ≈ 1.09 to exceed that null. This result confirms that the assumption is not exactly satisfied. High-h authors are concentrated rather than randomly distributed. This ground the normalization in the empirically observed scaling rather than the random-draw null.

**(d) Empirical OLS comparison.** As reported in response to Comment 2, the OLS log-log regression of log(h₂) on log(S) gives slope 0.404 (implied β ≈ 2.47) versus Egghe's β₁ = 2.991 (implied slope 0.334). Both exponents are reported and compared in the manuscript.

**(e) Convention.** The `powerlaw` package uses the parameterization P(X = x) ∝ x^(−α) for x ≥ x_min following Clauset et al. (2009), which matches Egghe's Lotka-law convention directly; no offset is needed. I add a clarifying sentence to the Methodology.

**(f) Separating empirical fit from theoretical prediction.** I sharpen the existing separation: the empirical size-scaling relationship h₂ ∝ S^(1/β₁) is a data description; the compounding formula α₀α₁ ≈ β₁ is the theory that fails. The size-adjusted metric depends on the former, not the latter. The regression validates the form; the exponent comes from the h₁ tail.

**(g) Lognormal and truncated power-law comparisons.** The Clauset et al. (2009) protocol specifies the exponential as the primary alternative to a power law, and both LRT tests are reported. The goal of the tail-distribution comparison is not to find the best-fitting distribution but to document where the power-law model breaks down; the exponential comparison is sufficient for that purpose. Adding lognormal and truncated power-law fits would shift the paper's focus toward distribution selection, which is not the contribution here. I add one sentence to the Results noting that the Clauset et al. protocol is followed for the tail comparison.

**Manuscript changes:** Results updated with corrected LRT language, explicit form/exponent separation, resampling baseline, and Clauset-protocol note.

---

## Comment 4

**Reviewer:** An author's full-career h₁ is assigned to an institution using that author's last five publishing years. These years can be far in the past for an inactive or deceased researcher, and the credited impact can originate at earlier institutions. The resulting roster therefore measures neither a current workforce nor research produced by the institution within a common period. Please define the intended construct and test a common recent publication window, an activity criterion, and, if feasible, an indicator based on works actually affiliated with each institution. Career-age differences should also be examined. The multi-institution variant assigns each author's full h₁ to every qualifying institution. This is full counting, not fractional counting, as suggested in Section 2.11. Integer-valued h-indices do not prevent fractional treatment of inputs or weighted threshold constructions. Rename this variant and discuss the implications of duplicate attribution. At country level, institutional splitting, mergers, and campus-versus-system representation can change both h₃ and its normalization denominator without changes in underlying research. Test sensitivity to organizational granularity before interpreting national "efficiency."

**Response:**

**(a) Intended construct and activity criterion.** The five-year window deliberately measures each author's primary institutional affiliation *during their most recent active publishing period*, not current employment. It assigns accumulated h₁ to the institution where the author most recently produced research, a retrospective measure of institutional talent concentration in recent output. I add an explicit statement of this construct to the Methods, acknowledging that it credits inactive and relocated researchers to their last-active institution rather than their current position.

The OpenAlex data does include a "recently active" robustness variant (restricting to authors with at least one publication in the five years preceding the snapshot extraction date). This feeds into the attribution robustness results in Table 4 under the "most-recent-snapshot" variant, which is the closest available sensitivity check. The most-recent-snapshot Spearman correlation of 0.907 (Table 4) reflects the sensitivity to this choice. A strictly affiliation-based indicator, crediting only the h₁ contribution from papers affiliated with a given institution, would require computing per-author, per-institution h-indices from the works graph, a substantially different construction beyond this paper's scope.

**(b) Full counting, not fractional counting.** The reviewer is correct. The multi-institution variant assigns each author's *full* h₁ to every qualifying institution. This is full counting. Fractional counting would require splitting the h₁ contribution across institutions, which is not trivially defined for an integer-valued rank-threshold index (a weighted threshold construction would be needed). I rename this variant the **full-counting variant** throughout and add a note in the Methodology explaining the distinction and its implication: institutions with many multiply-affiliated authors gain more from this rule than institutions with mostly single-affiliated authors.

**(c) Country-level organizational granularity.** Using OpenAlex's institution-lineage tree, I roll every institution up to its top-level same-country parent system and recompute h₃ and ε₃ on the consolidated roster.

Of the institutions with h₂ > 0, 5.5% have a same-country parent system distinct from themselves. Rank correlations between the original and rolled-up rankings are Spearman ρ = 0.9981 for h₃ and ρ = 0.9964 for ε₃, indicating that organizational granularity has negligible effect on the ordinal rankings. I added a paragraph about this analysis in the robustness Results section.

I adopt the reviewer's recommended "size-adjusted index" terminology and add a sentence noting that institution count is defined by OpenAlex's taxonomy..

**Manuscript changes:** Methodology subsections renamed and updated; granularity sensitivity added to the robustness Results section.

---

## Comment 5

**Reviewer:** The targeted sample of 30 authors is appropriately described as unsuitable for estimating population error rates. However, cross-database h-index discrepancies do not establish merged identities: coverage, document types, citation links, profile scope, and matching errors can also produce differences. In particular, the reported A. Jafari values of 139 in OpenAlex and 133 in Scopus do not substantiate a merge simply because Web of Science reports 41. The identified cases need publication-level identity checks, with separate conclusions about coverage and disambiguation. The Monte Carlo analysis multiplies existing h₁ values by ratios from four disputed cases while keeping identities, affiliations, and fields fixed. Actual merges and splits can also alter roster sizes and attribution. The country-specific multiplier and symmetric inflation/deflation assumptions need justification and alternative scenarios. Add concentrated and directional errors around institutional thresholds, report uncertainty across trials, and explain how ties and leader survival are handled. At p = 13%, Table 12 retains only 47% of the institutional top 20 despite a Spearman correlation of 0.9946. This shows that a high correlation across thousands of institutions can coexist with unstable headline rankings; the conclusions should give appropriate weight to that instability.

**Response:**

**(a) A. Jafari case and publication-level checks.** The reviewer is correct that the OA = 139 / Scopus = 133 agreement for A. Jafari (4% difference) does not support a disambiguation merge conclusion, and I revise the text accordingly. I did not perform publication-level identity verification (matching individual works across databases for each candidate author), and I acknowledge that this would be needed to draw definitive conclusions about any specific case. I revise the cross-validation discussion to separate the A. Jafari case: I retain it in the perturbation ratio pool to be conservative (the WoS-to-OA ratio is the most adverse cross-database comparison observed), but I note that the OA–Scopus agreement suggests this case is more likely a WoS coverage difference than an OA error, and that my labeling of it as a "disambiguation failure" was premature without publication-level evidence.

**(b) Additional Monte Carlo scenarios.** I add two new scenarios (50 trials × 7 error rates each):

- *Directional inflation-only*: all flagged authors are inflated (no deflation). Substantially more destructive at moderate p: top-20 institution overlap falls to 55% at p=5% (vs 77% bidirectional); Wageningen's Ag&Bio lead is displaced in all 50 trials at p=5% (vs 37/50 bidirectional); CMU's CS lead holds in only 2/50 at p=5% (vs 47/50). At p=13% the two scenarios converge (44% vs 47% top-20 overlap) because both are near their minimum.

- *Threshold-concentrated*: only authors with h₁ within ±5 of their institution's baseline h₂ are eligible for perturbation (bidirectional for those flagged). Counterintuitively more stable than the baseline: top-20 overlap stays ≥95% across all tested rates; all three field-leadership claims hold in 47–50/50 trials through p=40%. Threshold-straddling errors in a random bidirectional model still cancel across competing institutions; concentrated unidirectional errors at a single institution's threshold, outside this model, would be more damaging.

I clarify in the Methodology that the perturbation model holds roster membership fixed (actual merges and splits can also move authors between institutions) and note this as a limitation.

**(c) Country-stratified multiplier.** I add a uniform (non-stratified) scenario: bidirectional perturbation with the same base rate p applied to all authors, without the 3× multiplier for CN/KR/IR/SA. At p=13%, top-20 overlap rises to 87% (vs 47% stratified); Wageningen holds rank 1 in all 50 trials and CMU in 47/50. The heightened sensitivity in the stratified results is driven almost entirely by the 3× multiplier applied to Wageningen's Chinese competitors in Agricultural and Biological Sciences.

**(d) Tie handling.** I add a sentence specifying that ties in h₁ among authors within an institution are handled via `ROW_NUMBER() OVER (PARTITION BY institution ORDER BY h_index DESC, author_id ASC)`, breaking ties deterministically by author ID. This is applied identically in both the baseline and perturbed rankings.

**(e) Correlation vs. headline instability.** I add a paragraph explicitly addressing this tension. The Spearman correlation at p = 13% (ρ = 0.9946) is dominated by thousands of institutions far from the top-20 where perturbations cause only minor rank shuffles. The top-20, however, consists of institutions often separated by only 1–3 h₂ points, making headline rankings sensitive to exactly the threshold-straddling errors the Monte Carlo applies. The 47% top-20 retention at p = 13% is the operationally meaningful result for anyone relying on headline rankings, and I give it appropriate weight in the conclusions. Table 13 now reports top-set overlap as mean ± SD across 50 trials; Spearman ρ values have SD < 0.001 at all rates and are reported as means only.

**Manuscript changes:** Methodology and Results updated; new Monte Carlo scenarios added; conclusion revised.

---

## Comment 6

**Reviewer:** Medicine's 24% share of the selected author pool and ranking changes after removing biomedical fields demonstrate composition sensitivity. They do not establish that the overall index is effectively a ranking of medical school size, nor that institutions without a large medical school can never reach the top. The manuscript's own Antwerp result illustrates strong non-biomedical performance. Please quantify biomedical representation in each institution's h₂ core, compare with biomedical headcounts, and test field-balanced or field-normalized alternatives before making this stronger claim. Field-specific h₂ still uses each researcher's full-career h₁ rather than citations to work within the assigned field. It measures the concentration of researchers assigned to a field who have high overall h-indices, with possible influence from other fields. Make this interpretation explicit. Similarly, Gini coefficients computed on h₂ describe inequality in that compressed index, not directly inequality in research output or impact. Specify whether institutions with no authors in a field are excluded. The lower correlation of ε₂ with SCImago's composite ranking neither validates nor invalidates normalization, as the conclusion partly acknowledges; validation should target the intended construct and report matching coverage and selection effects.

**Response:**

**(a) Softening the "implicit biomedical ranking" claim.** The reviewer is correct that Antwerp's simultaneous #3 overall and #1 non-biomedical position disproves the strongest form of this claim. I revise the framing: the overall ranking is *substantially shaped by* biomedical field representation. I remove the "is, in substance" equivalence language. A field-balanced or field-normalized alternative index is a natural extension I flag as future work.

**(b) Field-specific h₂ interpretation.** I add an explicit note at first use.

**(c) Gini coefficient interpretation.** I add a clarifying sentence. The Gini coefficient measures inequality in the distribution of integer-valued h₂ scores across institutions within a field, not directly inequality in research output or citation impact. Institutions with no authors assigned to a field are excluded from that field's Gini computation.

**(d) SIR correlation framing.** I strengthen the existing disclaimer: the lower ε₂–SIR correlation neither validates nor invalidates the size adjustment; SIR's composite rewards scale-correlated factors that raw h₂ partially captures and that dividing out size removes by construction.

**Manuscript changes:** Methodology and the Conclusion updated.

---

## Comment 7

**Reviewer:** Minor comments:
* Correct the definition in Section 2.3. The index is the largest n for which at least n members have values of at least n; the remaining members need not all have values below n. For values 5, 4, 4, 4, 4, the h-index is 4 although the fifth value is also 4. Specify a zero return for an empty admissible set and use sequential row numbers, with deterministic tie handling, in the SQL implementation.
* Reconcile the 288,300 institution-field pairs in Section 2.4 with the baseline of 229,309 in Section 3.4. Section 3.5 reports 2,858,984 multiply affiliated authors as 18.0% of 13.3 million, whereas that ratio is about 21.5%; clarify the population and denominator.
* Reconcile institutional values across tables. Caltech has overall h₂ = 94 in Table 6 but 93 in Table 9; Adelaide has 88 in Table 6 but 91 in Table 9. A change in the eligible institution subset should not alter an institution's h₂ when its author roster is unchanged.
* Correct Section 3.11's 151 eligible countries versus n = 150 in Table 11, the text placing France eighth in efficiency while Table 11 places it ninth, and the claim that Germany, the UK, and France are the only countries in both top tens, although Italy, Australia, and Spain also qualify, and the statement that the US has nearly eight times China's institution count: 3,652/1,071 is about 3.4. More generally, regenerate prose and tables from one consistent output.
* Distinguish top-10 placements from rank-one field leadership in Section 3.8. Stanford's 13 top-10 placements and UCL's eight do not mean that they lead that many fields outright. Explain tie policies consistently across ranks, breadth counts, top-set overlaps, and leader counts.
* Provide exact extraction dates and frozen snapshot identifiers for authors, works, and institutions, along with the code commit and environment. Daily updated inputs alone are insufficient for reproducing the reported numerical rankings. Include a flow diagram or table showing exclusions and joins, and report how the h₁ > 0 filter changes the headcount denominator.
* Remove or qualify speculative claims attributing a country's score to purchased secondary affiliations unless the analyzed records provide supporting evidence under the default primary-institution rule. Distinguish historical reports from findings established by this dataset.

**Response:**

I accept all corrections.

**(a) h-index definition.** The algorithm in the Methodology is already correct and handles ties at the boundary (e.g., 5,4,4,4,4 → h = 4) properly. The Schubert (2007) prose in the Introduction overstates the condition by requiring the remaining members to have values *strictly below* n; I improve the prose before the algorithm and add a note clarifying that only the lower bound (≥ n members have value ≥ n) is required. I also add: the algorithm returns 0 for an empty group or a group where no member satisfies v(m) ≥ 1. The SQL implementation uses `ROW_NUMBER() OVER (PARTITION BY group ORDER BY h_index DESC, author_id ASC)` for deterministic sequential row numbers with tie-breaking by author ID.

**(b) 288,300 vs. 229,309; denominator for 18.0%.** I verified in the underlying data: the field-specific h₂ CSV contains 229,309 (institution, field) pairs and is now corrected.

For the multiply-affiliated percentage: 2,858,984 / 13,311,757 = 21.5%, not 18.0%. The 18.0% figure is correct but refers to a different denominator. I correct the text to specify: "18.0% of the 15.9 million authors with a works-based primary institution assigned" rather than "18.0% of 13.3 million."

**(c) Caltech and Adelaide.** The correct values from the underlying data are Caltech h₂ = 93 and Adelaide h₂ = 91. I have corrected all tables.

**(d) Country-level numerical errors.** Corrected:
- *151 → 150*: countries with ≥ 5 qualifying institutions.
- *France rank*: France is 9th in efficiency, not 8th.
- *"Only Germany, UK, France"*: Italy (efficiency rank 1), Australia (rank 2), and Spain (rank 3) also appear in both top-10 lists.
- *US vs. China*: 3,652 / 1,071 ≈ 3.4.

**(e) Top-10 placements vs. field leadership.** I revise to "Stanford places in the top 10 in 13 of 26 fields" and explicitly distinguish top-10 placements from outright field leadership (rank 1). The same correction applies to UCL.

**(f) Extraction dates and reproducibility.** I add the exact OpenAlex snapshot identifiers (authors and works partitions through 2026-06-26, both from `s3://openalex/data/parquet/`) and the git commit hash (`e8f0671`) to the Methodology. I add Table~1 (data-flow) showing the two independent processing streams.

**(g) Saudi Arabia.** I replace causal language with: "this dataset cannot independently confirm or quantify that mechanism under the primary-affiliation rule used here."

**Manuscript changes:** All seven corrections applied throughout.