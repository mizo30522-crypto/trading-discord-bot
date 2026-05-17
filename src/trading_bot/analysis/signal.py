"""Trade signal generation: bias, entry, stop-loss, TP1/TP2/TP3 with R:R.

This module composes the outputs of the existing analysis modules into a
concrete trade idea — *not* financial advice, just a mechanical reading of the
auction:

    bias         <- AMT day type + price location relative to value area + orderflow
    entry zone   <- nearest support (long) / resistance (short) inside the value area
    stop loss    <- beyond the opposite VA edge / σ band, with an ATR cushion
    take profits <- POC → VAH/VAL → ±1σ/±2σ → prior-day extreme, sorted by distance

Quality grading:

- ``high``   : AMT direction and orderflow bias align with the trade.
- ``medium`` : one of those signals is neutral / balanced.
- ``low``    : the trade is anti-trend, anti-flow, or against a tight range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from trading_bot.analysis.amt import AMTResult
from trading_bot.analysis.orderflow import OrderflowSummary
from trading_bot.analysis.poi import POI
from trading_bot.analysis.stdv import StdvBands
from trading_bot.analysis.volume_profile import VolumeProfile

Bias = Literal["LONG", "SHORT", "NEUTRAL"]
Quality = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Target:
    """A take-profit level with its structural source and risk:reward."""

    price: float
    source: str
    rr: float


@dataclass(frozen=True)
class TradeSignal:
    """A complete trade idea: bias + entry zone + stop + 3 take profits."""

    bias: Bias
    entry: float
    entry_low: float
    entry_high: float
    stop_loss: float
    tp1: Target
    tp2: Target
    tp3: Target
    quality: Quality
    rationale: str

    @property
    def risk_pct(self) -> float:
        if self.bias == "LONG":
            return (self.entry - self.stop_loss) / self.entry * 100.0
        if self.bias == "SHORT":
            return (self.stop_loss - self.entry) / self.entry * 100.0
        return 0.0

    @property
    def targets(self) -> tuple[Target, Target, Target]:
        return (self.tp1, self.tp2, self.tp3)


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < 2:
        return 0.0
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    tr = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ]
    )
    if tr.size == 0:
        return 0.0
    return float(np.mean(tr[-min(period, tr.size):]))


def _classify_bias(
    last_close: float,
    amt: AMTResult,
    vp: VolumeProfile,
    flow: OrderflowSummary,
) -> tuple[Bias, list[str]]:
    """Pick a directional bias and return it with a rationale trail."""
    notes: list[str] = []
    day_type = amt.day_type

    if day_type == "trend_up":
        notes.append("AMT trend-up day → long bias.")
        return "LONG", notes
    if day_type == "trend_down":
        notes.append("AMT trend-down day → short bias.")
        return "SHORT", notes

    if day_type == "normal_variation":
        if last_close > vp.poc:
            notes.append("Normal-variation day with close above POC → long bias.")
            return "LONG", notes
        notes.append("Normal-variation day with close below POC → short bias.")
        return "SHORT", notes

    if day_type == "normal":
        # Range extension on one side without an opposite drive — trade with it
        # if flow agrees, otherwise mean-revert toward POC.
        if last_close > vp.vah:
            if flow.bias == "bullish":
                notes.append("Above VAH on a normal day with bullish flow → long.")
                return "LONG", notes
            notes.append("Above VAH on a normal day → mean-revert short toward POC.")
            return "SHORT", notes
        if last_close < vp.val:
            if flow.bias == "bearish":
                notes.append("Below VAL on a normal day with bearish flow → short.")
                return "SHORT", notes
            notes.append("Below VAL on a normal day → mean-revert long toward POC.")
            return "LONG", notes
        # Inside VA — follow flow if any, otherwise neutral
        if flow.bias == "bullish":
            notes.append("Inside VA on a normal day, bullish flow → long.")
            return "LONG", notes
        if flow.bias == "bearish":
            notes.append("Inside VA on a normal day, bearish flow → short.")
            return "SHORT", notes
        notes.append("Inside VA on a normal day with balanced flow → no edge.")
        return "NEUTRAL", notes

    # Neutral / non-trend / anything else: mean-revert toward POC from
    # the value area edge that is currently closest to price.
    if last_close < vp.poc:
        notes.append(
            f"{amt.label}: price below POC, range trade long toward POC.",
        )
        return "LONG", notes
    if last_close > vp.poc:
        notes.append(
            f"{amt.label}: price above POC, range trade short toward POC.",
        )
        return "SHORT", notes
    notes.append(f"{amt.label}: price at POC, no clean edge.")
    return "NEUTRAL", notes


def _is_continuation(bias: Bias, amt: AMTResult) -> bool:
    """True iff the trade direction matches the AMT day's auction direction."""
    if bias == "LONG" and amt.day_type in {"trend_up", "normal_variation"}:
        return amt.session_close >= amt.session_open
    if bias == "SHORT" and amt.day_type in {"trend_down", "normal_variation"}:
        return amt.session_close <= amt.session_open
    return False


