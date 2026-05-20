"""Generate a sample dark-theme chart with synthetic data (no Discord needed).

Useful for local smoke-testing and for screenshots in the README / PR.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.data.fetchers import MarketBars
from trading_bot.render.charts import render_market_chart
from trading_bot.reports.daily import build_chart_bundle


def _build_synthetic_bars(symbol: str = "DEMO/USDT") -> MarketBars:
    rng = np.random.default_rng(seed=1)
    n = 240
    drift = np.linspace(0, 4, n)
    noise = rng.normal(0, 0.6, size=n).cumsum()
    closes = 100 + drift + noise
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) + rng.uniform(0.1, 0.8, size=n)
    lows = np.minimum(opens, closes) - rng.uniform(0.1, 0.8, size=n)
    volumes = rng.uniform(500, 2500, size=n)
    idx = pd.date_range("2024-06-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )
    return MarketBars(symbol=symbol, timeframe="1h", kind="crypto", df=df)


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/sample_chart.png")
    bars = _build_synthetic_bars()
    bundle = build_chart_bundle(bars)
    png = render_market_chart(bundle)
    out_path.write_bytes(png)
    print(f"Wrote {out_path} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
