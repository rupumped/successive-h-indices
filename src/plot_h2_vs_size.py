#!/usr/bin/env python3
"""
Scatter plot of H2 vs author_count^(1/beta_1) with a linear trendline and R²
value, where beta_1 = alpha_0*alpha_1 is the Lotka exponent fit by
estimate_alphas.py (Egghe 2008 eq. 11: h2 = author_count^(1/beta_1)). Run
estimate_alphas.py first.

Usage:
  python3 plot_h2_vs_size.py
"""

import json
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INST_CSV = os.path.join(ROOT_DIR, "data", "interim", "h2_by_institution.csv")
ALPHAS_JSON = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_PNG  = os.path.join(ROOT_DIR, "results", "h2_vs_size.png")

MIN_AUTHORS = 10

with open(ALPHAS_JSON) as f:
    beta_1 = json.load(f)["beta_1"]
inv_beta_1 = 1.0 / beta_1

df = pd.read_csv(INST_CSV)
df = df[df["author_count"] >= MIN_AUTHORS].copy()
df["scaled_authors"] = df["author_count"] ** inv_beta_1

x = df["scaled_authors"].values
y = df["h2"].values

# Regression forced through the origin: the self-consistency argument this
# tests predicts h2 = c*author_count^(1/beta_1) with no additive constant
# (N=0 authors trivially gives h2=0), so fit that one-parameter model rather
# than an OLS line with a free intercept. R² here is the uncentered version
# appropriate for a no-intercept fit (relative to sum(y^2), not
# sum((y-mean(y))^2)).
slope = np.sum(x * y) / np.sum(x ** 2)
y_pred = slope * x
r2 = 1 - np.sum((y - y_pred) ** 2) / np.sum(y ** 2)
x_line = np.linspace(0, x.max(), 300)
y_line = slope * x_line

fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(x, y, s=12, alpha=0.4, linewidths=0, color="steelblue", label="Institution")
ax.plot(x_line, y_line, color="crimson", linewidth=1.5,
        label=f"y = {slope:.3f}x   R² = {r2:.3f}")

ax.set_xlabel(f"author count^(1/β₁)  [β₁={beta_1:.3f}]", fontsize=12)
ax.set_ylabel("H2", fontsize=12)
ax.set_title("H2 vs. Institution Size", fontsize=13)
ax.set_xlim(left=0)
ax.set_ylim(bottom=0)
ax.legend(fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print(f"Saved → {OUT_PNG}")
print(f"beta_1={beta_1:.4f}  slope={slope:.4f}  R²={r2:.4f}  n={len(df):,}")
