from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.analysis.stdv import volume_weighted_stdv_bands


def test_constant_price_has_zero_sigma() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": np.full(20, 100.0),
            "high": np.full(20, 100.0),
            "low": np.full(20, 100.0),
            "close": np.full(20, 100.0),
            "volume": np.full(20, 100.0),
        },
        index=idx,
    )
    bands = volume_weighted_stdv_bands(df)
    assert bands.sigma == pytest.approx(0.0)
    assert bands.upper_1 == pytest.approx(bands.lower_1)


def test_sigma_increases_with_dispersion() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="1h", tz="UTC")
    base = np.full(20, 100.0)
    tight = pd.DataFrame(
        {"open": base, "high": base + 0.01, "low": base - 0.01, "close": base, "volume": base},
        index=idx,
    )
    wide_closes = base + np.array([1.0, -1.0] * 10)
    wide = pd.DataFrame(
        {
            "open": base,
            "high": wide_closes + 0.5,
            "low": wide_closes - 0.5,
            "close": wide_closes,
            "volume": base,
        },
        index=idx,
    )
    assert volume_weighted_stdv_bands(wide).sigma > volume_weighted_stdv_bands(tight).sigma
