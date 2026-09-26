# Response to Reviewers — Round 2

> **DRAFT — IN PROGRESS.** Several of the new analyses this response describes are still running or not yet started. Sections are marked `[DONE]`, `[IN PROGRESS]`, or `[NOT STARTED]` in a note under the comment heading so it's clear what's settled and what's still provisional. Remove these status markers before final submission. For each comment: reviewer's point, my response, and where/how the manuscript changed. Manuscript additions are marked in red font.

## Reviewer 1

### Comment 1.1

*(Status: **DONE** — multi-institution tie-check complete and adopted as evidence. A second check (restricting to authors with a single lifetime institution) was also run but is not used — see note below.)*

**Reviewer:** The manuscript assigns each researcher's entire career h-index to one institution—specifically, the most recent educational affiliation recorded by OpenAlex. Consequently, citations to work produced over an entire career are credited to the researcher's latest institution, regardless of where that work was conducted. This is not a secondary limitation. It defines the institutional h2 values and, through them, the national h3 values. The response acknowledges the issue but does not test any alternative institutional-attribution method. Instead, the authors conduct a multi-field assignment analysis. That analysis addresses disciplinary classification but says nothing about whether institutional and country rankings are stable under more defensible affiliation rules. The argument that publication-level attribution is impractical does not validate the chosen approach. At minimum, the authors could examine a restricted publication window, researchers with stable affiliations, fractional treatment of multiple current affiliations, or a subset for which work-level affiliation histories are sufficiently complete. Without such evidence, the results describe the current locations of researchers carrying accumulated career h-indices, not the research performance of the institutions or countries to which those indices are assigned. This distinction is especially serious for internationally mobile and multiply affiliated researchers.

**Response:** I agree this was the most serious unresolved gap in the previous revision, and that testing an alternative institutional-attribution rule — not just field assignment — is the right way to address it. OpenAlex's per-author `affiliations` array (already pulled by the data pipeline, with a `years[]` range recorded for every institution an author has ever listed) makes two of the reviewer's suggested checks directly computable without new data collection. I ran both; I report and adopt one of them.

**Multi-institution tie-check (adopted).** This addresses the reviewer's "fractional treatment of multiple current affiliations" suggestion. Roughly 3.75 million authors (12.5% of the qualifying population) have two or more educational institutions genuinely tied for "most recent" in their OpenAlex record; the current pipeline breaks such ties arbitrarily by smallest institution ID, silently dropping the others. I re-assign each such author to *every* tied institution (the same inclusive-membership pattern the paper already uses for its multi-field robustness check, Subsection~2.10 — not a literal 1/n-weighted fractional h-index, but a sensitivity bound on how much the arbitrary tiebreak, as opposed to genuine multi-affiliation, is moving the rankings) and recompute h2 and h3. Institution-level h2 rank correlation is ρ = 0.966 (top-10 overlap 80%, top-20 overlap 70%, 20,932 shared institutions); country-level h3 is ρ = 0.997 (top-10 overlap 100%, top-20 overlap 95%). Saudi Arabia's efficiency rank is unchanged in direction (ε3 rises slightly, 6.69 → 7.50, rather than falling), so the specific tiebreak rule is not the source of that outlier. I read this as evidence that the current-affiliation *tiebreak heuristic* is a comparatively minor contributor to ranking instability — real, and worth disclosing, but not the dominant mechanism the reviewer is concerned about.

**Stable-affiliation subset (run, not adopted as evidence).** I also restricted the population to the 60.8% of authors (18.2M of 29.97M) with exactly one lifetime educational institution recorded — i.e., no career mobility to misattribute — and recomputed h2/h3 on that subset alone. The result was a large shift (institution-level top-10 overlap with baseline: 0%), but on inspection the subset is not a representative holdout: authors who never change institutions are disproportionately concentrated in academic systems with low researcher mobility (the recomputed top institutions skew heavily toward continental European universities), and a career with zero institutional moves is not typical of a modern research career generally. Using this subset as a proxy for "true" attribution would substitute one selection bias (current-affiliation attribution) for another (never-moved-authors-only attribution), so I am not using it as supporting evidence, though the underlying script (`src/stable_affiliation_check.py`) and its output remain in the repository for transparency.

