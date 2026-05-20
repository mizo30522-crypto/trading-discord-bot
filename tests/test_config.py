from __future__ import annotations

from datetime import time

import pytest

from trading_bot.config import Settings


def test_symbols_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYMBOLS", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "BTC/USDT" in s.symbols
    assert "EURUSD=X" in s.symbols
    assert "GC=F" in s.symbols


def test_schedule_time_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULE_TIME", "07:30")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.schedule_hour_minute == time(7, 30)
    assert s.schedule_times == [time(7, 30)]


def test_schedule_time_multiple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULE_TIME", "06:00, 07:00 , 08:15")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.schedule_times == [time(6, 0), time(7, 0), time(8, 15)]
    assert s.schedule_hour_minute == time(6, 0)


def test_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULE_TZ", "Europe/London")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert str(s.tz) == "Europe/London"


def test_log_level_uppercased(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.log_level == "DEBUG"
