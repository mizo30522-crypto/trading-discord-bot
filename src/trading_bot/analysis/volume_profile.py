"""Volume Profile and Fixed Range Volume Profile (FRVP).

A volume profile bins traded volume by price into ``bins`` price buckets and
returns:

- **POC** (Point of Control): the price bucket with the most volume.
- **VAH / VAL**: the high / low price of the bucket range whose cumulative
  volume — expanding outward from the POC — covers ``value_area_pct`` (default
  70%) of the session's total volume.

The volume in each bar is distributed *uniformly* across the price buckets the
bar overlaps. This avoids attributing all of a bar's volume to its close and is
a standard approximation when tick data is not available.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VolumeProfile:
    """Result of a volume-profile computation."""

    poc: float
    vah: float
    val: float
    bin_edges: np.ndarray
    bin_volumes: np.ndarray
    total_volume: float
    value_area_pct: float

    @property
    def bin_centers(self) -> np.ndarray:
        return (self.bin_edges[:-1] + self.bin_edges[1:]) / 2.0


@dataclass(frozen=True)
class FRVPResult:
    """Fixed Range Volume Profile over a window of recent bars."""

    profile: VolumeProfile
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    bars: int


def _distribute_bar_volume(
    high: float,
    low: float,
    volume: float,
    bin_edges: np.ndarray,
) -> np.ndarray:
    """Spread ``volume`` evenly across all bins covered by ``[low, high]``."""
    out = np.zeros(len(bin_edges) - 1, dtype=float)
    if not np.isfinite(volume) or volume <= 0 or high <= low:
        # Degenerate bar: drop the volume into the bin that contains the close
        # if we can, otherwise skip it entirely.
        return out
    # clip to profile range so we don't lose volume to numerical drift
    lo = max(low, bin_edges[0])
    hi = min(high, bin_edges[-1])
    if hi <= lo:
        return out
    # binary-searchable bin indices for the price range
    lo_idx = int(np.searchsorted(bin_edges, lo, side="right") - 1)
    hi_idx = int(np.searchsorted(bin_edges, hi, side="left"))
    lo_idx = max(0, min(lo_idx, len(out) - 1))
    hi_idx = max(0, min(hi_idx, len(out) - 1))
    if lo_idx > hi_idx:
        return out
    span = hi - lo
    if span <= 0:
        out[lo_idx] += volume
        return out
    for i in range(lo_idx, hi_idx + 1):
        bin_lo = bin_edges[i]
        bin_hi = bin_edges[i + 1]
        overlap = max(0.0, min(hi, bin_hi) - max(lo, bin_lo))
        out[i] += volume * (overlap / span)
    return out


def _value_area_from_bins(
    bin_volumes: np.ndarray,
    bin_edges: np.ndarray,
    value_area_pct: float,
) -> tuple[int, int, int]:
    """Return ``(poc_idx, va_low_idx, va_high_idx)`` for the value area."""
    if bin_volumes.sum() == 0:
        return 0, 0, len(bin_volumes) - 1
    poc_idx = int(np.argmax(bin_volumes))
    target = bin_volumes.sum() * value_area_pct
    lo = hi = poc_idx
    covered = bin_volumes[poc_idx]
    while covered < target and (lo > 0 or hi < len(bin_volumes) - 1):
        up_vol = bin_volumes[hi + 1] if hi + 1 < len(bin_volumes) else -1
        down_vol = bin_volumes[lo - 1] if lo - 1 >= 0 else -1
        if up_vol < 0 and down_vol < 0:
            break
        if up_vol >= down_vol:
            hi += 1
            covered += up_vol
        else:
            lo -= 1
            covered += down_vol
    return poc_idx, lo, hi


def volume_profile(
    df: pd.DataFrame,
    *,
    bins: int = 64,
    value_area_pct: float = 0.70,
) -> VolumeProfile:
    """Compute the full volume profile for the given OHLCV ``df``."""
    if df.empty:
        raise ValueError("Cannot compute volume profile on an empty frame.")
    if not 0 < value_area_pct < 1:
        raise ValueError("value_area_pct must be in (0, 1).")
    lo = float(df["low"].min())
    hi = float(df["high"].max())
    if hi <= lo:
        # Flat market; widen by a hair so we still produce a valid profile.
        hi = lo + max(1e-6, lo * 1e-4)
    bin_edges = np.linspace(lo, hi, bins + 1)
    bin_volumes = np.zeros(bins, dtype=float)
    for high, low, vol in zip(df["high"].values, df["low"].values, df["volume"].values, strict=True):
        bin_volumes += _distribute_bar_volume(float(high), float(low), float(vol), bin_edges)
    poc_idx, va_lo_idx, va_hi_idx = _value_area_from_bins(bin_volumes, bin_edges, value_area_pct)
    poc = float((bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0)
    val = float(bin_edges[va_lo_idx])
    vah = float(bin_edges[va_hi_idx + 1])
    return VolumeProfile(
        poc=poc,
        vah=vah,
        val=val,
        bin_edges=bin_edges,
        bin_volumes=bin_volumes,
        total_volume=float(bin_volumes.sum()),
        value_area_pct=value_area_pct,
    )


def fixed_range_volume_profile(
    df: pd.DataFrame,
    *,
    lookback_bars: int = 120,
    bins: int = 64,
    value_area_pct: float = 0.70,
) -> FRVPResult:
    """Volume profile restricted to the most recent ``lookback_bars``."""
    if df.empty:
        raise ValueError("Cannot compute FRVP on an empty frame.")
    window = df.tail(lookback_bars)
    profile = volume_profile(window, bins=bins, value_area_pct=value_area_pct)
    return FRVPResult(
        profile=profile,
        window_start=pd.Timestamp(window.index[0]),
        window_end=pd.Timestamp(window.index[-1]),
        bars=len(window),
    )