I did not pursue a restricted publication window or full work-level affiliation histories: the former would require re-deriving each author's affiliation-in-force at an arbitrary cutoff year from the same `years[]` data used above, and the latter would require pulling per-work affiliation data for 30M authors from the OpenAlex works snapshot — the "impractical" objection the reviewer correctly said the previous revision leaned on without testing. Between the two checks I did run, neither fully resolves the reviewer's central point that a researcher's entire career h-index is credited to wherever they are affiliated now; I address that residual concern by narrowing the paper's claims rather than by further re-attribution (see Comment 1.5/Tier 2 scope language, and the Conclusion changes below).

**Manuscript changes:**
- `sections/method.tex`: new `\subsection{Robustness to institution assignment}` (`\label{subsec:methods-institution-robustness}`), placed after the field-robustness methods subsection, describing the tie-detection and inclusive multi-institution re-assignment methodology.
- `sections/results.tex`: new `\subsection{Robustness of institutional rankings to affiliation-tie assignment}` (`\label{subsec:results-institution-robustness}`), placed after the field-robustness results subsection, reporting the h2/h3 rank correlations, top-N overlaps, and the Saudi Arabia ε3 finding (rises rather than falls under the fix).
- `sections/conc.tex`: Limitations paragraph — added two sentences naming current-affiliation attribution (including the tiebreak heuristic) as an explicit limitation, citing the multi-institution check as bounding evidence for the tiebreak-specific risk while stating plainly that it does not resolve the broader career-attribution concern.
- Verified by rebuilding the PDF (compiles cleanly).

---

### Comment 1.2

*(Status: **NOT STARTED** — Monte Carlo revision not yet run.)*

**Reviewer:** The new sensitivity analysis randomly selects authors and multiplies their h-indices by ratios drawn from four manually identified outliers. This design is insufficient for several reasons. First, author-disambiguation errors are unlikely to be independent and identically distributed... Second, the simulation represents only upward inflation... Third, the analysis adds synthetic error to a baseline already known to contain unknown error... Fourth, the reported plateau at high perturbation rates is partly a consequence of applying similar positive inflation to competitors throughout the dataset... The top-20 institutional overlap also falls to 78% at the 10% and 13% rates, which is not negligible... Finally, five trials per condition are too few to characterize uncertainty... The conclusion that the risks are "bounded rather than fatal" and that the rankings are robust "at every rate tested" is therefore not warranted.

**Response:** *[Placeholder — planned response, pending the rerun:]* I agree with all four specific critiques and have revised the Monte Carlo design accordingly: trials per condition increase from 5 to at least 50; the perturbation now includes downward (author-splitting) as well as upward (merge-style) synthetic error, applied independently rather than uniformly, to better approximate the paper's own finding that real disambiguation errors cluster by name commonality, language, and country rather than hitting the population at random; and the write-up explicitly discusses the cancellation effect built into applying similar inflation across competitors as a property of the perturbation design, not evidence of ranking robustness. The "bounded rather than fatal" and "robust at every rate tested" language is removed and replaced with a narrower claim: the rankings are stable under the specific perturbation model tested, and that model cannot speak to concentrated or directional bias of the kind the reviewer describes.

**Manuscript changes:** *[to be drafted once the revised Monte Carlo results are in.]*

---

### Comment 1.3

*(Status: **DONE** except the community-college sub-item, which is answered under Comment 1.4.)*

**Reviewer:** The manuscript describes the Leiden Ranking comparison as an "independent" validation, but the Leiden Ranking Open Edition used here is itself based on OpenAlex... This is convergent comparison within the same underlying data infrastructure, not independent external validation. More importantly, raw h2 correlates more strongly with MNCS (ρ = 0.634) than the proposed efficiency measure does (ρ = 0.580)... The manuscript would need to show incremental validity... The efficiency tables themselves raise additional validity concerns. Several highly ranked institutions are community colleges or other organizations for which the reported author counts and h2 values appear implausible... Accordingly, the statement that the comparison demonstrates "genuine differences in research excellence rather than differences in institutional size" should be removed.

