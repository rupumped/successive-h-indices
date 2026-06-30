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
from scipy import stats

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
H3_CSV    = os.path.join(OUT_DIR, "h3_by_country.csv")
OUT_PNG   = os.path.join(OUT_DIR, "h3_vs_size.png")

MIN_INST = 5

df = pd.read_csv(H3_CSV)
df = df[df["institution_count"] >= MIN_INST].copy()
df["log2_inst"] = np.log2(df["institution_count"])

x = df["log2_inst"].values
y = df["h3"].values

slope, intercept, r, p, _ = stats.linregress(x, y)
r2 = r ** 2
x_line = np.linspace(x.min(), x.max(), 300)
y_line = slope * x_line + intercept

fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(x, y, s=30, alpha=0.6, linewidths=0, color="steelblue", label="Country")

for _, row in df.iterrows():
    ax.annotate(row["country_code"], (row["log2_inst"], row["h3"]),
                fontsize=6, alpha=0.7, xytext=(3, 2), textcoords="offset points")

ax.plot(x_line, y_line, color="crimson", linewidth=1.5,
        label=f"y = {slope:.3f}x + {intercept:.2f}   R² = {r2:.3f}")

ax.set_xlabel("log₂(institution count)", fontsize=12)
ax.set_ylabel("H3", fontsize=12)
ax.set_title("H3 vs. Country Size", fontsize=13)
ax.legend(fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print(f"Saved → {OUT_PNG}")
print(f"slope={slope:.4f}  intercept={intercept:.4f}  R²={r2:.4f}  n={len(df):,}")
