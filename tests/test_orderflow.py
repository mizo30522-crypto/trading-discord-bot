from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.analysis.orderflow import estimate_orderflow


def _frame(closes: list[float], highs: list[float], lows: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def test_bullish_when_closes_near_highs() -> None:
    # Each bar closes at its high → all flow attributed to buyers.
    n = 30
    df = _frame(closes=[100 + i * 0.1 for i in range(n)],
                highs=[100 + i * 0.1 for i in range(n)],
                lows=[99 + i * 0.1 for i in range(n)])
    flow = estimate_orderflow(df, window=n)
    assert flow.bias == "bullish"
    assert flow.cumulative_delta > 0


def test_bearish_when_closes_near_lows() -> None:
    n = 30
    df = _frame(closes=[100 - i * 0.1 for i in range(n)],
                highs=[101 - i * 0.1 for i in range(n)],
                lows=[100 - i * 0.1 for i in range(n)])
    flow = estimate_orderflow(df, window=n)
    assert flow.bias == "bearish"
    assert flow.cumulative_delta < 0


def test_balanced_when_closes_mid_range() -> None:
    n = 30
    df = _frame(
        closes=[100.0] * n,
        highs=[101.0] * n,
        lows=[99.0] * n,
    )
    flow = estimate_orderflow(df, window=n)
    assert flow.bias == "balanced"
