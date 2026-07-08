#!/usr/bin/env python3
"""
Scatter plot of H3 vs institution_count^(1/beta_2) with a linear trendline
and R² value, where beta_2 = alpha_0*alpha_1*alpha_2 is the Lotka exponent
fit by estimate_alphas.py (Egghe 2008 eq. 18: h3 = institution_count^(1/beta_2)).
Run estimate_alphas.py first.

Usage:
  python3 plot_h3_vs_size.py
"""

import json
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H3_CSV    = os.path.join(ROOT_DIR, "data", "interim", "h3_by_country.csv")
ALPHAS_JSON = os.path.join(ROOT_DIR, "results", "lotka_exponents.json")
OUT_PNG   = os.path.join(ROOT_DIR, "results", "h3_vs_size.png")

MIN_INST = 5

with open(ALPHAS_JSON) as f:
    beta_2 = json.load(f)["beta_2"]
inv_beta_2 = 1.0 / beta_2

df = pd.read_csv(H3_CSV)
df = df[df["institution_count"] >= MIN_INST].copy()
df["scaled_inst"] = df["institution_count"] ** inv_beta_2

x = df["scaled_inst"].values
y = df["h3"].values

# Regression forced through the origin: institution_count=0 trivially gives
# h3=0. Unlike the old log2(institution_count) parametrization, x=0 here
# does correspond to institution_count=0 (not 1), so no separate intercept
# anchor is needed the way the log form required (log2(1)=0 forced a
# workaround since h3=1, not 0, at institution_count=1). R² is the uncentered
# version appropriate for a no-intercept fit.
slope = np.sum(x * y) / np.sum(x ** 2)
y_pred = slope * x
r2 = 1 - np.sum((y - y_pred) ** 2) / np.sum(y ** 2)
x_line = np.linspace(0, x.max(), 300)
y_line = slope * x_line

fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(x, y, s=30, alpha=0.6, linewidths=0, color="steelblue", label="Country")

for _, row in df.iterrows():
    ax.annotate(row["country_code"], (row["scaled_inst"], row["h3"]),
                fontsize=6, alpha=0.7, xytext=(3, 2), textcoords="offset points")

ax.plot(x_line, y_line, color="crimson", linewidth=1.5,
        label=f"y = {slope:.3f}x   R² = {r2:.3f}")

ax.set_xlabel(f"institution count^(1/β₂)  [β₂={beta_2:.3f}]", fontsize=12)
ax.set_ylabel("H3", fontsize=12)
ax.set_title("H3 vs. Country Size", fontsize=13)
ax.set_xlim(left=0)
ax.set_ylim(bottom=0)
ax.legend(fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print(f"Saved → {OUT_PNG}")
print(f"beta_2={beta_2:.4f}  slope={slope:.4f}  R²={r2:.4f}  n={len(df):,}")
