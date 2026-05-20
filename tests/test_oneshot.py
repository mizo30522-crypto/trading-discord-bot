"""Tests for the one-shot webhook poster (GitHub Actions entry point)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading_bot.oneshot import run


def _stub_report_factory():
    """Return a stand-in for ``build_symbol_report`` that yields a fake report."""
    fake_embed = MagicMock(name="Embed")
    fake_report = MagicMock(name="SymbolReport")
    fake_report.embed = fake_embed
    fake_report.chart_png = b"\x89PNG\r\n\x1a\nstub"

    def _factory(symbol: str, *, crypto_exchange: str) -> MagicMock:
        out = MagicMock(name=f"SymbolReport[{symbol}]")
        out.embed = fake_embed
        out.chart_png = b"\x89PNG\r\n\x1a\nstub"
        return out

    return _factory


def test_run_returns_1_without_webhook_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    exit_code = asyncio.run(run(["BTC/USDT"]))
    assert exit_code == 1


def test_run_posts_each_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    monkeypatch.setenv("SYMBOLS", "BTC/USDT,ETH/USDT")
    monkeypatch.setenv("CRYPTO_EXCHANGE", "kraken")

    webhook = MagicMock(name="Webhook")
    webhook.send = AsyncMock(name="send")

    with (
        patch(
            "trading_bot.oneshot.build_symbol_report",
            side_effect=_stub_report_factory(),
        ) as mock_build,
        patch(
            "trading_bot.oneshot.discord.Webhook.from_url",
            return_value=webhook,
        ),
        patch("trading_bot.oneshot.aiohttp.ClientSession") as mock_session_cls,
    ):
        mock_session = AsyncMock(name="ClientSession")
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_cls.return_value = mock_session

        exit_code = asyncio.run(run())

    assert exit_code == 0
    assert mock_build.call_count == 2
    assert webhook.send.await_count == 2
    sent_symbols = [c.kwargs.get("file").filename for c in webhook.send.await_args_list]
    assert "BTC_USDT.png" in sent_symbols
    assert "ETH_USDT.png" in sent_symbols


def test_run_continues_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")

    fake_factory = _stub_report_factory()

    def side_effect(symbol: str, *, crypto_exchange: str):
        if symbol == "BAD/SYM":
            raise RuntimeError("boom")
        return fake_factory(symbol, crypto_exchange=crypto_exchange)

    webhook = MagicMock(name="Webhook")
    webhook.send = AsyncMock(name="send")

    with (
        patch(
            "trading_bot.oneshot.build_symbol_report",
            side_effect=side_effect,
        ),
        patch(
            "trading_bot.oneshot.discord.Webhook.from_url",
            return_value=webhook,
        ),
        patch("trading_bot.oneshot.aiohttp.ClientSession") as mock_session_cls,
    ):
        mock_session = AsyncMock(name="ClientSession")
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_cls.return_value = mock_session

        exit_code = asyncio.run(run(["BTC/USDT", "BAD/SYM", "ETH/USDT"]))

    # Two symbols posted, one failed → non-zero exit.
    assert exit_code == 1
    assert webhook.send.await_count == 2
