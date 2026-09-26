# Reviewer comment

The revised manuscript has added several analyses in response to the reviewers, including a larger manual cross-validation exercise, a Monte Carlo sensitivity analysis, multi-field assignment checks, and a comparison with the CWTS Leiden Ranking. I appreciate the effort invested in the revision. However, the new analyses do not resolve my principal concern: the reported rankings cannot be interpreted as valid measures of institutional or national research performance. The central problems concern construct validity and attribution, not merely statistical robustness. In several places, the revision now makes stronger claims than the added evidence supports.

1. The institutional-attribution problem remains unresolved

The manuscript assigns each researcher’s entire career h-index to one institution—specifically, the most recent educational affiliation recorded by OpenAlex. Consequently, citations to work produced over an entire career are credited to the researcher’s latest institution, regardless of where that work was conducted.

This is not a secondary limitation. It defines the institutional h2 values and, through them, the national h3 values. The response acknowledges the issue but does not test any alternative institutional-attribution method. Instead, the authors conduct a multi-field assignment analysis. That analysis addresses disciplinary classification but says nothing about whether institutional and country rankings are stable under more defensible affiliation rules.

The argument that publication-level attribution is impractical does not validate the chosen approach. At minimum, the authors could examine a restricted publication window, researchers with stable affiliations, fractional treatment of multiple current affiliations, or a subset for which work-level affiliation histories are sufficiently complete. Without such evidence, the results describe the current locations of researchers carrying accumulated career h-indices, not the research performance of the institutions or countries to which those indices are assigned. This distinction is especially serious for internationally mobile and multiply affiliated researchers.

2. The Monte Carlo analysis does not simulate the main data-generating errors

The new sensitivity analysis randomly selects authors and multiplies their h-indices by ratios drawn from four manually identified outliers. This design is insufficient for several reasons.

First, author-disambiguation errors are unlikely to be independent and identically distributed. The manuscript itself states that they are concentrated among common names, non-Anglophone researchers, and particular countries. An independent uniform perturbation therefore removes precisely the institutional, linguistic, and geographic clustering that could create systematic ranking bias.

Second, the simulation represents only upward inflation. Real disambiguation problems include both merges and splits, missing works, erroneous affiliations, duplicate profiles, and incorrect assignment of works between researchers. These processes can raise or lower an author’s h-index and need not resemble multiplication by one of four ratios.

Third, the analysis adds synthetic error to a baseline already known to contain unknown error. Similarity between a perturbed ranking and the contaminated baseline is not evidence of similarity to the unknown true ranking.

Fourth, the reported plateau at high perturbation rates is partly a consequence of applying similar positive inflation to competitors throughout the dataset. Such cancellation is built into the perturbation design and cannot establish robustness to concentrated or directional bias. The top-20 institutional overlap also falls to 78% at the 10% and 13% rates, which is not negligible for a paper centered on rankings.

Finally, five trials per condition are too few to characterize uncertainty, particularly for the field-leadership results. The non-monotonic survival rates in Table 11—for example, leadership claims becoming more stable again at 40% or 80% error—illustrate the instability and artificial character of the exercise.

The conclusion that the risks are “bounded rather than fatal” and that the rankings are robust “at every rate tested” is therefore not warranted.

3. The external validation is neither independent nor supportive of the efficiency claim

The manuscript describes the Leiden Ranking comparison as an “independent” validation, but the Leiden Ranking Open Edition used here is itself based on OpenAlex. The two measures therefore share source coverage, author-work links, institutional identifiers, affiliation errors, and citation data. This is convergent comparison within the same underlying data infrastructure, not independent external validation.

More importantly, raw h2 correlates more strongly with MNCS (ρ = 0.634) than the proposed efficiency measure does (ρ = 0.580). These results do not demonstrate that the normalization improves the measurement of research quality or adds information beyond an existing field-normalized indicator. Statistical significance is unsurprising with 1,495 observations and is not the relevant criterion. The manuscript would need to show incremental validity—for example, through partial correlations controlling for size, comparisons of explanatory or predictive performance, or tests against genuinely external measures.

The efficiency tables themselves raise additional validity concerns. Several highly ranked institutions are community colleges or other organizations for which the reported author counts and h2 values appear implausible. These cases require direct validation rather than being presented as substantive findings. They may reflect the same historical-affiliation and author-disambiguation problems that motivated the original review.

