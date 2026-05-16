"""Orderflow approximation derived from OHLCV bars.

True order flow requires tick / level-2 data which is not freely available
for FX or retail crypto feeds. We approximate it per bar by splitting the
bar's volume into estimated buying and selling pressure:

    buy_pct  = (close - low)  / (high - low)
    sell_pct = (high - close) / (high - low)

    buy_vol  = volume * buy_pct
    sell_vol = volume * sell_pct
    delta    = buy_vol - sell_vol

The cumulative delta over the window is a useful proxy for net directional
pressure. This module returns the latest delta, the cumulative delta, and a
classification of recent flow ("bullish" / "bearish" / "balanced").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

FlowBias = Literal["bullish", "bearish", "balanced"]


@dataclass(frozen=True)
class OrderflowSummary:
    """Summary of the estimated orderflow over a window of bars."""

    buy_volume: float
    sell_volume: float
    delta: float
    cumulative_delta: float
    delta_series: pd.Series
    bias: FlowBias
    bias_strength: float  # 0..1


def _bar_buy_sell(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    rng = np.maximum(high - low, 1e-12)
    buy_pct = np.clip((close - low) / rng, 0.0, 1.0)
    sell_pct = 1.0 - buy_pct
    return vol * buy_pct, vol * sell_pct


def estimate_orderflow(
    df: pd.DataFrame,
    *,
    window: int = 24,
    bias_threshold: float = 0.15,
) -> OrderflowSummary:
    """Estimate orderflow over the last ``window`` bars of ``df``."""
    if df.empty:
        raise ValueError("Cannot estimate orderflow on an empty frame.")
    recent = df.tail(min(window, len(df)))
    buy, sell = _bar_buy_sell(recent)
    delta_arr = buy - sell
    delta_series = pd.Series(delta_arr, index=recent.index, name="delta")
    cum = float(delta_arr.sum())
    total = float(buy.sum() + sell.sum())
    bias_strength = abs(cum) / total if total > 0 else 0.0
    if bias_strength < bias_threshold:
        bias: FlowBias = "balanced"
    elif cum > 0:
        bias = "bullish"
    else:
        bias = "bearish"
    return OrderflowSummary(
        buy_volume=float(buy.sum()),
        sell_volume=float(sell.sum()),
        delta=float(delta_arr[-1]) if delta_arr.size else 0.0,
        cumulative_delta=cum,
        delta_series=delta_series,
        bias=bias,
        bias_strength=min(bias_strength, 1.0),
    )
