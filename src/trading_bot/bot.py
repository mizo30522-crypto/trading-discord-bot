"""Discord client + slash commands.

The bot exposes:

- ``/report <symbol>``  – run an on-demand report for any supported symbol.
- ``/symbols``          – list the configured daily symbols.
- ``/ping``             – latency check.
- ``/health``           – probe upstream data sources.

It also schedules a daily job at ``SCHEDULE_TIME`` (default 07:00 UTC) that
posts a multi-asset market report to ``DISCORD_REPORT_CHANNEL_ID``.
"""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO

import discord
from discord import app_commands

from trading_bot.config import Settings
from trading_bot.reports import build_symbol_report
from trading_bot.reports.daily import report_filename
from trading_bot.scheduler import build_scheduler

logger = logging.getLogger(__name__)


class TradingBot:
    """Wrapper around :class:`discord.Client` with slash commands + scheduler."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        intents = discord.Intents.default()
        intents.message_content = False
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        self._scheduler = None
        self._register_commands()
        self._register_events()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start_bot(self) -> None:
        if not self.settings.discord_bot_token:
            raise RuntimeError(
                "DISCORD_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
            )
        async with self.client:
            await self.client.start(self.settings.discord_bot_token)

    def _register_events(self) -> None:
        @self.client.event
        async def on_ready() -> None:  # noqa: D401 - discord.py event handler
            logger.info("Logged in as %s (id=%s)", self.client.user, getattr(self.client.user, "id", "?"))
            try:
                await self.tree.sync()
                logger.info("Slash commands synced.")
            except Exception:
                logger.exception("Failed to sync slash commands")
            if self._scheduler is None:
                self._scheduler = build_scheduler(self.settings, self._daily_job)
                self._scheduler.start()

    # ------------------------------------------------------------------ #
    # daily job
    # ------------------------------------------------------------------ #

    async def _daily_job(self) -> None:
        """Post one report per configured symbol to the daily channel."""
        if not self.settings.discord_report_channel_id:
            logger.warning("DISCORD_REPORT_CHANNEL_ID not set; skipping daily job.")
            return
        channel = self.client.get_channel(self.settings.discord_report_channel_id)
        if channel is None:
            try:
                channel = await self.client.fetch_channel(self.settings.discord_report_channel_id)
            except discord.HTTPException:
                logger.exception("Could not resolve report channel.")
                return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning("Configured channel is not a text channel; got %r", channel)
            return

        await channel.send(
            content=(
                "**📊 Daily market report**\n"
                "AMT · DVA · FRVP · STDV · POI · Orderflow · Volume Profile"
            )
        )
        for symbol in self.settings.symbols:
            try:
                await self._post_report(channel, symbol)
            except Exception:
                logger.exception("Failed to post report for %s", symbol)
                try:
                    await channel.send(f":warning: Could not generate report for `{symbol}`.")
                except discord.HTTPException:
                    logger.exception("Could not send failure notice for %s", symbol)

    async def _post_report(
        self,
        channel: discord.TextChannel | discord.Thread,
        symbol: str,
    ) -> None:
        report = await asyncio.to_thread(
            build_symbol_report,
            symbol,
            crypto_exchange=self.settings.crypto_exchange,
        )
        filename = report_filename(symbol)
        file = discord.File(BytesIO(report.chart_png), filename=filename)
        await channel.send(embed=report.embed, file=file)

    # ------------------------------------------------------------------ #
    # slash commands
    # ------------------------------------------------------------------ #

    def _register_commands(self) -> None:
        @self.tree.command(name="ping", description="Latency check.")
        async def ping(interaction: discord.Interaction) -> None:
            latency_ms = round(self.client.latency * 1000)
            await interaction.response.send_message(f"Pong · {latency_ms}ms", ephemeral=True)

        @self.tree.command(
            name="symbols",
            description="List the symbols included in the daily report.",
        )
        async def symbols(interaction: discord.Interaction) -> None:
            text = "\n".join(f"• `{s}`" for s in self.settings.symbols)
            await interaction.response.send_message(
                f"**Daily symbols ({len(self.settings.symbols)})**\n{text}",
                ephemeral=True,
            )

        @self.tree.command(
            name="report",
            description="Generate an on-demand market report for a symbol.",
        )
        @app_commands.describe(symbol="e.g. BTC/USDT, EURUSD=X, GC=F")
        async def report(interaction: discord.Interaction, symbol: str) -> None:
            await interaction.response.defer(thinking=True)
            try:
                rep = await asyncio.to_thread(
                    build_symbol_report,
                    symbol,
                    crypto_exchange=self.settings.crypto_exchange,
                )
            except Exception as exc:  # noqa: BLE001 — user-facing surface
                logger.exception("on-demand report failed for %s", symbol)
                await interaction.followup.send(
                    f":warning: Could not generate report for `{symbol}`: `{exc}`",
                    ephemeral=True,
                )
                return
            filename = report_filename(symbol)
            file = discord.File(BytesIO(rep.chart_png), filename=filename)
            await interaction.followup.send(embed=rep.embed, file=file)

        @self.tree.command(
            name="health",
            description="Probe upstream data sources for the configured symbols.",
        )
        async def health(interaction: discord.Interaction) -> None:
            await interaction.response.defer(thinking=True, ephemeral=True)
            lines: list[str] = []
            for symbol in self.settings.symbols:
                try:
                    bars = await asyncio.to_thread(
                        _light_health_probe,
                        symbol,
                        self.settings.crypto_exchange,
                    )
                    lines.append(f"✅ `{symbol}` · {bars} bars")
                except Exception as exc:  # noqa: BLE001 - user-facing
                    lines.append(f"❌ `{symbol}` · `{exc}`")
            await interaction.followup.send("\n".join(lines), ephemeral=True)


def _light_health_probe(symbol: str, exchange: str) -> int:
    """Used by the /health command — fetches a small number of bars."""
    from trading_bot.data import fetch_bars

    bars = fetch_bars(symbol, timeframe="1h", limit=10, exchange_id=exchange)
    return len(bars.df)