**Response:** I agree on both counts and address them separately.

**Independence.** I no longer describe the Leiden Open Edition comparison as independent validation; I now describe it as a convergent check within a shared OpenAlex-derived data infrastructure, and I have added a second, genuinely independent comparison against Scimago Institutions Rankings (SIR) 2026, which is Scopus-derived — a different underlying citation database from both OpenAlex and Web-of-Science-based Leiden. Joining on normalized institution name (SIR's public export carries no ROR or OpenAlex ID, so this join is name-based and necessarily less precise than the ID-based Leiden join; match diagnostics are reported alongside the result), I match 3,659 institutions (~34% of SIR's list; ~30% of the paper's ≥100-author efficiency table) and find:

- Spearman ρ(raw h2 rank, SIR Global Rank) = **0.752**
- Spearman ρ(efficiency ε2 rank, SIR Global Rank) = **0.338**

Restricting the match to SIR's "Universities" sector only (5,491 of SIR's 10,827 institutions, excluding ministries, companies, hospitals, and other non-university entities SIR also ranks) gives essentially the same result (ρ = 0.755 raw, ρ = 0.332 efficiency), so the gap is not an artifact of comparing academic h2 against a mixed-sector SIR list.

This is, I want to be direct about it, the same pattern the reviewer flagged in the Leiden comparison, now confirmed against a source with no shared infrastructure with OpenAlex at all: raw h2 tracks an external composite ranking more closely than the size-normalized efficiency metric does. I no longer claim the efficiency normalization "demonstrates genuine differences in research excellence" — that sentence is removed. I now report both correlations as description rather than validation, and discuss directly, in a revised paragraph, why efficiency normalization apparently does not track independent external rankings as well as the raw (scale-dominated) measure — most plausibly because SIR's composite and Leiden's MNCS are themselves influenced by scale-correlated factors (institutional prominence, resource concentration) that raw h2 partially captures and that dividing out size removes.

**Community college entries.** See Comment 1.4 for the manual validation and manuscript fix.

**Manuscript changes:**
- `sections/method.tex`: existing `\subsection{External validation against the Leiden Ranking}` (`\label{subsec:methods-leiden}`) reframed — "independent" dropped, now explicitly described as a convergent check sharing OpenAlex infrastructure. New `\subsection{External validation against Scimago Institutions Rankings}` (`\label{subsec:methods-scimago}`) added immediately after, describing the SIR data source, the name-based join and its limitations relative to the ID-based Leiden join, and the Universities-only robustness check.
- `sections/results.tex`: existing `\subsubsection*{External validation against the Leiden Ranking}` — removed "The successive h-index hierarchy captures genuine differences in research quality across institutions rather than differences in size alone," replaced with a pointer to the new convergent-vs-independent framing. New `\subsubsection*{External validation against Scimago Institutions Rankings}` (`\label{subsubsec:scimago-validation}`) added reporting both Spearman correlations, the Universities-only check, and a synthesis paragraph noting both external comparisons show raw h2 outperforming ε2, read as description rather than validation.
- `sections/conc.tex`: sentence citing the Leiden comparison revised to drop the overclaim and mention the Scimago check.
- `references.bib`: added `scimago2026` entry (SCImago Institutions Rankings 2026, Overall Rank export).
- Verified by rebuilding the PDF (compiles cleanly).

---

### Comment 1.4

*(Status: **DONE**, scoped to the four institutions the reviewer named. See note below on a broader pattern found but deliberately left out of scope this round.)*

**Reviewer:** Several highly ranked institutions are community colleges or other organizations for which the reported author counts and h2 values appear implausible. These cases require direct validation rather than being presented as substantive findings. They may reflect the same historical-affiliation and author-disambiguation problems that motivated the original review.

