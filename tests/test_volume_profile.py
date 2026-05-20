from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.analysis.volume_profile import (
    fixed_range_volume_profile,
    volume_profile,
)


def test_poc_falls_in_busiest_band() -> None:
    # Build a frame whose volume is concentrated in the [99.5, 100.5] band.
    idx = pd.date_range("2024-01-01", periods=20, freq="1h", tz="UTC")
    rows = []
    for i in range(20):
        if i < 16:
            row = {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1000}
        else:
            row = {"open": 110.0, "high": 110.5, "low": 109.5, "close": 110.0, "volume": 50}
        rows.append(row)
    df = pd.DataFrame(rows, index=idx)
    vp = volume_profile(df, bins=40)
    assert 99.0 <= vp.poc <= 101.0
    assert vp.val <= vp.poc <= vp.vah
    assert vp.bin_volumes.sum() == pytest.approx(df["volume"].sum(), rel=1e-6)


def test_value_area_covers_target_volume() -> None:
    rng = np.random.default_rng(seed=0)
    closes = 100 + np.cumsum(rng.normal(0, 0.2, size=100))
    idx = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.3,
            "low": closes - 0.3,
            "close": closes,
            "volume": rng.uniform(500, 1500, size=100),
        },
        index=idx,
    )
    vp = volume_profile(df, bins=50, value_area_pct=0.7)
    in_va = (vp.bin_centers >= vp.val) & (vp.bin_centers <= vp.vah)
    fraction = vp.bin_volumes[in_va].sum() / vp.bin_volumes.sum()
    # The greedy expansion may slightly under-shoot the strict 70% target on the
    # last step; allow a small slack.
    assert fraction >= 0.65


def test_frvp_uses_last_window(trending_up_frame: pd.DataFrame) -> None:
    full = volume_profile(trending_up_frame, bins=32)
    frvp = fixed_range_volume_profile(trending_up_frame, lookback_bars=10, bins=32)
    assert frvp.bars == 10
    # The window is at the upper end of the trend, so its POC must be higher than
    # the overall POC.
    assert frvp.profile.poc > full.poc


def test_empty_frame_raises() -> None:
    with pytest.raises(ValueError):
        volume_profile(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
