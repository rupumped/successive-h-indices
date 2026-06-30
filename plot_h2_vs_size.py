#!/usr/bin/env python3
"""
Scatter plot of H2 vs sqrt(author_count) with a linear trendline and R² value.

Usage:
  python3 plot_h2_vs_size.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

OUT_DIR  = os.path.dirname(os.path.abspath(__file__))
INST_CSV = os.path.join(OUT_DIR, "h2_by_institution.csv")
OUT_PNG  = os.path.join(OUT_DIR, "h2_vs_size.png")

MIN_AUTHORS = 10

df = pd.read_csv(INST_CSV)
df = df[df["author_count"] >= MIN_AUTHORS].copy()
df["sqrt_authors"] = np.sqrt(df["author_count"])

x = df["sqrt_authors"].values
y = df["h2"].values

slope, intercept, r, p, _ = stats.linregress(x, y)
r2 = r ** 2
x_line = np.linspace(x.min(), x.max(), 300)
y_line = slope * x_line + intercept

fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(x, y, s=12, alpha=0.4, linewidths=0, color="steelblue", label="Institution")
ax.plot(x_line, y_line, color="crimson", linewidth=1.5,
        label=f"y = {slope:.3f}x + {intercept:.2f}   R² = {r2:.3f}")

ax.set_xlabel("√(author count)", fontsize=12)
ax.set_ylabel("H2", fontsize=12)
ax.set_title("H2 vs. Institution Size", fontsize=13)
ax.legend(fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print(f"Saved → {OUT_PNG}")
print(f"slope={slope:.4f}  intercept={intercept:.4f}  R²={r2:.4f}  n={len(df):,}")
