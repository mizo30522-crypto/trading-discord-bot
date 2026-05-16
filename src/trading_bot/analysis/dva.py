"""Developing Value Area — how POC / VAH / VAL evolve through the session."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_bot.analysis.volume_profile import volume_profile


@dataclass(frozen=True)
class DevelopingValueArea:
    """POC / VAH / VAL recomputed cumulatively across a session."""

    timestamps: pd.DatetimeIndex
    poc: np.ndarray
    vah: np.ndarray
    val: np.ndarray

    @property
    def latest(self) -> tuple[float, float, float]:
        """Return ``(poc, vah, val)`` at the end of the developing window."""
        return float(self.poc[-1]), float(self.vah[-1]), float(self.val[-1])

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"poc": self.poc, "vah": self.vah, "val": self.val},
            index=self.timestamps,
        )


def developing_value_area(
    df: pd.DataFrame,
    *,
    bins: int = 48,
    value_area_pct: float = 0.70,
    min_bars: int = 5,
    step: int = 1,
) -> DevelopingValueArea:
    """Compute the value area incrementally across the most recent session.

    Recomputes a volume profile at every ``step`` bars starting from
    ``min_bars`` bars and stores the resulting POC / VAH / VAL series.
    """
    if df.empty:
        raise ValueError("Cannot compute developing value area on an empty frame.")
    n = len(df)
    if n < min_bars:
        min_bars = max(2, n)
    rows: list[tuple[pd.Timestamp, float, float, float]] = []
    for end in range(min_bars, n + 1, step):
        window = df.iloc[:end]
        vp = volume_profile(window, bins=bins, value_area_pct=value_area_pct)
        rows.append((pd.Timestamp(window.index[-1]), vp.poc, vp.vah, vp.val))
    if not rows:
        # Single-bar fallback so callers never get an empty result.
        vp = volume_profile(df, bins=bins, value_area_pct=value_area_pct)
        rows = [(pd.Timestamp(df.index[-1]), vp.poc, vp.vah, vp.val)]
    timestamps = pd.DatetimeIndex([r[0] for r in rows])
    poc = np.array([r[1] for r in rows], dtype=float)
    vah = np.array([r[2] for r in rows], dtype=float)
    val = np.array([r[3] for r in rows], dtype=float)
    return DevelopingValueArea(timestamps=timestamps, poc=poc, vah=vah, val=val)
