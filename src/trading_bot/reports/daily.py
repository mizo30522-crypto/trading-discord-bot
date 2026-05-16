"""Build a per-symbol report (analysis + chart + Discord embed)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import discord
import pandas as pd

from trading_bot.analysis import (
    classify_amt,
    developing_value_area,
    estimate_orderflow,
    find_points_of_interest,
    fixed_range_volume_profile,
    volume_profile,
    volume_weighted_stdv_bands,
)
from trading_bot.data import MarketBars, fetch_bars
from trading_bot.render.charts import ChartBundle, render_market_chart
from trading_bot.render.theme import DARK_THEME

logger = logging.getLogger(__name__)

_TIMEFRAME_FOR_KIND = {
    "crypto": "1h",
    "fx_or_commodity": "1h",
}
_LIMIT_FOR_KIND = {
    "crypto": 24 * 14,  # ~2 weeks of hourly crypto bars
    "fx_or_commodity": 24 * 14,
}
_BIAS_EMOJI = {"bullish": "🟢", "bearish": "🔴", "balanced": "🟡"}
_DAY_TYPE_EMOJI = {
    "trend_up": "🚀",
    "trend_down": "🔻",
    "normal_variation": "🌀",
    "normal": "⚖️",
    "neutral": "⚪",
    "non_trend": "💤",
}
_EMBED_COLORS = {
    "bullish": 0x26D07C,
    "bearish": 0xFF5466,
    "balanced": 0x7C5CFF,
}


@dataclass(frozen=True)
class SymbolReport:
    """Bundle of everything we need to push one symbol to Discord."""

    symbol: str
    timeframe: str
    bars: MarketBars
    embed: discord.Embed
    chart_png: bytes


def _fmt_price(price: float) -> str:
    if abs(price) >= 1000:
        return f"{price:,.2f}"
    if abs(price) >= 10:
        return f"{price:,.3f}"
    if abs(price) >= 1:
        return f"{price:,.4f}"
    return f"{price:,.5f}"


def build_chart_bundle(bars: MarketBars) -> ChartBundle:
    """Run every analysis module on the bars and return a :class:`ChartBundle`."""
    df = bars.df
    vp = volume_profile(df, bins=64)
    frvp = fixed_range_volume_profile(df, lookback_bars=min(len(df), 24 * 5), bins=64)
    dva = developing_value_area(df, bins=32, step=max(1, len(df) // 60))
    stdv = volume_weighted_stdv_bands(df)
    amt = classify_amt(df, session_bars=min(24, len(df)))
    flow = estimate_orderflow(df, window=min(24, len(df)))
    poi = find_points_of_interest(df).levels
    return ChartBundle(
        symbol=bars.symbol,
        timeframe=bars.timeframe,
        df=df,
        volume_profile=vp,
        frvp=frvp,
        dva=dva,
        stdv=stdv,
        amt=amt,
        orderflow=flow,
        poi=poi,
    )


def build_embed(bundle: ChartBundle, *, image_filename: str) -> discord.Embed:
    """Build the Discord embed describing the bundle."""
    flow = bundle.orderflow
    amt = bundle.amt
    vp = bundle.volume_profile
    frvp = bundle.frvp.profile
    stdv = bundle.stdv
    last_close = float(bundle.df["close"].iloc[-1])
    color = _EMBED_COLORS.get(flow.bias, 0x7C5CFF)
    embed = discord.Embed(
        title=f"{bundle.symbol} · daily market report",
        description=(
            f"**Last:** `{_fmt_price(last_close)}`  ·  "
            f"**AMT:** {_DAY_TYPE_EMOJI.get(amt.day_type, '•')} {amt.label}  ·  "
            f"**Flow:** {_BIAS_EMOJI[flow.bias]} {flow.bias.title()} "
            f"({flow.bias_strength * 100:.0f}%)"
        ),
        color=color,
        timestamp=datetime.now(tz=UTC),
    )
    embed.add_field(
        name="Volume Profile",
        value=(
            f"POC `{_fmt_price(vp.poc)}`\n"
            f"VAH `{_fmt_price(vp.vah)}`\n"
            f"VAL `{_fmt_price(vp.val)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"FRVP · {bundle.frvp.bars} bars",
        value=(
            f"POC `{_fmt_price(frvp.poc)}`\n"
            f"VAH `{_fmt_price(frvp.vah)}`\n"
            f"VAL `{_fmt_price(frvp.val)}`"
        ),
        inline=True,
    )
    dva_poc, dva_vah, dva_val = bundle.dva.latest
    embed.add_field(
        name="DVA (latest)",
        value=(
            f"POC `{_fmt_price(dva_poc)}`\n"
            f"VAH `{_fmt_price(dva_vah)}`\n"
            f"VAL `{_fmt_price(dva_val)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="STDV bands",
        value=(
            f"+2σ `{_fmt_price(stdv.upper_2)}`\n"
            f"+1σ `{_fmt_price(stdv.upper_1)}`\n"
            f"μ   `{_fmt_price(stdv.poc)}`\n"
            f"-1σ `{_fmt_price(stdv.lower_1)}`\n"
            f"-2σ `{_fmt_price(stdv.lower_2)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="Orderflow",
        value=(
            f"Σ buy `{flow.buy_volume:,.0f}`\n"
            f"Σ sell `{flow.sell_volume:,.0f}`\n"
            f"ΣΔ   `{flow.cumulative_delta:+,.0f}`"
        ),
        inline=True,
    )
    if bundle.poi:
        # show the 6 POIs nearest to the current price
        ranked = sorted(bundle.poi, key=lambda p: abs(p.price - last_close))[:6]
        ranked.sort(key=lambda p: p.price, reverse=True)
        poi_text = "\n".join(
            f"{_kind_glyph(p.kind)} **{p.name}** `{_fmt_price(p.price)}`" for p in ranked
        )
        embed.add_field(name="POI (nearest)", value=poi_text, inline=False)
    embed.add_field(name="AMT rationale", value=f"```{amt.rationale}```", inline=False)
    embed.set_image(url=f"attachment://{image_filename}")
    embed.set_footer(text=f"Timeframe {bundle.timeframe}  ·  bars={len(bundle.df)}")
    _ = DARK_THEME  # keep import even if unused at runtime
    return embed


def _kind_glyph(kind: str) -> str:
    return {"resistance": "🔺", "support": "🔻", "level": "▪️"}.get(kind, "▪️")


def build_symbol_report(
    symbol: str,
    *,
    crypto_exchange: str = "binance",
) -> SymbolReport:
    """Fetch bars, run analysis, render the chart, and build the embed."""
    bars = fetch_bars(
        symbol,
        timeframe=_TIMEFRAME_FOR_KIND["crypto" if "/" in symbol else "fx_or_commodity"],
        limit=_LIMIT_FOR_KIND["crypto" if "/" in symbol else "fx_or_commodity"],
        exchange_id=crypto_exchange,
    )
    bundle = build_chart_bundle(bars)
    chart_png = render_market_chart(bundle)
    filename = _safe_filename(symbol) + ".png"
    embed = build_embed(bundle, image_filename=filename)
    return SymbolReport(
        symbol=symbol,
        timeframe=bars.timeframe,
        bars=bars,
        embed=embed,
        chart_png=chart_png,
    )


def _safe_filename(symbol: str) -> str:
    return symbol.replace("/", "_").replace("=", "_").replace(" ", "_")


def report_filename(symbol: str) -> str:
    return _safe_filename(symbol) + ".png"


# kept for re-export from reports.__init__
_ = pd