Accordingly, the statement that the comparison demonstrates “genuine differences in research excellence rather than differences in institutional size” should be removed. The evidence does not support that inference.

4. Field-classification validity remains assumed rather than demonstrated

The manuscript cites topic-level classifier accuracy and then asserts that field-level accuracy is “substantially higher” because some topic errors remain within a parent field. This is plausible, but no field-level validation is presented, and the manuscript acknowledges that no formal evaluation is available. Plausibility should not be stated as an empirical result.

The multi-field analysis tests an alternative allocation rule using the same underlying OpenAlex classifications; it does not test whether those classifications are correct. Moreover, the substantive leaders are not fully robust: only 18 of 27 field leaders remain unchanged at the 20% threshold, while the Wageningen Environmental Science and Carnegie Mellon Computer Science conclusions change under alternative specifications. These are prominent findings in the abstract and conclusion. The results therefore demonstrate meaningful specification dependence, not merely minor noise.

5. The indicators remain dominated by scale, while the interpretation continues to invoke excellence

The manuscript reports that size accounts for approximately 91% of institutional h2 variation and that institution count accounts for approximately 92% of country h3 variation. This confirms that the raw indicators primarily measure scale. The proposed efficiency normalization is based on an empirical power-law relationship, but its theoretical compounding foundation fails by 177% and 97%, and the external comparison does not validate the normalization as a superior measure of quality.

Despite acknowledging these problems, the manuscript continues to use expressions such as “global research strength,” “research depth,” “high-quality research systems,” and “genuine differences in research excellence.” These interpretations exceed what has been established. At most, the study documents patterns in successive h-indices computed from a particular OpenAlex snapshot under specific author, affiliation, and field-allocation rules.

6. The country rankings inherit and compound the attribution problem

The h3 calculation assigns institutional h2 values to countries using current OpenAlex institutional locations. Because each institutional h2 already attributes researchers’ accumulated career impact to their most recent institution, international mobility and secondary affiliations can reallocate historical research impact across countries. The manuscript itself identifies Saudi Arabia as an apparent example of this distortion, yet continues to interpret other country efficiency rankings substantively.

Once a known artifact can elevate a country to fourth place in the efficiency ranking, the validity of the entire country comparison requires systematic investigation. It is not sufficient to label one conspicuous case as a limitation while treating the remaining rankings as genuine research-system differences.

7. Internal inconsistencies indicate that the revised dataset and analyses have not been adequately reconciled

The manuscript contains several material inconsistencies:

* Section 2 reports 17.1 million retained authors and 20,669 institutions, whereas Section 3.2 reports 30.0 million authors and 20,932 institutions.
* The abstract states that Medicine accounts for 44% of the author pool, while the conclusion states 25%.
* Section 3.2 says the ranking uses the institutions and authors “described in Section 2,” although the reported totals do not agree.
* The manuscript refers to “26 fields” in the methodology but reports leaders for 27 fields in the robustness analysis.
* The conclusion states that “institution count alone” explains variation in h2, although institutional h2 is modeled using author count; institution count is used for h3.
* Table and figure numbering appears inconsistent around the country-level results.

# Plan to address
The reviewer raises concerns across two categories: (A) fixable text/claim issues requiring no new analysis, and (B) issues requiring new analysis or additional data work. Address in four tiers. Every edit made in the paper text should be encompassed in `\textcolor{red}{}` to indicate edits.

## Tier 1 — Fix Internal Inconsistencies First (Issue 7)
These are factual errors that undermine credibility and must be resolved before anything else. They're all text-only fixes, but some require reconciling against the actual computed data first.

### 7a. Author/institution count discrepancy — most critical
The methods section says 17.1M authors / 20,669 institutions; the results section says 30.0M / 20,932. The results tables are clearly based on 30.0M, so the methods section (and abstract) need to be updated. The filters described in Section 2 must be checked against the actual pipeline to explain the discrepancy.

### 7b. Medicine percentage
Abstract says 44%; the results compute 7.58M / 30.0M = 25.3%. Confirm using the data, then fix.

### 7c. 26 vs 27 fields
The Gini table has 26 rows; the robustness section reports 27 field leaders. One of these is wrong. Confirm from the data. Fix whichever is the error.

