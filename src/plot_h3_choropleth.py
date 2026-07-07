#!/usr/bin/env python3
"""
World choropleth of H3 (successive H-index) by country.

Reads:
  data/interim/h3_by_country.csv
  data/external/ne_50m_admin_0_countries.zip  (downloaded on first run)

Output: results/h3_choropleth.png

Usage:
  python3 plot_h3_choropleth.py
"""

import os
import urllib.request

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H3_CSV = os.path.join(ROOT_DIR, "data", "interim", "h3_by_country.csv")
WORLD_ZIP = os.path.join(ROOT_DIR, "data", "external", "ne_50m_admin_0_countries.zip")
WORLD_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"
OUT_PNG = os.path.join(ROOT_DIR, "results", "h3_choropleth.png")

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
NO_DATA_FILL = "#e1e0d9"
NO_DATA_EDGE = "#c3c2b7"
BORDER = "#fcfcfb"

# Sequential blue ramp, step 100 -> 700 (references/palette.md)
BLUE_RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]


def load_world():
    if not os.path.exists(WORLD_ZIP):
        os.makedirs(os.path.dirname(WORLD_ZIP), exist_ok=True)
        print(f"Downloading Natural Earth countries -> {WORLD_ZIP}")
        urllib.request.urlretrieve(WORLD_URL, WORLD_ZIP)
    world = gpd.read_file(f"zip://{WORLD_ZIP}")
    world = world[world["CONTINENT"] != "Antarctica"].copy()
    world = world.to_crs("ESRI:54009")  # Mollweide, equal-area

    # A few sovereigns (e.g. Australia's Indian Ocean territories) appear as
    # extra rows sharing the parent's ISO code -- keep only the largest.
    world["area"] = world.geometry.area
    has_iso = world["ISO_A2_EH"] != "-99"
    deduped = (
        world[has_iso]
        .sort_values("area", ascending=False)
        .drop_duplicates("ISO_A2_EH", keep="first")
    )
    world = pd.concat([deduped, world[~has_iso]])

    return world[["NAME", "ISO_A2_EH", "geometry"]]


def load_h3():
    df = pd.read_csv(H3_CSV, keep_default_na=False, na_values=[""])
    return df[["country_code", "h3"]]


def build_choropleth():
    world = load_world()
    h3 = load_h3()
    merged = world.merge(h3, left_on="ISO_A2_EH", right_on="country_code", how="left")
    merged["has_data"] = merged["h3"].notna()
    return merged


def plot_choropleth(gdf):
    cmap = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)
    real = gdf[gdf["has_data"]]
    norm = Normalize(vmin=np.log1p(real["h3"].min()), vmax=np.log1p(real["h3"].max()))

    fig, ax = plt.subplots(figsize=(18, 8))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    no_data = gdf[~gdf["has_data"]]
    no_data.plot(ax=ax, color=NO_DATA_FILL, edgecolor=NO_DATA_EDGE, linewidth=0.3)

    colors = cmap(norm(np.log1p(real["h3"])))
    real.plot(ax=ax, color=colors, edgecolor=BORDER, linewidth=0.4)

    ax.set_axis_off()
    ax.set_aspect("equal")

    sm = ScalarMappable(norm=norm, cmap=cmap)
    ticks_raw = [1, 5, 10, 20, 40, 70]
    cbar = fig.colorbar(
        sm, ax=ax, orientation="horizontal", fraction=0.035, pad=0.02,
        ticks=[np.log1p(t) for t in ticks_raw],
    )
    cbar.ax.set_xticklabels([str(t) for t in ticks_raw])
    cbar.set_label("H3 (successive H-index)", color=MUTED, fontsize=10)
    cbar.ax.xaxis.set_tick_params(color=MUTED, labelcolor=MUTED)
    cbar.outline.set_edgecolor(MUTED)

    fig.suptitle(
        "The World, Colored by H3", fontsize=24, fontweight="bold", color=INK, y=0.99,
    )

    fig.tight_layout(rect=(0, 0, 1, 0.92))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=300, facecolor=SURFACE)
    print(f"Saved -> {OUT_PNG}")


if __name__ == "__main__":
    gdf = build_choropleth()
    plot_choropleth(gdf)
