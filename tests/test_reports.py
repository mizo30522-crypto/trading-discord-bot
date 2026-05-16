"""End-to-end test for the report builder using a synthetic data source."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.data.fetchers import MarketBars
from trading_bot.reports.daily import build_chart_bundle


@pytest.fixture
def synthetic_bars() -> MarketBars:
    rng = np.random.default_rng(seed=0)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, size=200))
    idx = pd.date_range("2024-01-01", periods=200, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": np.concatenate([[closes[0]], closes[:-1]]),
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": rng.uniform(500, 1500, size=200),
        },
        index=idx,
    )
    return MarketBars(symbol="TEST/USD", timeframe="1h", kind="crypto", df=df)


def test_chart_bundle_runs_all_analyses(synthetic_bars: MarketBars) -> None:
    bundle = build_chart_bundle(synthetic_bars)
    assert bundle.volume_profile.total_volume > 0
    assert bundle.frvp.bars > 0
    assert bundle.stdv.sigma >= 0
    assert bundle.amt.label
    assert bundle.orderflow.bias in {"bullish", "bearish", "balanced"}
    # Developing VA produces at least one point.
    assert len(bundle.dva.poc) >= 1


def test_chart_rendering_produces_png(synthetic_bars: MarketBars) -> None:
    from trading_bot.render.charts import render_market_chart

    bundle = build_chart_bundle(synthetic_bars)
    png = render_market_chart(bundle)
    assert png.startswith(b"\x89PNG\r\n")
    assert len(png) > 5000  # not just an empty 1x1 placeholder
