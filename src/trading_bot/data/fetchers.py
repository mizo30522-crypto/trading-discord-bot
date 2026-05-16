"""Market data fetchers.

Crypto symbols (containing '/') are fetched via ccxt's public API; everything
else is treated as a yfinance ticker (Forex pairs, Gold futures, indices, ...).

All fetchers return a :class:`MarketBars` containing a tidy pandas DataFrame
indexed by UTC timestamp with columns ``[open, high, low, close, volume]``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

AssetKind = Literal["crypto", "fx_or_commodity"]


@dataclass(frozen=True)
class MarketBars:
    """OHLCV bars for one symbol on one timeframe."""

    symbol: str
    timeframe: str
    kind: AssetKind
    df: pd.DataFrame  # columns: open, high, low, close, volume; UTC index

    def __post_init__(self) -> None:
        expected = {"open", "high", "low", "close", "volume"}
        missing = expected - set(self.df.columns)
        if missing:
            raise ValueError(f"MarketBars df missing columns: {missing}")
        if self.df.empty:
            raise ValueError(f"MarketBars df is empty for {self.symbol}")


def classify_symbol(symbol: str) -> AssetKind:
    """Pick the data source family based on the symbol shape."""
    return "crypto" if "/" in symbol else "fx_or_commodity"


# --------------------------------------------------------------------------- #
# Crypto via ccxt
# --------------------------------------------------------------------------- #


def _fetch_crypto(symbol: str, timeframe: str, exchange_id: str, limit: int) -> pd.DataFrame:
    import ccxt  # imported lazily so tests can stub the function

    exchange_cls = getattr(ccxt, exchange_id, None)
    if exchange_cls is None:
        raise ValueError(f"Unknown ccxt exchange '{exchange_id}'")
    exchange = exchange_cls({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if not raw:
        raise RuntimeError(f"ccxt returned no bars for {symbol} @ {timeframe}")
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts")
    return df.astype(float)


# --------------------------------------------------------------------------- #
# FX / Gold / equities via yfinance
# --------------------------------------------------------------------------- #


_YF_INTERVAL = {
    "1h": "1h",
    "30m": "30m",
    "15m": "15m",
    "1d": "1d",
    "4h": "1h",  # yfinance has no 4h, we resample below
}


def _fetch_yf(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    import yfinance as yf  # imported lazily

    interval = _YF_INTERVAL.get(timeframe, "1h")
    # yfinance intraday is capped at ~730 days; pick a period that comfortably
    # covers the bar count we want.
    period = "60d" if interval in {"15m", "30m", "1h"} else "2y"
    raw = yf.download(
        tickers=symbol,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    # yfinance may return a multi-indexed column frame when one ticker.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    keep = ["open", "high", "low", "close", "volume"]
    df = raw[keep].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.dropna()
    if timeframe == "4h":
        df = (
            df.resample("4h", label="right", closed="right")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
    return df.tail(limit).astype(float)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def fetch_bars(
    symbol: str,
    *,
    timeframe: str = "1h",
    limit: int = 500,
    exchange_id: str = "binance",
) -> MarketBars:
    """Fetch OHLCV bars for ``symbol`` at ``timeframe`` (latest ``limit`` bars)."""
    kind = classify_symbol(symbol)
    if kind == "crypto":
        df = _fetch_crypto(symbol, timeframe=timeframe, exchange_id=exchange_id, limit=limit)
    else:
        df = _fetch_yf(symbol, timeframe=timeframe, limit=limit)
    df = df.sort_index()
    # Drop any bars in the future / duplicates.
    df = df[~df.index.duplicated(keep="last")]
    cutoff = datetime.now(tz=UTC) + timedelta(minutes=5)
    df = df[df.index <= cutoff]
    return MarketBars(symbol=symbol, timeframe=timeframe, kind=kind, df=df)
