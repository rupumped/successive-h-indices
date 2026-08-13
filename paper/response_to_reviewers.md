# Response to Reviewers

For each comment: reviewer's point, my response, and where/how the manuscript changed. Manuscript additions are marked in red font.

## Reviewer 1

### Comment 1.1

**Reviewer:** Although the manuscript presents an ambitious computational analysis, the main conclusions are not sufficiently supported because the proposed indicators depend on several strong assumptions about data quality, author identification, institutional attribution, and disciplinary classification. The limitations discussed by the authors are not minor issues; they directly affect the validity of the rankings and conclusions presented. The most serious concern is the reliability of the underlying author-level data. The calculation of h2 and h3 depends entirely on the accuracy of OpenAlex author h-indices. The manuscript reports substantial disagreements between OpenAlex and other databases, including cases where OpenAlex values are much higher than Web of Science or Scopus values. For example, the paper reports a large discrepancy for Lei Jiang, whose OpenAlex h-index is 215 compared with 115 in Web of Science, and for Donald Small, whose OpenAlex h-index is 103 compared with 57 in Scopus. These examples indicate that author disambiguation errors can substantially influence the results. Since the successive h-index aggregates author-level values, even a small number of incorrect author profiles can have a large impact on institutional and national rankings. The manual validation of only 19 authors is not sufficient to establish the reliability of a dataset containing more than 17 million researchers.

**Response:** I agree that a hand sample, however chosen, cannot by itself establish the reliability of a 17.1-million-author dataset. This was true of the original 19-author sample and is equally true of a larger one, since the sample is deliberately adversarial (chosen to find errors, not to estimate their population-wide rate). I made three substantive additions:

1. **Reframed the manual cross-validation** as an explicit bound on the *type and locus* of error (which authors, by how much) rather than an estimate of its population-wide *rate*, and added two independent, larger-scale, systematic studies that corroborate the same failure pattern: Zhao & Chen (2025) and OpenAlex's own account of an ongoing correction effort for exactly this kind of over-merging (Demes, 2026).
2. **Completed additional manual cross-validation** of 11 additional authors using the same adversarial selection technique. The results are broadly identical. The outlier count remains **4 of 30 (13%)**. Table 1 and the surrounding prose have been updated to reflect the 30-author total.
3. **Added a new Monte Carlo sensitivity analysis** (new Subsections "Sensitivity to disambiguation error" in Methodology and Results) that directly quantifies the reviewer's concern: I inject synthetic disambiguation-style errors into the full 17.1M-author dataset, at the same magnitude observed in the cross-validation outliers, at six population-wide rates spanning 1% to a deliberately implausible 80%, and recompute all headline rankings at each rate. Result: institution- and country-level rank correlations decline modestly and then plateau. The field-leadership claims (Wageningen, Carnegie Mellon) are noisier and are flagged as more fragile than the paper's other claims.

**Manuscript changes:**
- Subsections 2.8 and 2.9: reframed the cross-validation description as adversarial-not-representative; added new subsection "Sensitivity to disambiguation error" describing the Monte Carlo perturbation methodology.
- Subsections 3.1 and 3.11: updated opening sentence to reflect 30-author total; revised coverage counts; updated Table 1 aggregate statistics; updated outlier-rate; expanded Arts & Humanities paragraph; added paragraph citing Zhao & Chen (2025) and Demes (2026); added new subsection "Sensitivity to disambiguation error" with Table 11 and interpretive text.
- Conlcusion: added sentence summarizing the sensitivity analysis (plateau finding, field-leadership caveat).
- References: added Zhao & Chen (2025) and Demes (2026).

---

### Comment 1.2

**Reviewer:** A second major problem concerns the assignment of researchers to institutions and fields. The manuscript assigns each researcher to only one institution based on the most recent affiliation and assigns each researcher to a single field based on the dominant OpenAlex topic classification. This approach oversimplifies modern research careers. Many researchers have multiple affiliations, move between institutions, and publish across several disciplines. Assigning all historical research impact to the most recent institution may produce misleading institutional comparisons because it does not necessarily represent where the research was conducted or where the scholarly contribution originated. Similarly, forcing multidisciplinary researchers into one field may distort field-level rankings. The paper would need a much stronger justification for these allocation decisions. At minimum, the authors should examine whether the results remain stable under alternative approaches, such as fractional affiliation counting, publication-level attribution, or multiple-field assignment. Without such analyses, it is unclear whether the reported rankings reflect genuine institutional performance or methodological choices.

**Response:** I agree that both choices are simplifications that warrant explicit robustness testing. I ran the most tractable of the three suggested alternatives, multi-field assignment, and report its results here. I defer publication-level attribution (which would require per-paper affiliation data not consistently recorded in the OpenAlex works snapshot) and fractional affiliation counting (which requires redefining h2 over a weighted roster) to future work, given that the multi-field result already characterises the key sensitivity.

At a threshold τ, each author is included in every field for which their OpenAlex topic-weight share is at least τ. I tested τ at 20% at 33%. The overall field ranking structure is highly stable at 33% (ρ = 0.963) and stable at 20% (ρ = 0.907), but the multi-field assignment technique seems to benefit large, comprehensive universities over smaller, more specialized institutes.

