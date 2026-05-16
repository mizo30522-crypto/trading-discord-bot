"""Configuration loaded from environment / .env file."""

from __future__ import annotations

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    discord_report_channel_id: int = Field(default=0, alias="DISCORD_REPORT_CHANNEL_ID")

    schedule_tz: str = Field(default="UTC", alias="SCHEDULE_TZ")
    schedule_time: str = Field(default="07:00", alias="SCHEDULE_TIME")

    symbols_raw: str = Field(
        default="BTC/USDT,ETH/USDT,EURUSD=X,GBPUSD=X,USDJPY=X,GC=F",
        alias="SYMBOLS",
    )
    crypto_exchange: str = Field(default="kraken", alias="CRYPTO_EXCHANGE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def symbols(self) -> list[str]:
        return [s.strip() for s in self.symbols_raw.split(",") if s.strip()]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.schedule_tz)

    @property
    def schedule_hour_minute(self) -> time:
        hh, mm = self.schedule_time.split(":")
        return time(hour=int(hh), minute=int(mm))


def load_settings(env_file: Path | None = None) -> Settings:
    """Load settings, optionally pointing at a custom env file (for tests)."""
    if env_file is not None:
        return Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    return Settings()
