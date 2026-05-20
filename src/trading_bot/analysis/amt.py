"""Auction Market Theory day-type classification.

Loose mapping of an OHLC session to one of:

- ``trend_up`` / ``trend_down``  – directional, open near one extreme and close
  near the opposite extreme.
- ``normal_variation``           – wide-range balanced session, close inside the
  initial balance.
- ``normal``                     – range extension on one side without an
  opposite drive.
- ``neutral``                    – range extension on both sides, close in
  between.
- ``non_trend``                  – tight range relative to recent volatility.

The classifier is intentionally simple and rule-based so it can be unit-tested
deterministically; it is a heuristic helper, not a definitive AMT call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

DayType = Literal[
    "trend_up",
    "trend_down",
    "normal_variation",
    "normal",
    "neutral",
    "non_trend",
]


@dataclass(frozen=True)
class AMTResult:
    """Result of an AMT day-type classification."""

    day_type: DayType
    initial_balance_high: float
    initial_balance_low: float
    session_high: float
    session_low: float
    session_open: float
    session_close: float
    range_to_atr_ratio: float
    rationale: str

    @property
    def label(self) -> str:
        return self.day_type.replace("_", " ").title()


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    tr = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ]
    )
    if tr.size == 0:
        return float(high[-1] - low[-1]) if high.size else 0.0
    period = min(period, tr.size)
    return float(np.mean(tr[-period:]))


def classify_amt(
    df: pd.DataFrame,
    *,
    initial_balance_bars: int = 2,
    session_bars: int | None = None,
    non_trend_ratio: float = 0.6,
    trend_close_pct: float = 0.2,
) -> AMTResult:
    """Classify the most recent ``session_bars`` of ``df`` into a day type."""
    if df.empty:
        raise ValueError("Cannot classify AMT on an empty frame.")
    if session_bars is None:
        # Default: last 24 bars (e.g. last 24h on 1h data).
        session_bars = min(24, len(df))
    session = df.tail(session_bars)
    ib = session.head(max(1, min(initial_balance_bars, len(session))))
    ib_high = float(ib["high"].max())
    ib_low = float(ib["low"].min())
    s_high = float(session["high"].max())
    s_low = float(session["low"].min())
    s_open = float(session["open"].iloc[0])
    s_close = float(session["close"].iloc[-1])
    session_range = s_high - s_low
    # ATR is measured on the history *before* the session so that a tight session
    # following a volatile history is correctly flagged as non-trend.
    context = df.iloc[:-session_bars] if len(df) > session_bars else df
    atr = _atr(context, period=14)
    ratio = session_range / atr if atr > 0 else 1.0

    rationale_parts: list[str] = []
    rationale_parts.append(
        f"IB={ib_low:.5g}-{ib_high:.5g}, session={s_low:.5g}-{s_high:.5g}, "
        f"open={s_open:.5g}, close={s_close:.5g}, range/ATR={ratio:.2f}"
    )

    if ratio < non_trend_ratio:
        rationale_parts.append(f"range/ATR<{non_trend_ratio} → non-trend day.")
        return AMTResult(
            day_type="non_trend",
            initial_balance_high=ib_high,
            initial_balance_low=ib_low,
            session_high=s_high,
            session_low=s_low,
            session_open=s_open,
            session_close=s_close,
            range_to_atr_ratio=ratio,
            rationale=" ".join(rationale_parts),
        )

    extended_up = s_high > ib_high
    extended_down = s_low < ib_low
    span = max(session_range, 1e-12)
    close_loc = (s_close - s_low) / span  # 0 at low, 1 at high

    if extended_up and not extended_down and close_loc >= 1 - trend_close_pct:
        day_type: DayType = "trend_up"
        rationale_parts.append("Upside extension and close near session high → trend up day.")
    elif extended_down and not extended_up and close_loc <= trend_close_pct:
        day_type = "trend_down"
        rationale_parts.append("Downside extension and close near session low → trend down day.")
    elif extended_up and extended_down:
        if trend_close_pct < close_loc < 1 - trend_close_pct:
            day_type = "neutral"
            rationale_parts.append("Range extended on both sides, close in middle → neutral day.")
        else:
            day_type = "normal_variation"
            rationale_parts.append(
                "Range extended on both sides but close near one extreme → normal variation."
            )
    elif extended_up or extended_down:
        day_type = "normal"
        rationale_parts.append(
            "Range extension on a single side without a strong opposite drive → normal day."
        )
    else:
        day_type = "non_trend"
        rationale_parts.append("Stayed within the initial balance → non-trend day.")
    return AMTResult(
        day_type=day_type,
        initial_balance_high=ib_high,
        initial_balance_low=ib_low,
        session_high=s_high,
        session_low=s_low,
        session_open=s_open,
        session_close=s_close,
        range_to_atr_ratio=ratio,
        rationale=" ".join(rationale_parts),
    )
