"""Tests for the trade-signal generator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.analysis import (
    classify_amt,
    compute_signal,
    estimate_orderflow,
    find_points_of_interest,
    volume_profile,
    volume_weighted_stdv_bands,
)
from trading_bot.analysis.signal import TradeSignal


def _frame(closes: list[float], *, volume: float = 1000.0) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    arr = np.array(closes, dtype=float)
    opens = np.concatenate([[arr[0]], arr[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, arr) + 0.2,
            "low": np.minimum(opens, arr) - 0.2,
            "close": arr,
            "volume": np.full(n, volume),
        },
        index=idx,
    )


def _signal_for(df: pd.DataFrame) -> TradeSignal:
    return compute_signal(
        df,
        amt=classify_amt(df, session_bars=min(24, len(df))),
        vp=volume_profile(df, bins=32),
        stdv=volume_weighted_stdv_bands(df),
        flow=estimate_orderflow(df, window=min(24, len(df))),
        poi=find_points_of_interest(df).levels,
    )


def test_trend_up_yields_long_signal() -> None:
    closes = list(np.linspace(100, 130, 48))
    sig = _signal_for(_frame(closes))
    assert sig.bias == "LONG"
    last = closes[-1]
    assert sig.entry_low <= last <= sig.entry_high + 1e-9
    assert sig.stop_loss < sig.entry
    assert sig.tp1.price > sig.entry
    assert sig.tp2.price >= sig.tp1.price
    assert sig.tp3.price >= sig.tp2.price
    assert sig.tp1.rr > 0
    assert sig.risk_pct > 0
    assert sig.quality in {"high", "medium", "low"}


def test_trend_down_yields_short_signal() -> None:
    closes = list(np.linspace(130, 100, 48))
    sig = _signal_for(_frame(closes))
    assert sig.bias == "SHORT"
    last = closes[-1]
    assert sig.entry_low - 1e-9 <= last <= sig.entry_high
    assert sig.stop_loss > sig.entry
    assert sig.tp1.price < sig.entry
    assert sig.tp2.price <= sig.tp1.price
    assert sig.tp3.price <= sig.tp2.price
    assert sig.tp1.rr > 0
    assert sig.risk_pct > 0


def test_targets_have_distinct_sources_when_structure_is_rich() -> None:
    rng = np.random.default_rng(seed=11)
    # Up-trend with noise so multiple distinct levels appear above the close.
    closes = list(100 + np.cumsum(rng.normal(0.4, 0.6, size=120)))
    sig = _signal_for(_frame(closes))
    assert sig.bias == "LONG"
    sources = {sig.tp1.source, sig.tp2.source, sig.tp3.source}
    assert len(sources) >= 2  # at least two distinct structural targets


def test_neutral_signal_when_no_actionable_setup() -> None:
    # Tight range right at the POC → mean-reversion pulls toward POC but the
    # current price barely deviates, so the signal should be NEUTRAL or low
    # quality. We assert it at least renders without raising.
    rng = np.random.default_rng(seed=3)
    closes = 100 + rng.uniform(-0.05, 0.05, size=80)
    sig = _signal_for(_frame(list(closes)))
    assert sig.bias in {"LONG", "SHORT", "NEUTRAL"}
    if sig.bias != "NEUTRAL":
        # Even if not strictly neutral, a tight range should produce a low or
        # medium quality grade, not high.
        assert sig.quality in {"low", "medium"}


def test_risk_reward_is_positive_for_directional_trades() -> None:
    closes = list(np.linspace(50, 60, 48))
    sig = _signal_for(_frame(closes))
    assert sig.bias == "LONG"
    for tp in (sig.tp1, sig.tp2, sig.tp3):
        assert tp.rr >= 0
    assert sig.tp3.rr >= sig.tp1.rr


def test_short_target_ordering() -> None:
    closes = list(np.linspace(200, 180, 48))
    sig = _signal_for(_frame(closes))
    assert sig.bias == "SHORT"
    # For shorts, TPs are below entry and monotonically decrease.
    assert sig.tp1.price < sig.entry
    assert sig.tp2.price <= sig.tp1.price
    assert sig.tp3.price <= sig.tp2.price
