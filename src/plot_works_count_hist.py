#!/usr/bin/env python3
"""
Histogram of works_count across authors, diagnostic for the WORKS_COUNT_CAP
used by estimate_alphas.py to exclude author-disambiguation artifacts before
fitting alpha_1 (Egghe 2008 eq. 6). The top works_count authors pair huge
volume with single-digit h_index (e.g. works_count=278,862, h_index=1) --
implausible for a real individual, and the likely signature of a generic
name or collaboration byline merged into one OpenAlex author ID.

Usage:
  python3 plot_works_count_hist.py
"""

import os

import duckdb
import numpy as np
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHORS_CSV = os.path.join(ROOT_DIR, "data", "interim", "authors.csv")
OUT_PNG = os.path.join(ROOT_DIR, "results", "works_count_histogram.png")

CANDIDATE_CUTOFFS = (2_000, 5_000, 10_000)

con = duckdb.connect()
vals = con.execute(
    f"SELECT works_count FROM read_csv_auto('{AUTHORS_CSV}') WHERE works_count > 0"
).fetchnumpy()["works_count"].astype(float)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

axes[0].hist(vals, bins=200)
axes[0].set_yscale("log")
axes[0].set_xlabel("works_count")
axes[0].set_ylabel("number of authors (log scale)")
axes[0].set_title("works_count distribution (linear x)")

bins = np.logspace(0, np.log10(vals.max()), 80)
axes[1].hist(vals, bins=bins)
axes[1].set_xscale("log")
axes[1].set_yscale("log")
axes[1].set_xlabel("works_count (log scale)")
axes[1].set_ylabel("number of authors (log scale)")
axes[1].set_title("works_count distribution (log-log)")
for cutoff in CANDIDATE_CUTOFFS:
    axes[1].axvline(cutoff, color="red", linestyle="--", alpha=0.5)
    axes[1].text(cutoff, axes[1].get_ylim()[1] * 0.5, str(cutoff),
                 rotation=90, fontsize=8, color="red")

fig.suptitle(f"n={len(vals):,} authors, min={vals.min():.0f}, max={vals.max():.0f}")
fig.tight_layout()
fig.savefig(OUT_PNG, dpi=130)
print(f"Saved -> {OUT_PNG}")
for cutoff in CANDIDATE_CUTOFFS:
    excluded = int(np.sum(vals > cutoff))
    print(f"  cutoff={cutoff:>6,}: excludes {excluded:>4,} authors ({100*excluded/len(vals):.4f}%)")