def _clamp_sl(side: Bias, entry: float, structural_sl: float, atr: float, k: float) -> float:
    """Clamp the structural SL between 0.5*ATR (minimum cushion) and ``k``*ATR."""
    min_cushion = 0.5 * atr
    max_cushion = max(k * atr, min_cushion + 1e-9)
    if side == "LONG":
        near_sl = entry - min_cushion  # closest allowed (above)
        far_sl = entry - max_cushion   # furthest allowed (below)
        return float(max(far_sl, min(structural_sl, near_sl)))
    near_sl = entry + min_cushion
    far_sl = entry + max_cushion
    return float(min(far_sl, max(structural_sl, near_sl)))


def _grade(bias: Bias, amt: AMTResult, flow: OrderflowSummary) -> Quality:
    if bias == "NEUTRAL":
        return "low"
    aligned = (
        (bias == "LONG" and flow.bias == "bullish")
        or (bias == "SHORT" and flow.bias == "bearish")
    )
    counter = (
        (bias == "LONG" and flow.bias == "bearish")
        or (bias == "SHORT" and flow.bias == "bullish")
    )
    directional_day = amt.day_type in {"trend_up", "trend_down", "normal_variation"}
    if aligned and directional_day:
        return "high"
    if counter and directional_day:
        return "low"
    if aligned or directional_day:
        return "medium"
    return "low"


def _candidate_levels(
    side: Bias,
    last_close: float,
    vp: VolumeProfile,
    stdv: StdvBands,
    poi: list[POI],
) -> list[tuple[float, str]]:
    """Collect every structural level beyond ``last_close`` on the trade side."""
    cands: list[tuple[float, str]] = []
    base = [
        (vp.poc, "POC"),
        (vp.vah, "VAH"),
        (vp.val, "VAL"),
        (stdv.upper_1, "+1σ"),
        (stdv.upper_2, "+2σ"),
        (stdv.lower_1, "-1σ"),
        (stdv.lower_2, "-2σ"),
    ]
    cands.extend(base)
    for p in poi:
        cands.append((p.price, p.name))
    if side == "LONG":
        return [(price, lbl) for price, lbl in cands if price > last_close]
    return [(price, lbl) for price, lbl in cands if price < last_close]


def _pick_three(
    candidates: list[tuple[float, str]],
    reference: float,
    min_separation: float,
    min_from_reference: float,
) -> list[tuple[float, str]]:
    """Pick up to three targets that are usefully far from ``reference`` and each other."""
    ordered = sorted(candidates, key=lambda c: abs(c[0] - reference))
    picked: list[tuple[float, str]] = []
    for price, label in ordered:
        if abs(price - reference) < min_from_reference:
            continue
        if any(abs(price - p[0]) < min_separation for p in picked):
            continue
        picked.append((price, label))
        if len(picked) >= 3:
            break
    return picked