**Response:** I manually checked the authors behind Bellevue University, Imperial Valley College, City College of San Francisco, and Frederick Community College's h2 values. The mechanism is not what I initially expected (authors listing a community college for demographic/alumni reasons); it is author-disambiguation merge failure. Each institution's highest-h1 contributing "authors" list an implausible number of distinct lifetime educational institutions (46–340, against a median of 4–7 across the rest of each institution's roster), spanning unrelated countries, fields, and career eras within a single record — clear evidence that several distinct real researchers have been collapsed into one OpenAlex author identifier, one of whose many affiliations happens to be the flagged institution.

I tested a concrete filter — excluding authors with ≥20 distinct lifetime educational institutions — against these four institutions specifically. It substantially closes the gap for three of the four (Bellevue 54→28, Imperial Valley 62→55, CCSF 43→35) but leaves Frederick Community College's h2 unchanged (37→37, since only 1 of its 416 assigned authors meets the threshold and removing it doesn't cross the rank-37 value) — indicating the pattern isn't fully captured by a single clean threshold. I added this as an explicit caveat directly under the efficiency table rather than silently patching the numbers, since (a) three of the four still don't fall all the way to a value I'd consider validated for a two-year teaching institution, and (b) I do not have a principled, validated system-wide threshold — see the note below.

**Note on scope:** while running this check, I found that the *same* merge-artifact pattern is not confined to small institutions. Applying the identical ≥20-institution filter system-wide (not just to the four flagged cases) drops Harvard's h2 from 137 to 103 (the largest single-institution drop in the dataset) and changes the overall top-10 institution ranking (60% overlap with baseline). All 40 of Harvard's top-40 authors by h1 are excluded by this filter; their h1 values (226–325) are individually implausible for a real person, and their affiliation lists show the same cross-field, cross-era pattern as the four flagged community colleges. This is a substantive finding — it suggests the paper's single most prominent number (Harvard, rank 1) may itself be inflated by the same disambiguation-error mechanism the reviewer is concerned about — but recomputing the paper's headline tables under a system-wide merge-artifact filter is a materially larger methodological change than what the reviewer asked for in this comment, and I have deliberately scoped this round's response to the four institutions named. The supporting scripts and data (`src/merge_artifact_filter_check.py`, `src/harvard_merge_check.py`, `results/merge_artifact_filter_check.log`, `results/harvard_merge_check.log`) remain in the repository, and this is flagged here for the record in case it should be taken up in a future revision or by the reviewer.

**Manuscript changes:**
- `sections/results.tex`, "Efficiency rankings" subsubsection (after Table `tab:h2-efficiency-all`): added a paragraph reporting the merge-artifact mechanism and the corrected h2 values for the four flagged institutions, explicitly scoping the correction to these four and not the rest of the dataset.
- `sections/conc.tex`: Limitations paragraph — added a sentence pointing to this caveat alongside the existing retraction-flagging sentence.
- Verified by rebuilding the PDF (compiles cleanly).

---

### Comment 1.5

*(Status: **DONE**.)*

**Reviewer:** The manuscript cites topic-level classifier accuracy and then asserts that field-level accuracy is "substantially higher" because some topic errors remain within a parent field. This is plausible, but no field-level validation is presented... The multi-field analysis tests an alternative allocation rule using the same underlying OpenAlex classifications; it does not test whether those classifications are correct. Moreover, the substantive leaders are not fully robust: only 18 of 27 field leaders remain unchanged at the 20% threshold, while the Wageningen Environmental Science and Carnegie Mellon Computer Science conclusions change under alternative specifications... The results therefore demonstrate meaningful specification dependence, not merely minor noise.

**Response:** I agree "substantially higher" overstates a claim I have not measured directly, and have softened it to "plausibly higher," with an added clause making explicit that this is an inference from the structure of the classification hierarchy, not a measured field-level accuracy figure — no field-level validation of the classifier is presented. I also checked whether the abstract and conclusion's claims about Wageningen's Environmental Science lead and Carnegie Mellon's Computer Science lead were already conditioned on the single-field assignment: Wageningen's Environmental Science lead already carried this caveat from the round-1 revision; Carnegie Mellon's Computer Science lead did not (the paper's own robustness section shows it falls to Stanford at the 20% multi-field threshold), so I added the missing qualifier.

