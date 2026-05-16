"""Shared pytest fixtures: synthetic OHLCV frames for deterministic tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_frame(
    closes: list[float],
    *,
    volume: float = 1000.0,
    start: str = "2024-01-01",
    freq: str = "1h",
) -> pd.DataFrame:
    n = len(closes)
    index = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    closes_arr = np.array(closes, dtype=float)
    opens = np.concatenate([[closes_arr[0]], closes_arr[:-1]])
    highs = np.maximum(opens, closes_arr) + 0.5
    lows = np.minimum(opens, closes_arr) - 0.5
    volumes = np.full(n, fill_value=volume, dtype=float)
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes_arr,
            "volume": volumes,
        },
        index=index,
    )


@pytest.fixture
def trending_up_frame() -> pd.DataFrame:
    """A frame that walks steadily from 100 up to 130."""
    closes = list(np.linspace(100, 130, 30))
    return _make_frame(closes)


@pytest.fixture
def trending_down_frame() -> pd.DataFrame:
    closes = list(np.linspace(130, 100, 30))
    return _make_frame(closes)


@pytest.fixture
def range_bound_frame() -> pd.DataFrame:
    """Bars that oscillate tightly around 100."""
    rng = np.random.default_rng(seed=42)
    closes = 100 + rng.uniform(-0.5, 0.5, size=40)
    return _make_frame(list(closes))


@pytest.fixture
def two_day_frame() -> pd.DataFrame:
    """48 hourly bars spanning two calendar days for POI tests."""
    rng = np.random.default_rng(seed=7)
    closes = 100 + np.cumsum(rng.normal(0, 0.5, size=48))
    return _make_frame(list(closes), start="2024-01-01")