def _fallback_target(side: Bias, reference: float, atr: float, idx: int) -> tuple[float, str]:
    """Synthesise a target at ``reference ± idx*ATR`` when structure runs out."""
    step = max(atr, abs(reference) * 0.002) * (idx + 1)
    if side == "LONG":
        return reference + step, f"+{idx + 1} ATR"
    return reference - step, f"-{idx + 1} ATR"


def compute_signal(
    df: pd.DataFrame,
    *,
    amt: AMTResult,
    vp: VolumeProfile,
    stdv: StdvBands,
    flow: OrderflowSummary,
    poi: list[POI],
) -> TradeSignal:
    """Compute a :class:`TradeSignal` from the analysis bundle."""
    if df.empty:
        raise ValueError("Cannot compute a trade signal on an empty frame.")
    last_close = float(df["close"].iloc[-1])
    atr = _atr(df, period=14) or max(abs(last_close) * 0.002, 1e-6)
    bias, notes = _classify_bias(last_close, amt, vp, flow)
    quality = _grade(bias, amt, flow)

    continuation = _is_continuation(bias, amt)
    sl_atr_multiple = 2.0 if continuation else 3.0
    if bias == "LONG":
        if continuation:
            entry = last_close
            entry_low = last_close - 0.3 * atr
            entry_high = last_close + 0.3 * atr
            structural_sl = min(
                stdv.lower_1,
                vp.val,
            ) - 0.3 * atr
        else:
            entry_low = min(vp.val, stdv.lower_1, last_close)
            entry_high = last_close
            entry = (entry_low + entry_high) / 2.0
            structural_sl = min(vp.val, stdv.lower_2) - 0.5 * atr
        stop_loss = _clamp_sl("LONG", entry, structural_sl, atr, sl_atr_multiple)
    elif bias == "SHORT":
        if continuation:
            entry = last_close
            entry_low = last_close - 0.3 * atr
            entry_high = last_close + 0.3 * atr
            structural_sl = max(
                stdv.upper_1,
                vp.vah,
            ) + 0.3 * atr
        else:
            entry_high = max(vp.vah, stdv.upper_1, last_close)
            entry_low = last_close
            entry = (entry_low + entry_high) / 2.0
            structural_sl = max(vp.vah, stdv.upper_2) + 0.5 * atr
        stop_loss = _clamp_sl("SHORT", entry, structural_sl, atr, sl_atr_multiple)
    else:
        # NEUTRAL: still emit a degenerate "stand aside" signal so the rest of
        # the report can render. Use the closer VA edge as a no-op entry.
        entry_low = vp.val
        entry_high = vp.vah
        entry = vp.poc
        stop_loss = vp.poc
        zero = Target(price=vp.poc, source="POC", rr=0.0)
        notes.append("No actionable setup; stand aside.")
        return TradeSignal(
            bias="NEUTRAL",
            entry=entry,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            tp1=zero,
            tp2=zero,
            tp3=zero,
            quality="low",
            rationale=" ".join(notes),
        )

    risk = abs(entry - stop_loss)
    candidates = _candidate_levels(bias, entry, vp, stdv, poi)
    picks = _pick_three(
        candidates,
        reference=entry,
        min_separation=0.5 * atr,
        min_from_reference=1.0 * atr,
    )
    while len(picks) < 3:
        anchor = picks[-1][0] if picks else entry
        picks.append(_fallback_target(bias, anchor, atr, len(picks)))

    targets: list[Target] = []
    for price, src in picks:
        rr = abs(price - entry) / risk if risk > 0 else 0.0
        targets.append(Target(price=price, source=src, rr=rr))

    style = "trend-continuation" if continuation else "mean-reversion"
    notes.append(
        f"{style}: ATR(14)={atr:.5g}, entry={entry:.5g}, SL={stop_loss:.5g}, risk={risk:.5g}"
    )

    return TradeSignal(
        bias=bias,
        entry=entry,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        tp1=targets[0],
        tp2=targets[1],
        tp3=targets[2],
        quality=quality,
        rationale=" ".join(notes),
    )


__all__ = ["Bias", "Quality", "Target", "TradeSignal", "compute_signal"]