**Manuscript changes:**
- `sections/method.tex`, "Author-level assignment" subsection: "field-level accuracy is substantially higher" → "plausibly higher, though this is an inference from the structure of the classification hierarchy rather than a directly measured field-level accuracy figure: no field-level validation of the classifier is presented here."
- `main.tex` abstract and `sections/conc.tex`: added a qualifier noting the Carnegie Mellon Computer Science lead, like the Wageningen Environmental Science lead, is a single-field-assignment result that changes under the paper's own multi-field robustness check.
- Verified by rebuilding the PDF (compiles cleanly).

---

### Comment 1.6

*(Status: **DONE**, in the sense that the planned response is fully written and reflected in the manuscript — but see the response text below for what this does and doesn't establish; it is honestly only a partial answer to the reviewer's "systematic investigation" ask.)*

**Reviewer:** The h3 calculation assigns institutional h2 values to countries using current OpenAlex institutional locations. Because each institutional h2 already attributes researchers' accumulated career impact to their most recent institution, international mobility and secondary affiliations can reallocate historical research impact across countries. The manuscript itself identifies Saudi Arabia as an apparent example of this distortion, yet continues to interpret other country efficiency rankings substantively. Once a known artifact can elevate a country to fourth place in the efficiency ranking, the validity of the entire country comparison requires systematic investigation. It is not sufficient to label one conspicuous case as a limitation while treating the remaining rankings as genuine research-system differences.

**Response:** I ran the country-level analogue of the Comment 1.1 multi-institution tie-check: h3 rank correlation between baseline and the inclusive multi-institution roster is ρ = 0.997, with 100% top-10 and 95% top-20 overlap, and Saudi Arabia's efficiency figure moves slightly *up* under the tie-fix (ε3: 6.69 → 7.50), not down. I want to be direct about what this does and doesn't establish: it rules out the current-affiliation tiebreak heuristic as the mechanism behind Saudi Arabia's anomaly (already suspected, per the manuscript's own citation, to be funding-driven affiliation-listing rather than a tie-breaking artifact) — but it does not constitute the "systematic investigation" the reviewer is asking for, because it only tests one specific attribution mechanism (current-tie handling) and that mechanism turns out not to be the one responsible. I do not have a country-level check that isolates *secondary/funding-affiliation listing* specifically, which is the mechanism the manuscript already names for Saudi Arabia, and building one would require the same per-work affiliation data the "impractical" objection in Comment 1.1 already covers.

Given that, I am not claiming the country-efficiency comparison is now validated. Instead, per Tier 2/Comment 1.5's scope-narrowing, I am moderating the interpretive language around country efficiency rankings generally (removing claims like "confirming that their research depth is genuine rather than an artefact of institutional scale" for the countries that place well on both raw h3 and efficiency) so the manuscript does not imply the other rankings are cleared of the same risk merely because one case was named. The Saudi Arabia caveat stays; it is no longer implied to be an isolated exception.

Note that institution→country mapping itself (which country an institution is located in) is a static lookup independent of researcher mobility — the reviewer's concern, and both checks run under Comment 1.1, operate entirely at the researcher→institution attribution step.

**Manuscript changes:**
- `sections/results.tex`, "Country efficiency" subsection (`\label{subsec:h3-efficiency}`): "a top tier of countries with compact but high-quality research systems" → "compact research systems that place well on this metric"; "confirming that their research depth is genuine rather than an artefact of institutional scale" replaced with a sentence noting that placing well on both raw h3 and efficiency is a weaker claim than confirming genuine research depth, since neither measure rules out affiliation-attribution distortion; Saudi Arabia sentence extended to note the multi-institution check rules out the tiebreak mechanism specifically without clearing other countries of comparable risk.
- `sections/conc.tex`: Limitations paragraph's Saudi Arabia sentence extended with the same "not necessarily the only country affected" framing.
- Verified by rebuilding the PDF (compiles cleanly).

---

### Comment 1.7

*(Status: **DONE**.)*

**Reviewer:** The manuscript contains several material inconsistencies:
- Section 2 reports 17.1 million retained authors and 20,669 institutions, whereas Section 3.2 reports 30.0 million authors and 20,932 institutions.
- The abstract states that Medicine accounts for 44% of the author pool, while the conclusion states 25%.
- Section 3.2 says the ranking uses the institutions and authors "described in Section 2," although the reported totals do not agree.
- The manuscript refers to "26 fields" in the methodology but reports leaders for 27 fields in the robustness analysis.
- The conclusion states that "institution count alone" explains variation in h2, although institutional h2 is modeled using author count; institution count is used for h3.
- Table and figure numbering appears inconsistent around the country-level results.

