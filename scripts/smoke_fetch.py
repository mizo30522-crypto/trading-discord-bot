"""Smoke-test data fetching for every configured symbol."""

from __future__ import annotations

from trading_bot.config import load_settings
from trading_bot.data import fetch_bars


def main() -> int:
    settings = load_settings()
    failures: list[tuple[str, str]] = []
    for symbol in settings.symbols:
        try:
            bars = fetch_bars(
                symbol,
                timeframe="1h",
                limit=24,
                exchange_id=settings.crypto_exchange,
            )
            last = bars.df["close"].iloc[-1]
            print(f"OK   {symbol:14s} bars={len(bars.df):3d} last={last:.5g}")
        except Exception as exc:  # noqa: BLE001 - this is a probe script
            print(f"FAIL {symbol:14s} {exc!r}")
            failures.append((symbol, str(exc)))
    if failures:
        print(f"\n{len(failures)} symbol(s) failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
