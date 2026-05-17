"""High-density "good looking" market chart used in the daily Discord embed.

Layout (5 stacked rows sharing the time axis):
1. Candlestick price + STDV bands + POI lines + Developing VAH/VAL/POC.
2. Horizontal Fixed Range Volume Profile shown on the right edge of row 1.
3. Bar volume (bull-green / bear-red).
4. Bar delta (orderflow estimator).
5. Cumulative delta line.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle

from trading_bot.analysis import (
    POI,
    AMTResult,
    DevelopingValueArea,
    FRVPResult,
    OrderflowSummary,
    StdvBands,
    TradeSignal,
    VolumeProfile,
)
from trading_bot.render.theme import DARK_THEME, apply_dark_theme


@dataclass(frozen=True)
class ChartBundle:
    """All analysis results required to render the daily chart for a symbol."""

    symbol: str
    timeframe: str
    df: pd.DataFrame
    volume_profile: VolumeProfile
    frvp: FRVPResult
    dva: DevelopingValueArea
    stdv: StdvBands
    amt: AMTResult
    orderflow: OrderflowSummary
    poi: list[POI]
    signal: TradeSignal


def _candles(ax: plt.Axes, df: pd.DataFrame) -> None:
    bull = DARK_THEME["bull"]
    bear = DARK_THEME["bear"]
    times = mdates.date2num(df.index.to_pydatetime())
    width = float(np.median(np.diff(times))) * 0.7 if len(times) >= 2 else 1.0 / 24 / 2
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    for i, t in enumerate(times):
        color = bull if c[i] >= o[i] else bear
        ax.vlines(t, lo[i], h[i], color=color, linewidth=0.8, zorder=2)
        body_low = min(o[i], c[i])
        body_h = abs(c[i] - o[i])
        if body_h <= 0:
            body_h = (h[i] - lo[i]) * 0.001 if h[i] > lo[i] else 1e-6
        rect = Rectangle(
            (t - width / 2, body_low),
            width,
            body_h,
            facecolor=color,
            edgecolor=color,
            linewidth=0.6,
            alpha=0.9,
            zorder=3,
        )
        ax.add_patch(rect)


def _frvp_panel(ax: plt.Axes, profile: VolumeProfile) -> None:
    centers = profile.bin_centers
    vols = profile.bin_volumes
    max_v = vols.max() if vols.size and vols.max() > 0 else 1.0
    widths = vols / max_v
    poc_idx = int(np.argmax(vols)) if vols.size else 0
    for i, (cy, w) in enumerate(zip(centers, widths, strict=True)):
        within_va = profile.val <= cy <= profile.vah
        color = DARK_THEME["poc"] if i == poc_idx else (
            DARK_THEME["frvp"] if within_va else DARK_THEME["muted"]
        )
        alpha = 1.0 if i == poc_idx else (0.85 if within_va else 0.55)
        bin_height = (profile.bin_edges[i + 1] - profile.bin_edges[i]) * 0.9
        ax.barh(cy, w, height=bin_height, color=color, alpha=alpha, edgecolor="none")
    ax.set_xlim(0, 1.05)
    ax.set_xticks([])
    ax.tick_params(axis="y", labelleft=False, labelright=True, right=True)
    ax.set_title("FRVP", color=DARK_THEME["muted"], fontsize=9, loc="left")


def _draw_horizontal(
    ax: plt.Axes,
    price: float,
    *,
    color: str,
    label: str,
    linestyle: str = "--",
    alpha: float = 0.9,
) -> None:
    ax.axhline(price, color=color, linestyle=linestyle, linewidth=1.0, alpha=alpha)
    # Place the inline label on the left edge of the price panel (the FRVP panel
    # occupies the right edge so right-anchored text would be clipped).
    ax.text(
        0.005,
        price,
        f"{label} {price:.5g} ",
        transform=ax.get_yaxis_transform(),
        color=color,
        fontsize=7,
        va="center",
        ha="left",
        alpha=alpha,
        bbox={"facecolor": DARK_THEME["panel"], "edgecolor": "none", "alpha": 0.55, "pad": 1.0},
    )


def _draw_signal(ax: plt.Axes, sig: TradeSignal) -> None:
    """Overlay the trade plan (entry zone, SL, TP1/TP2/TP3) on the price axis."""
    if sig.bias == "NEUTRAL":
        return
    # entry zone as a translucent band
    lo = min(sig.entry_low, sig.entry_high)
    hi = max(sig.entry_low, sig.entry_high)
    ax.axhspan(lo, hi, color=DARK_THEME["trade_zone"], alpha=0.18, zorder=1)
    _draw_horizontal(
        ax,
        sig.entry,
        color=DARK_THEME["trade_entry"],
        label=f"ENTRY {sig.bias}",
        linestyle="-",
        alpha=0.95,
    )
    _draw_horizontal(
        ax,
        sig.stop_loss,
        color=DARK_THEME["trade_sl"],
        label="SL",
        linestyle="-",
        alpha=0.95,
    )
    for idx, target, color in [
        (1, sig.tp1, DARK_THEME["trade_tp1"]),
        (2, sig.tp2, DARK_THEME["trade_tp2"]),
        (3, sig.tp3, DARK_THEME["trade_tp3"]),
    ]:
        _draw_horizontal(
            ax,
            target.price,
            color=color,
            label=f"TP{idx} {target.source} R:R {target.rr:.1f}",
            linestyle="-",
            alpha=0.85,
        )


def _format_x(ax: plt.Axes, span_hours: float) -> None:
    if span_hours <= 48:
        loc = mdates.HourLocator(interval=max(1, int(span_hours // 12)))
        fmt = mdates.DateFormatter("%H:%M")
    elif span_hours <= 24 * 14:
        loc = mdates.DayLocator(interval=max(1, int(span_hours // 24 // 12)))
        fmt = mdates.DateFormatter("%m-%d")
    else:
        loc = mdates.WeekdayLocator()
        fmt = mdates.DateFormatter("%m-%d")
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(fmt)


def render_market_chart(bundle: ChartBundle) -> bytes:
    """Render the full daily chart for one symbol; return PNG bytes."""
    apply_dark_theme()
    df = bundle.df
    fig = plt.figure(figsize=(12, 9), dpi=140)
    gs = GridSpec(
        nrows=4,
        ncols=2,
        figure=fig,
        width_ratios=[5.0, 1.0],
        height_ratios=[3.2, 0.9, 0.9, 0.9],
        hspace=0.08,
        wspace=0.04,
    )
    ax_price = fig.add_subplot(gs[0, 0])
    ax_frvp = fig.add_subplot(gs[0, 1], sharey=ax_price)
    ax_vol = fig.add_subplot(gs[1, 0], sharex=ax_price)
    ax_delta = fig.add_subplot(gs[2, 0], sharex=ax_price)
    ax_cumd = fig.add_subplot(gs[3, 0], sharex=ax_price)
    # the right column under FRVP stays empty for visual breathing room
    ax_blank = fig.add_subplot(gs[1:, 1])
    ax_blank.axis("off")

    title = f"{bundle.symbol}  ·  {bundle.timeframe}  ·  AMT: {bundle.amt.label}"
    ax_price.set_title(title, loc="left", pad=12)
    ax_price.grid(True, axis="y", alpha=0.35)

    _candles(ax_price, df)

    for price, color, label, alpha in [
        (bundle.stdv.upper_2, DARK_THEME["sigma2"], "+2σ", 0.5),
        (bundle.stdv.upper_1, DARK_THEME["sigma1"], "+1σ", 0.5),
        (bundle.stdv.poc, DARK_THEME["poc"], "POC", 0.95),
        (bundle.stdv.lower_1, DARK_THEME["sigma1"], "-1σ", 0.5),
        (bundle.stdv.lower_2, DARK_THEME["sigma2"], "-2σ", 0.5),
    ]:
        _draw_horizontal(ax_price, price, color=color, label=label, alpha=alpha)

    _draw_horizontal(ax_price, bundle.frvp.profile.vah, color=DARK_THEME["vah"], label="VAH")
    _draw_horizontal(ax_price, bundle.frvp.profile.val, color=DARK_THEME["val"], label="VAL")

    for poi in bundle.poi:
        color = (
            DARK_THEME["poi_res"]
            if poi.kind == "resistance"
            else DARK_THEME["poi_sup"]
            if poi.kind == "support"
            else DARK_THEME["poi_lvl"]
        )
        _draw_horizontal(ax_price, poi.price, color=color, label=poi.name, linestyle=":", alpha=0.7)

    if len(bundle.dva.poc) > 1:
        ax_price.plot(
            bundle.dva.timestamps,
            bundle.dva.poc,
            color=DARK_THEME["poc"],
            linewidth=1.0,
            alpha=0.6,
            label="Developing POC",
        )
        ax_price.plot(
            bundle.dva.timestamps,
            bundle.dva.vah,
            color=DARK_THEME["vah"],
            linewidth=0.8,
            alpha=0.4,
            label="Developing VAH",
        )
        ax_price.plot(
            bundle.dva.timestamps,
            bundle.dva.val,
            color=DARK_THEME["val"],
            linewidth=0.8,
            alpha=0.4,
            label="Developing VAL",
        )
        ax_price.legend(
            loc="upper right",
            frameon=False,
            fontsize=7,
            bbox_to_anchor=(0.995, 0.995),
        )

    _draw_signal(ax_price, bundle.signal)

    _frvp_panel(ax_frvp, bundle.frvp.profile)

    bull = DARK_THEME["bull"]
    bear = DARK_THEME["bear"]
    colors = [bull if c >= o else bear for o, c in zip(df["open"], df["close"], strict=True)]
    times = mdates.date2num(df.index.to_pydatetime())
    bw = float(np.median(np.diff(times))) * 0.7 if len(times) >= 2 else 1.0 / 24 / 2
    ax_vol.bar(times, df["volume"].to_numpy(dtype=float), width=bw, color=colors, alpha=0.85)
    ax_vol.set_ylabel("Vol", color=DARK_THEME["muted"])
    ax_vol.grid(True, axis="y", alpha=0.25)

    delta_series = bundle.orderflow.delta_series.reindex(df.index, fill_value=0.0)
    d_colors = [DARK_THEME["delta_pos"] if v >= 0 else DARK_THEME["delta_neg"] for v in delta_series]
    ax_delta.bar(times, delta_series.to_numpy(dtype=float), width=bw, color=d_colors, alpha=0.9)
    ax_delta.axhline(0, color=DARK_THEME["muted"], linewidth=0.6)
    ax_delta.set_ylabel("Δ", color=DARK_THEME["muted"])
    ax_delta.grid(True, axis="y", alpha=0.25)

    cum = delta_series.cumsum().to_numpy(dtype=float)
    ax_cumd.plot(times, cum, color=DARK_THEME["accent"], linewidth=1.2)
    ax_cumd.axhline(0, color=DARK_THEME["muted"], linewidth=0.6)
    ax_cumd.set_ylabel("ΣΔ", color=DARK_THEME["muted"])
    ax_cumd.grid(True, axis="y", alpha=0.25)
    ax_cumd.fill_between(
        times,
        cum,
        0,
        where=cum >= 0,
        interpolate=True,
        color=DARK_THEME["delta_pos"],
        alpha=0.15,
    )
    ax_cumd.fill_between(
        times,
        cum,
        0,
        where=cum < 0,
        interpolate=True,
        color=DARK_THEME["delta_neg"],
        alpha=0.15,
    )

    span_hours = (df.index[-1] - df.index[0]).total_seconds() / 3600.0
    _format_x(ax_cumd, span_hours=span_hours)
    for ax in (ax_price, ax_vol, ax_delta):
        ax.tick_params(axis="x", labelbottom=False)

    fig.text(
        0.01,
        0.005,
        f"AMT: {bundle.amt.label}  ·  Orderflow bias: {bundle.orderflow.bias} "
        f"({bundle.orderflow.bias_strength * 100:.1f}%)  ·  bars={len(df)}",
        color=DARK_THEME["muted"],
        fontsize=8,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=DARK_THEME["bg"])
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