**Response:** All six were checked directly against the live pipeline output (not just reconciled by picking whichever number "looked more current") before editing, since two of them turned out not to be simple typos.

- **17.1M/20,669 vs. 30.0M/20,932:** the live dataset (`data/openalex.duckdb`) contains 29,970,900 authors across 20,932 institutions — the figures already used in Section 3.2 and the Conclusion. Section 2 and the abstract had not been updated after a later pipeline consolidation step; I have updated them to match rather than the reverse.
- **44% vs. 25% Medicine share:** confirmed directly — Medicine accounts for 7,584,582 of 29,970,900 authors, 25.3%. The abstract's "44%" was simply incorrect and is corrected to 25%.
- **26 vs. 27 fields:** there are exactly 26 distinct fields in the data, as used consistently everywhere except the field-robustness passage. Tracing the "27" there to its source, I found it is not an error: the field-robustness script's "leading institution per field" query returns two tied co-leaders for Social Sciences (a genuine tie in h2, not a bug), so "27 fields' leading institutions" is the correct count of leader *rows*, one more than the field count. I've added a clarifying parenthetical at first use rather than silently changing 27 to 26, since either number alone is incomplete.
- **"Institution count alone" explains h2/h3:** confirmed the reviewer is right that this conflates the two models. The Conclusion now reads "author count alone explains 91% of the variance in h2, and institution count alone explains 92% of the variance in h3," matching the precise language already used in the Results section.
- **Table/figure numbering:** I audited every cross-reference in the country-level results subsections (institution efficiency through the sensitivity analysis) against its label definition and found no mismatches or duplicate labels. I was not able to identify the specific inconsistency the reviewer saw; it is possible this was resolved in the PDF regenerated for this revision, or the reviewer can point to a specific table/figure pair if the issue persists.

**Manuscript changes:**
- Abstract (`main.tex`): institution/author counts and Medicine percentage corrected.
- Methods (`sections/method.tex`): author/institution counts corrected in two places (opening filter description and the institution-h2 row count).
- Results (`sections/results.tex`): added clarifying parenthetical explaining the 26-fields/27-leaders discrepancy.
- Conclusion (`sections/conc.tex`): variance-explained sentence corrected to distinguish author count (h2) from institution count (h3); stale 17.1-million-author reference in the Limitations paragraph corrected to 30.0 million.
- All six changes verified by rebuilding the PDF (compiles cleanly, no LaTeX errors).

---

## Summary of pending work

| # | Issue | Status |
|---|---|---|
| 1.1 | Institutional attribution (multi-institution tie-check adopted; stable-affiliation subset run but rejected as non-representative) | **Done** |
| 1.2 | Monte Carlo redesign (50+ trials, bidirectional, clustering) | Not started |
| 1.3 | External validation independence (Leiden reframe + Scimago) | **Done** |
| 1.4 | Community college efficiency entries | **Done**, scoped to the 4 named institutions — see note below on a broader pattern found but deliberately left out of scope |
| 1.5 | Field-classification language softening | **Done** |
| 1.6 | Country-level attribution (multi-institution check run; does not fully resolve reviewer's ask, see response) | **Done** (honest partial answer) |
| 1.7 | Internal inconsistencies | **Done** |

**Note on 1.4 (carried over from Comment 1.4 above):** the same disambiguation-merge pattern found in the four flagged community colleges is also present at the very top of Harvard's author roster (all 40 of its top-40-by-h1 authors are excluded by the same ≥20-institution filter), and applying that filter system-wide drops Harvard's h2 from 137 to 103 and reshuffles the top-10 institution table (60% overlap). This is a real, quantified finding, deliberately left out of this round's manuscript changes — the reviewer's comment named four specific institutions, and recomputing the paper's headline tables is a substantially larger change than what was asked. Flagged here for visibility in case it should be taken up separately.
