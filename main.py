"""Entry point for uvicorn / Fly.io.

Exposes the FastAPI ``app`` that wraps the Discord bot, so ``uvicorn main:app``
boots both the HTTP healthcheck layer and the bot itself.
"""

from trading_bot.server import app

__all__ = ["app"]
