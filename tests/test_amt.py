from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.analysis.amt import classify_amt


def _frame_from_closes(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    arr = np.array(closes, dtype=float)
    opens = np.concatenate([[arr[0]], arr[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, arr) + 0.1,
            "low": np.minimum(opens, arr) - 0.1,
            "close": arr,
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def test_trend_up_day_is_classified() -> None:
    closes = list(np.linspace(100, 130, 24))
    df = _frame_from_closes(closes)
    res = classify_amt(df, session_bars=24, initial_balance_bars=2)
    assert res.day_type == "trend_up"
    assert res.session_close > res.session_open


def test_trend_down_day_is_classified() -> None:
    closes = list(np.linspace(130, 100, 24))
    df = _frame_from_closes(closes)
    res = classify_amt(df, session_bars=24, initial_balance_bars=2)
    assert res.day_type == "trend_down"


def test_non_trend_when_range_is_tight() -> None:
    rng = np.random.default_rng(seed=42)
    # First 30 bars give a wide ATR, last 24 bars are tight → non-trend session.
    wide = list(100 + np.cumsum(rng.normal(0, 1.0, size=30)))
    tight = list(wide[-1] + rng.uniform(-0.02, 0.02, size=24))
    df = _frame_from_closes(wide + tight)
    res = classify_amt(df, session_bars=24, initial_balance_bars=2)
    assert res.day_type == "non_trend"