**Manuscript changes:**
- Subsection 2.10: new subsection "Robustness to field assignment" describing the two-threshold multi-field re-assignment and h2 recomputation.
- Subsection 3.4: new subsection "Robustness of field-specific rankings to multi-field assignment" reporting ρ and changed-leader counts with mechanistic explanation.
- Conclusion: updated affirmative claims to flag their conditionality; added a sentence to the limitations paragraph summarising the field-robustness finding.

---

### Comment 1.3

**Reviewer:** The interpretation of the successive h-index as a measure of institutional or national research strength is also problematic. The manuscript shows that institution size explains approximately 91% of the variation in h2, while the number of institutions explains approximately 92% of the variation in h3. This finding suggests that the indicators are primarily measuring scale rather than research excellence. The proposed efficiency measures attempt to correct for this effect, but the normalization procedure is not sufficiently validated. The manuscript does not demonstrate that these efficiency measures provide information beyond existing field-normalized bibliometric indicators.

**Response:** I agree that external validation strengthens the case for the efficiency metrics. I compare both raw h2 and ε2 against the CWTS Leiden Ranking Open Edition 2024. The Leiden Open Edition's mean normalised citation score (MNCS) is a standard, well-validated measure of field- and time-normalised citation impact; crucially, it is already size-independent by construction (it is a mean, not a total), making it the natural external reference for ε2. I compute Spearman rank correlations between the Leiden MNCS ranking and (a) my raw h₂ ranking and (b) my ε₂ ranking. Both correlations are highly significant. Taken together, the results validate both metrics against an established external standard and establish that the normalisation does what it claims to do.

**Manuscript changes:**
- Subsectin 2.11: new subsection "External validation against the Leiden Ranking" describing the Leiden MNCS extraction and Spearman correlation methodology.
- Subsection 3.8: new subsubsection within "Institution efficiency" reporting correlations with mechanistic interpretation.
- References: added CWTS Leiden Ranking Open Edition (2024).

---

### Comment 1.4

**Reviewer:** The theoretical discussion of the Lotkaian scaling framework also requires further consideration. The manuscript applies Egghe’s model to explain the relationship between different levels of aggregation but reports that the predicted relationships fail substantially. The paper notes that the theoretical prediction differs from the observed values by 177% for one relationship and 97% for another. These are not small deviations. If the theoretical assumptions do not hold, the manuscript needs to provide a stronger explanation of why the resulting efficiency indicators remain meaningful.

**Response:** I agree the discrepancy is large and that the one-line dismissal in the original manuscript ("the model is empirically useful; the underlying theory needs a different reading") was insufficient. The revision makes the following distinction explicit in the results.

Egghe's framework contributes two logically separate claims to this paper:
1. h2 ~ S^(1/β1): this is an empirical observation, confirmed here with R² = 0.911. It does not depend on the compounding formula.
2. β1 = α0α1: this is a theoretical prediction about the relationship between separately-fitted exponents. It is tested in the paper and fails badly.

The efficiency metric ε2 uses only claim (1). β1 is estimated directly from the distribution of h1 values across authors via discrete MLE, not derived from α0α1, so the 177% discrepancy in the compounding formula has no bearing on the exponent actually used in ε2.

The external validation against the Leiden Ranking (added in response to Comment 3) provides an independent empirical confirmation.

**Manuscript changes:**
- Subsection 3.8: the "Model Validation" and "External validation against the Leiden Ranking" subsubsection makes the two-layer distinction explicit and connects to the Leiden validation.

---

### Comment 1.5

**Reviewer:** Another concern is the reliance on OpenAlex field classifications. Many of the paper’s main conclusions depend on comparisons between disciplines and countries, yet the accuracy of OpenAlex topic assignments is not sufficiently examined. This is particularly important because coverage and classification quality vary across disciplines. The manuscript acknowledges that Arts and Humanities have weaker coverage but still presents broad field-level comparisons across 26 areas. The authors should provide evidence that the field classification method is sufficiently accurate for these comparisons.

**Response:** The concern is legitimate at the granular topic level but is substantially mitigated by two structural features of the paper's methodology, which I now state explicitly in the "Author-level assignment" subsection.

1. OpenAlex's topic classifier fine-tunes a multilingual BERT model on title, abstract, and citation data and achieves a top-1 accuracy of 0.72 when full metadata is available, and 0.53 on average, at the topic level (~4,500 topics). However, the paper operates at the *field* level (26 fields). Many topic-level misclassifications stay within the same parent field. For example, a paper incorrectly assigned from "Deep Learning" to "Computer Vision" still contributes correctly to Computer Science, so field-level accuracy is substantially higher than the topic-level figures suggest. No formal field-level accuracy evaluation of OpenAlex's classifier has been published, and I say so; but the coarseness of the classification is itself an argument for robustness.
2. Each author's field is the mode of their entire publication record, weighted by topic counts across all works. A researcher would need a substantial fraction of their career output systematically misclassified to a different field before their field assignment would change. Isolated misclassifications of individual papers are effectively diluted.

