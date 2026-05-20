"""Console entrypoint: `python -m trading_bot` or `trading-bot`."""

from __future__ import annotations

import asyncio
import logging
import sys

from trading_bot.bot import TradingBot
from trading_bot.config import load_settings


def main() -> int:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bot = TradingBot(settings)
    try:
        asyncio.run(bot.start_bot())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interrupted, shutting down.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
