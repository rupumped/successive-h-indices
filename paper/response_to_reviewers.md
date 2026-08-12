# Response to Reviewers

Paper: "Successive h-indices using OpenAlex"

For each comment: reviewer's point, our response, and where/how the manuscript changed (file + line/section). Manuscript changes are marked in the LaTeX source with `\textcolor{red}{...}`.

---

## Comment 1: Reliability of the underlying author-level data (h2/h3 validity given OpenAlex disambiguation errors)

**Reviewer:** The manual validation of only 19 authors is not sufficient to establish the reliability of a dataset containing more than 17 million researchers; the reported discrepancies (e.g., Lei Jiang 215 vs. WoS 115; Donald Small 103 vs. Scopus 57) show that disambiguation errors can substantially influence institutional and national rankings, which aggregate author-level h-index values.

**Response:** We agree that a hand sample, however chosen, cannot by itself establish the reliability of a 17.1-million-author dataset — this was true of the original 19-author sample and would have been equally true of a larger one, since the sample is deliberately adversarial (chosen to find errors, not to estimate their population-wide rate). We made three substantive additions:

1. **Reframed the manual cross-validation** as an explicit bound on the *type and locus* of error (which authors, by how much) rather than an estimate of its population-wide *rate*, and added two independent, larger-scale, systematic studies that corroborate the same failure pattern (disambiguation precision concentrated in common-name and non-Anglophone strata): Zhao & Chen (2025), a 2,700-scholar benchmark, and OpenAlex's own account of an ongoing correction effort for exactly this kind of over-merging (Demes, 2026).
2. **Added a new Monte Carlo sensitivity analysis** (new Subsections "Sensitivity to disambiguation error" in Methodology and Results) that directly quantifies the reviewer's concern: we inject synthetic disambiguation-style errors into the full 17.1M-author dataset, at the same magnitude observed in the cross-validation outliers, at six population-wide rates spanning 1% to a deliberately implausible 80% (rather than asserting any single rate as a "worst case" — the cross-validation sample's own raw outlier rate, 4/19 ≈ 21%, is just one noisy 19-author draw, not a principled bound, and is included in the table only for reference), and recompute all headline rankings at each rate. Result: institution- and country-level rank correlations decline only modestly (Spearman ρ from 0.999 at 1% down to 0.988) and then *plateau* rather than continuing toward zero, all the way out to 80% — a consequence of h₂/h₃ being order statistics with a bounded per-author perturbation, so there is no error rate in this model, however extreme, at which the aggregate rankings collapse. The field-leadership claims (Wageningen, Carnegie Mellon) are noisier at every rate (surviving 3–5 of 5 trials with no trend as the rate rises) and are flagged as more fragile than the paper's other claims.
3. **Generated 11 additional cross-validation candidates**, disjoint from the original 19 by institution (Stanford, MIT, Cambridge, Yale, Tsinghua, Cairo, Tehran, plus the global 6th-highest h₁), using the same targeted sampling scheme (threshold authors, weak-coverage fields, non-Anglophone institutions, global top sanity check). *[Open item, flagged to author: the candidate list is generated (`src/cross_validation_sample_wave2.py` → `results/cross_validation_sample_wave2.csv`), but the actual Web of Science/Scopus/Google Scholar lookups require manual/subscription access neither of us has in this Claude Code session — these still need to be done by hand before Table `tab:crossval` and the surrounding text can be updated with a 30-author total.]*

**Manuscript changes:**
- `paper/sections/method.tex`: reframed the cross-validation description (end of `subsec:methods-crossval`) as adversarial-not-representative; added new subsection `subsec:methods-sensitivity` ("Sensitivity to disambiguation error") describing the six-rate Monte Carlo perturbation methodology.
- `paper/sections/results.tex`: added a paragraph after the four-outlier discussion citing `zhao2025` and `demes2026` and pointing to the new sensitivity subsection; added new subsection `subsec:results-sensitivity` with Table `tab:sensitivity` (Spearman ρ, top-set overlap, and field-leader survival rate across p = 1%–80%) and interpretive text explaining the plateau.
- `paper/sections/conc.tex`: added a sentence to the limitations paragraph summarizing the sensitivity analysis (plateau finding, field-leadership caveat).
- `paper/references.bib`: added `zhao2025` (Zhao & Chen, 2025, arXiv:2502.11610) and `demes2026` (OpenAlex blog, 2026).
- New analysis scripts: `src/sensitivity_disambiguation.py`, `src/cross_validation_sample_wave2.py`; raw output: `results/sensitivity_disambiguation.csv`, `results/sensitivity_disambiguation.log`, `results/cross_validation_sample_wave2.csv`.

**Still needed from the author before this comment can be marked fully resolved:** hand-check the 11 wave-2 candidates against Web of Science, Scopus, and Google Scholar (see table below), then fold the results into Table `tab:crossval` and the surrounding prose (19 → 30 authors, updated outlier count/rate).

| # | Bucket | Institution | Name | OpenAlex h₁ | Why sampled |
|---|---|---|---|---|---|
| 1 | Threshold @ top institution | Stanford | W. James Nelson | 108 | sits at H2=107 threshold |
| 2 | Threshold @ top institution | Stanford | Serpil C. Erzurum | 108 | sits at H2=107 threshold |
| 3 | Threshold @ top institution | MIT | James M. Poterba | 94 | sits at H2=94 threshold |
| 4 | Weak-coverage field | Cambridge / Arts & Humanities | D. H. Mellor | 28 | sits at H2=28 threshold |
| 5 | Weak-coverage field | Cambridge / Arts & Humanities | James Raven | 24 | sits at H2=28 threshold |
| 6 | Weak-coverage field | Yale / Social Sciences | Nicholas Sambanis | 39 | sits at H2=39 threshold |
| 7 | Non-Anglophone institution | Tsinghua | Tien Yin Wong | 208 | top h₁ at institution |
| 8 | Non-Anglophone institution | Tsinghua | Dingsheng Wang | 175 | top h₁ at institution |
| 9 | Non-Anglophone institution | Cairo | B. De La Cruz | 141 | top h₁ at institution (scattered affiliation history — check first) |
| 10 | Non-Anglophone institution | Tehran | A. Fahim | 122 | top h₁ at institution (scattered affiliation history — check first) |
| 11 | Global top h₁ (sanity check) | Osaka Int'l University | Shizuo Akira | 271 | 6th-highest h₁ globally |

---