What the paper genuinely cannot rule out is that a handful of authors near an institution's h2 threshold are misclassified to the wrong field, mildly deflating or inflating a field-specific h2. This is unknowable without ground truth, and I say so. The multi-field robustness analysis (Comment 1.2) provides indirect evidence that the classification is stable.

**Manuscript changes:**
- Subsection 2.2: new paragraph at the end of "Author-level assignment" explaining the two structural buffers against classification error (field-level coarseness and modal assignment), citing OpenAlex (2024), and noting Arts and Humanities as the most vulnerable case.
- References: added OpenAlex's whitepaper on the subject.

---

### Comment 1.6

**Reviewer:** The "Academic Olympics" analysis is an interesting visualization, but its scientific contribution is limited. Ranking countries by medals based on the top three h3 values in each field creates an artificial competition structure that may exaggerate differences between countries. Such rankings are highly influenced by database coverage, institutional size, language effects, and historical research investment. The results should not be interpreted as a direct measure of national scientific performance.

**Response:** I agree. The Academic Olympics section has been removed from the manuscript in its entirety.

**Manuscript changes:**
- Abstract, Methods, Results, and Conclusion: Academic Olympics subsection removed.

---

### Comment 1.7

**Reviewer:** The manuscript also tends to make conclusions stronger than the evidence allows. For example, statements about national leadership in specific fields and institutional superiority should be presented more cautiously because they are based on indicators with substantial uncertainty. The paper demonstrates that successive h-indices can reveal patterns in large bibliometric datasets, but it does not demonstrate that they provide reliable rankings of research excellence.

**Response:** I agree, and have moderated the language throughout.

**Manuscript changes:**
- Results and Conclusion: softened "single strongest research group on Earth", "leads X outright", and "world's six deepest" to "rank first globally by this measure", "ranks first in X by field h₂", and "among the top six globally by this measure" respectively.

---

## Reviewer 2

### Comment 2.1

**Reviewer:** The paper is original. It presents an interesting application of the concept of successive h-indices. Overall, I consider that it meets the quality criteria required for publication in “Scientometrics” and merits publication.
The authors might consider adding background information on successive h-indices (particularly an idea previously proposed by the Indian researcher Gangan Prathap) to the introduction in order to enrich the literature review on the topic.
I suggest reviewing the following references:
Prathap, G. (2006). Hirsch-type indices for ranking institutions’ scientific research output. Current Science, 91 : 1439.
Arencibia-Jorge, R., & Rousseau, R. (2009). Influence of individual researchers’ visibility on institutional impact: an example of Prathap’s approach to successive h-indices. Scientometrics, 79(3), 507-516.
Otherwise, I believe the paper is well-crafted. 

**Response:** I thank Reviewer 2 for this pointer. Prathap (2006) independently proposed applying the h-index hierarchically at the researcher-institution level in a brief note in *Current Science* dated 10 December 2006, less than one month before Schubert's paper appeared. This near-simultaneous independent discovery speaks to how ready the field was for this step. I was not previously aware of this work and are grateful for the correction.

Having read both papers carefully, I note that Prathap's contribution and Schubert's are complementary but distinct. Prathap stops at h2: his note does not discuss the possibility of applying the construction recursively to obtain h3 at a still higher level of aggregation. Schubert's distinctive contribution recognizes that the hierarchy extends to an arbitrary succession of levels and thereby opening the path to h3 and beyond. The present paper relies on that extension.

I have revised the introduction accordingly. The new text credits Prathap as an independent near-simultaneous proposer of h2 at the researcher-institution level, states Schubert's distinctive contribution clearly, and cites Arencibia-Jorge & Rousseau (2009), which the reviewer's note led us to, as a case study that explicitly applies Prathap's framing.

**Manuscript changes:**
- Introduction: new sentence in the "modest but sustained attention" paragraph crediting Prathap (2006) as an independent proposer of h2; "Two case studies" changed to "Several case studies"; added Arencibia-Jorge & Rousseau (2009) as a third case study applying Prathap's framing to Cuban brain-research institutions.
- References: added Prathap (2006) and Arencibia-Jorge & Rousseau, (2009).

---

### Comment 2.2

**Reviewer:** Otherwise, I believe the paper is well-crafted. I found the "Olympic-style table" unnecessary, as it represents yet another way to undermine the true purpose of research assessment. It is just one more ranking that fosters competitiveness (values not aligned with a tool like OpenAlex) at a time when the focus is shifting toward the social impact of research rather than spurious metrics; thus, I consider it a futile addition. However, given that the Olympic-style table so clearly illustrates the vast gap between developed nations and the rest of the world, I acknowledge that its inclusion in the paper is not without merit. My overall assessment is positive. I recommend that the paper be published.

**Response:** The Academic Olympics section has been removed from the manuscript in its entirety. I am grateful for the reviewer's positive overall assessment and recommendation to publish.

**Manuscript changes:**
- Abstract, Methods, Results, and Conclusion: Academic Olympics subsection removed.