#!/usr/bin/env python3
"""
Scatter plot of H3 vs log2(institution_count) with a linear trendline and R² value.

Usage:
  python3 plot_h3_vs_size.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H3_CSV    = os.path.join(ROOT_DIR, "data", "interim", "h3_by_country.csv")
OUT_PNG   = os.path.join(ROOT_DIR, "results", "h3_vs_size.png")

MIN_INST = 5

df = pd.read_csv(H3_CSV)
df = df[df["institution_count"] >= MIN_INST].copy()
df["log2_inst"] = np.log2(df["institution_count"])

x = df["log2_inst"].values
y = df["h3"].values

# Intercept fixed at 1, not 0: x=0 corresponds to institution_count=1, and a
# country with exactly one qualifying institution has h3=1 by construction
# (every retained author has h_index>=1, so that institution's h2>=1), not
# h3=0. Fit the one free parameter (slope) with that true boundary condition
# imposed, rather than an OLS line with an unconstrained intercept. R² is the
# uncentered version appropriate for a fixed-intercept fit, computed on the
# shifted variable z = y - 1.
z = y - 1
slope = np.sum(x * z) / np.sum(x ** 2)
z_pred = slope * x
r2 = 1 - np.sum((z - z_pred) ** 2) / np.sum(z ** 2)
x_line = np.linspace(0, x.max(), 300)
y_line = 1 + slope * x_line

fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(x, y, s=30, alpha=0.6, linewidths=0, color="steelblue", label="Country")

for _, row in df.iterrows():
    ax.annotate(row["country_code"], (row["log2_inst"], row["h3"]),
                fontsize=6, alpha=0.7, xytext=(3, 2), textcoords="offset points")

ax.plot(x_line, y_line, color="crimson", linewidth=1.5,
        label=f"y = 1 + {slope:.3f}x   R² = {r2:.3f}")

ax.set_xlabel("log₂(institution count)", fontsize=12)
ax.set_ylabel("H3", fontsize=12)
ax.set_title("H3 vs. Country Size", fontsize=13)
ax.set_ylim(bottom=0)
ax.legend(fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print(f"Saved → {OUT_PNG}")
print(f"slope={slope:.4f}  R²={r2:.4f}  n={len(df):,}")
