"""One-shot report runner: post the daily report to a Discord webhook and exit.

Designed for GitHub Actions cron (no always-on bot needed). Posts one Discord
embed + chart per symbol via the ``DISCORD_WEBHOOK_URL`` environment variable.

Usage:

    python -m trading_bot.oneshot           # post every symbol in $SYMBOLS
    python -m trading_bot.oneshot BTC/USDT  # only post the given symbols
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys

import aiohttp
import discord

from trading_bot.config import load_settings
from trading_bot.reports.daily import build_symbol_report, report_filename

logger = logging.getLogger(__name__)


async def post_symbol(
    webhook: discord.Webhook,
    symbol: str,
    *,
    crypto_exchange: str,
) -> None:
    """Fetch + analyse + post one symbol to the Discord webhook."""
    logger.info("Building report for %s", symbol)
    report = await asyncio.to_thread(
        build_symbol_report,
        symbol,
        crypto_exchange=crypto_exchange,
    )
    filename = report_filename(symbol)
    file = discord.File(io.BytesIO(report.chart_png), filename=filename)
    await webhook.send(embed=report.embed, file=file)
    logger.info("Posted %s", symbol)


async def run(symbols: list[str] | None = None) -> int:
    """Run the one-shot pipeline. Returns 0 on full success, 1 on any failure."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL is not set")
        return 1
    settings = load_settings()
    targets = symbols or settings.symbols
    if not targets:
        logger.error("No symbols configured (SYMBOLS env var is empty)")
        return 1
    logger.info("Posting %d symbol(s): %s", len(targets), ", ".join(targets))
    failed: list[str] = []
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        for symbol in targets:
            try:
                await post_symbol(
                    webhook,
                    symbol,
                    crypto_exchange=settings.crypto_exchange,
                )
            except Exception:
                logger.exception("Failed to post %s", symbol)
                failed.append(symbol)
    if failed:
        logger.error("Finished with %d failure(s): %s", len(failed), ", ".join(failed))
        return 1
    logger.info("All symbols posted successfully")
    return 0


def main() -> None:
    args = [a for a in sys.argv[1:] if a.strip()]
    sys.exit(asyncio.run(run(args or None)))


if __name__ == "__main__":
    main()
