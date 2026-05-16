"""Points of Interest extracted from recent price action.

POIs returned by :func:`find_points_of_interest`:

- Prior session High / Low / Close
- Last week's High / Low
- Recent swing High / Low (fractal-style 5-bar pivots)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class POI:
    """A single Point of Interest."""

    name: str
    price: float
    kind: str  # "resistance" | "support" | "level"


@dataclass(frozen=True)
class POIBundle:
    """Container for the full set of POIs extracted for a symbol."""

    levels: list[POI] = field(default_factory=list)

    @property
    def by_name(self) -> dict[str, float]:
        return {p.name: p.price for p in self.levels}


def _swings(df: pd.DataFrame, *, window: int = 5) -> tuple[float | None, float | None]:
    """Find the most recent N-bar fractal swing high and swing low.

    A 5-bar fractal swing high is a bar whose high is strictly greater than
    the two bars on either side; analogously for swing lows.
    """
    if len(df) < window:
        return None, None
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    half = window // 2
    swing_high: float | None = None
    swing_low: float | None = None
    for i in range(len(df) - half - 1, half - 1, -1):
        window_h = high[i - half : i + half + 1]
        window_l = low[i - half : i + half + 1]
        if swing_high is None and high[i] == window_h.max() and (window_h == high[i]).sum() == 1:
            swing_high = float(high[i])
        if swing_low is None and low[i] == window_l.min() and (window_l == low[i]).sum() == 1:
            swing_low = float(low[i])
        if swing_high is not None and swing_low is not None:
            break
    return swing_high, swing_low


def _prior_session_levels(df: pd.DataFrame) -> tuple[POI, POI, POI] | None:
    """Yesterday's H/L/C using calendar-day grouping in the index timezone."""
    if df.empty:
        return None
    days = df.copy()
    days["date"] = days.index.date  # type: ignore[attr-defined]
    grouped = days.groupby("date")
    if len(grouped) < 2:
        return None
    dates = sorted(grouped.groups.keys())
    prior = grouped.get_group(dates[-2])
    return (
        POI(name="Prior Day High", price=float(prior["high"].max()), kind="resistance"),
        POI(name="Prior Day Low", price=float(prior["low"].min()), kind="support"),
        POI(name="Prior Day Close", price=float(prior["close"].iloc[-1]), kind="level"),
    )


def _weekly_extremes(df: pd.DataFrame) -> tuple[POI, POI] | None:
    if df.empty:
        return None
    weekly = df.tail(min(len(df), 24 * 7))  # last ~week of 1h bars
    return (
        POI(name="Weekly High", price=float(weekly["high"].max()), kind="resistance"),
        POI(name="Weekly Low", price=float(weekly["low"].min()), kind="support"),
    )


def find_points_of_interest(df: pd.DataFrame) -> POIBundle:
    """Return the union of prior session, weekly, and swing POIs."""
    if df.empty:
        return POIBundle(levels=[])
    out: list[POI] = []
    prior = _prior_session_levels(df)
    if prior is not None:
        out.extend(prior)
    weekly = _weekly_extremes(df)
    if weekly is not None:
        out.extend(weekly)
    swing_high, swing_low = _swings(df, window=5)
    last_close = float(df["close"].iloc[-1])
    if swing_high is not None:
        kind = "resistance" if swing_high >= last_close else "support"
        out.append(POI(name="Swing High", price=swing_high, kind=kind))
    if swing_low is not None:
        kind = "resistance" if swing_low >= last_close else "support"
        out.append(POI(name="Swing Low", price=swing_low, kind=kind))
    # de-dup very-close levels (numerical drift on FX)
    cleaned: list[POI] = []
    for poi in sorted(out, key=lambda p: p.price):
        if cleaned and not _materially_different(cleaned[-1].price, poi.price):
            continue
        cleaned.append(poi)
    return POIBundle(levels=cleaned)


def _materially_different(a: float, b: float, *, tol_bps: float = 1.0) -> bool:
    """Return True iff a and b differ by more than ``tol_bps`` basis points."""
    base = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / base * 1e4 > tol_bps


__all__ = ["POI", "POIBundle", "find_points_of_interest"]


# numpy is imported to keep linters happy for downstream type stubs
_ = np