### 7d. "Institution count alone" explains h2
The conclusion says institution count explains h2 variance, but the actual model uses author count (S) for h2 and institution count (R) for h3. Fix to be precise: "author count explains 91% of h2 variance; institution count explains 92% of h3 variance."

### 7e. Table/figure numbering
Audit all cross-references in the country-level results section.

## Tier 2 — Recalibrate Claims (Issues 1, 3, 4, 5, 6)
These require text revisions but no new analysis. The core move is narrowing what the paper claims to measure.

### Reframe scope throughout (Issues 1, 5, 6)
The paper should describe itself as computing successive h-indices from OpenAlex under specific attribution rules, not as measuring institutional research performance. Everywhere the paper says "research strength," "research excellence," or "research performance," replace with language that accurately describes what's computed: "concentration of highly-cited researchers as recorded in OpenAlex under current affiliation." Add one clear sentence in the abstract stating that institutional rankings reflect current researcher concentrations, not historical research production.

### Remove "independent" from Leiden comparison (Issue 3)
Option A: The Leiden Open Edition uses OpenAlex as its source. Acknowledge the shared data infrastructure. Reframe as convergent validity within a shared system, not independent external validation. Also address the finding that raw h2 (ρ=0.634) outperforms ε2 (ρ=0.580) against MNCS — this needs to be explained, not glossed over. Remove the conclusion that the comparison demonstrates "genuine differences in research excellence."
Option B: find a new, actually external rankings system. I like this option better, but I don't know how to implement.

### Soften field classification language (Issue 4)
Change "field-level accuracy is substantially higher" to "plausibly higher." Clarify that the multi-field robustness analysis tests allocation sensitivity, not whether the underlying classifications are correct. The 18/27 leaders surviving at the 20% threshold demonstrates meaningful specification dependence — the conclusion and abstract claims about Wageningen Environmental Science and Carnegie Mellon CS should be conditioned accordingly.

### Consistent treatment of country outliers (Issue 6)
The paper flags Saudi Arabia as a likely artifact but then interprets other efficiency rankings substantively. We should re-analyze the data with institutionally-split h indices XXX.

## Tier 3 — New and Revised Analyses
### Revise Monte Carlo analysis (Issue 2)
The reviewer's four specific critiques are all valid:
* Increase trials from 5 to at least 50 per condition — five is too few to characterize uncertainty
* Add downward perturbations — simulate author-splitting (divide h-index by a ratio) alongside the current inflation-only design. This addresses the reviewer's point that real disambiguation errors go in both directions
* Explicitly acknowledge and explain the cancellation effect in the text — the plateau is partly a design artifact, not purely a property of the indices
* Recalibrate conclusions — remove "bounded rather than fatal" and "robust at every rate tested." Replace with honest characterization: the rankings are stable under the specific perturbation model tested, but that model cannot capture concentrated or directional bias
* Add fractional multi-affiliation check (Issue 1). How would this work though?

### Validate community college efficiency entries (Issue 3)
Manually check the top 10 efficiency institutions (at least Bellevue University, Imperial Valley College, City College of San Francisco, Frederick Community College). These entries look implausible and the reviewer explicitly flags them. If they are data artifacts (likely — authors who list community college affiliations for demographic purposes), either add an explicit data-quality caveat or add a filter criterion to require a minimum number of publications actually attributed to the institution.

## Tier 4 — Response Strategy
The reviewer's principal concern is construct validity: the paper cannot be a valid measure of institutional research performance because of the attribution method. This concern is legitimate and cannot be fully rebutted. The viable path forward is to agree with the diagnosis and reposition accordingly.

The paper's defensible contribution is:

Demonstrating Schubert's successive h-index framework at a scale that was previously impossible
Documenting structural patterns — scale dominance, field heterogeneity, the non-biomedical vs. overall ranking divergence
Computing descriptive indices that bibliometricians can use as a starting point
The paper should not claim to validate institutional research quality. It should claim to characterize bibliometric patterns.

## Order of Operations
Resolve the 17.1M vs 30.0M discrepancy by checking the actual pipeline — everything else depends on this being consistent
Fix all remaining Tier 1 inconsistencies
Draft revised scope language for abstract and conclusion (Tier 2)
Run revised Monte Carlo with 50+ trials and bidirectional perturbation (Tier 3)
Run fractional multi-affiliation check (Tier 3)
Validate community college entries (Tier 3)
Assemble revised response letter, similar to response_to_reviewers_1.md in this directory.