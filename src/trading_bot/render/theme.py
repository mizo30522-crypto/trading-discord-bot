"""Matplotlib dark theme used by every chart the bot ships to Discord."""

from __future__ import annotations

from typing import Final

import matplotlib as mpl

DARK_THEME: Final[dict[str, str]] = {
    "bg": "#0b1020",
    "panel": "#11172b",
    "grid": "#1c2440",
    "text": "#e6e9f5",
    "muted": "#8b94b8",
    "accent": "#7c5cff",
    "bull": "#26d07c",
    "bear": "#ff5466",
    "poc": "#ffd166",
    "vah": "#9ad6ff",
    "val": "#9ad6ff",
    "frvp": "#7c5cff",
    "delta_pos": "#26d07c",
    "delta_neg": "#ff5466",
    "sigma1": "#5fc7a8",
    "sigma2": "#f0a44b",
    "sigma3": "#ff6f91",
    "poi_res": "#ff7aa2",
    "poi_sup": "#7ad3ff",
    "poi_lvl": "#c2c8e0",
}


def apply_dark_theme() -> None:
    """Apply the bot's dark color palette to all subsequent matplotlib charts."""
    mpl.rcParams.update(
        {
            "figure.facecolor": DARK_THEME["bg"],
            "axes.facecolor": DARK_THEME["panel"],
            "axes.edgecolor": DARK_THEME["grid"],
            "axes.labelcolor": DARK_THEME["text"],
            "axes.titlecolor": DARK_THEME["text"],
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "xtick.color": DARK_THEME["muted"],
            "ytick.color": DARK_THEME["muted"],
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "grid.color": DARK_THEME["grid"],
            "grid.linestyle": "-",
            "grid.alpha": 0.45,
            "legend.facecolor": DARK_THEME["panel"],
            "legend.edgecolor": DARK_THEME["grid"],
            "legend.labelcolor": DARK_THEME["text"],
            "legend.fontsize": 8,
            "text.color": DARK_THEME["text"],
            "savefig.facecolor": DARK_THEME["bg"],
            "savefig.edgecolor": DARK_THEME["bg"],
            "font.family": "DejaVu Sans",
            "font.size": 9,
        }
    )
