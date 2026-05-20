"""FastAPI healthcheck wrapper for 24/7 deployment.

The Discord bot is a long-running background asyncio task started during the
FastAPI app's lifespan. The HTTP layer exists purely so a cloud host (Fly.io,
Render, etc.) sees the process as a healthy web service.

Endpoints:

- ``GET /``        : minimal liveness probe.
- ``GET /health``  : returns bot status (logged_in flag, configured symbols).
- ``GET /status``  : same as /health plus latency.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import FastAPI

from trading_bot.bot import TradingBot
from trading_bot.config import load_settings

logger = logging.getLogger(__name__)


class _BotRunner:
    """Owns the TradingBot and the background task that runs it."""

    def __init__(self) -> None:
        self.settings = load_settings()
        self.bot: TradingBot | None = None
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.task is not None and not self.task.done():
            return
        self.bot = TradingBot(self.settings)
        self.task = asyncio.create_task(self.bot.start_bot(), name="trading-bot")

    async def stop(self) -> None:
        if self.bot is not None:
            with contextlib.suppress(Exception):
                await self.bot.client.close()
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task

    def snapshot(self) -> dict[str, Any]:
        client = self.bot.client if self.bot else None
        user = getattr(client, "user", None) if client else None
        times = [
            f"{t.hour:02d}:{t.minute:02d}" for t in self.settings.schedule_times
        ]
        return {
            "logged_in": bool(user is not None),
            "bot_user": str(user) if user else None,
            "guilds": [g.name for g in getattr(client, "guilds", [])] if client else [],
            "symbols": self.settings.symbols,
            "schedule": f"{', '.join(times)} {self.settings.schedule_tz}",
            "schedule_times": times,
            "latency_ms": (
                round(client.latency * 1000)
                if client and not client.is_closed()
                else None
            ),
        }


_runner = _BotRunner()


def _make_app() -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        await _runner.start()
        try:
            yield
        finally:
            await _runner.stop()

    app = FastAPI(
        title="Trading Discord Bot",
        version="0.1.0",
        description=(
            "HTTP healthcheck wrapper for the trading Discord bot. The bot "
            "itself runs in the background; this HTTP layer only exists so "
            "cloud platforms can probe liveness."
        ),
        lifespan=lifespan,
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok", "service": "trading-discord-bot"}

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return _runner.snapshot()

    @app.get("/status")
    async def status() -> dict[str, Any]:
        return _runner.snapshot()

    return app


app = _make_app()
