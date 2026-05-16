# Trading Discord Bot

A Discord bot that posts a daily multi-asset market report on **Forex, Crypto, and Gold**
combining seven techniques:

| Abbrev. | Technique |
|---|---|
| **AMT** | Auction Market Theory — day-type classifier (trend / normal / neutral / non-trend) |
| **VP** | Volume Profile — POC, Value Area High/Low (70% volume) |
| **FRVP** | Fixed Range Volume Profile — VP over a configurable lookback window |
| **DVA** | Developing Value Area — POC/VAH/VAL evolution intraday |
| **STDV** | Volume-weighted Standard Deviation bands around the POC |
| **POI** | Points of Interest — prior session H/L, weekly extremes, value area edges, swing pivots |
| **Orderflow** | Bid/ask volume estimator + cumulative delta derived from OHLCV |

The bot renders a slick dark-theme chart per symbol and posts a rich Discord embed
containing every metric, plus the chart attached as an image.

## Features

- Runs daily at a configurable time (default **07:00 UTC**) via APScheduler.
- Slash commands: `/report <symbol>`, `/symbols`, `/ping`, `/health`.
- Crypto data via `ccxt` (Binance public API by default — no key required).
- FX & Gold data via `yfinance` (no key required).
- Pluggable symbol list via env var.
- Pure-Python analysis (numpy / pandas) — fully unit-tested.

## Quickstart

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# edit .env: set DISCORD_BOT_TOKEN and DISCORD_REPORT_CHANNEL_ID

# 3. Run
trading-bot
```

## Discord setup

1. Create a Bot at <https://discord.com/developers/applications>.
2. Enable the **Message Content Intent** (Bot → Privileged Gateway Intents).
3. Invite the bot with the `bot` and `applications.commands` scopes,
   permissions `Send Messages`, `Embed Links`, `Attach Files`.
4. Right-click the target channel in Discord → *Copy Channel ID* → put it in
   `DISCORD_REPORT_CHANNEL_ID`.

## Commands

| Command | Description |
|---|---|
| `/report <symbol>` | Render an on-demand market report for any supported symbol. |
| `/symbols` | List the symbols included in the daily schedule. |
| `/ping` | Latency check. |
| `/health` | Verifies upstream data sources are reachable. |

## Configuration

All settings come from environment variables (or a local `.env` file).
See [`.env.example`](.env.example) for the full list.

## Architecture

```
src/trading_bot/
├── bot.py             # discord.py client + slash commands
├── scheduler.py       # APScheduler daily job
├── config.py          # pydantic-settings config
├── data/              # market-data fetchers (ccxt, yfinance)
├── analysis/          # AMT, VP, FRVP, DVA, STDV, POI, Orderflow
├── render/            # matplotlib / mplfinance dark theme charts
└── reports/           # builds the Discord embed + chart per symbol
```

## Testing

```bash
pytest -q
ruff check .
```

## License

MIT
