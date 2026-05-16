from __future__ import annotations

import pandas as pd

from trading_bot.analysis.dva import developing_value_area
from trading_bot.analysis.poi import find_points_of_interest


def test_developing_value_area_is_monotone_in_length(trending_up_frame: pd.DataFrame) -> None:
    dva = developing_value_area(trending_up_frame, bins=24, min_bars=5, step=1)
    assert len(dva.poc) >= 5
    assert dva.poc[-1] >= dva.poc[0]  # POC drifts up in an up-trend


def test_poi_contains_prior_day_levels(two_day_frame: pd.DataFrame) -> None:
    bundle = find_points_of_interest(two_day_frame)
    names = {p.name for p in bundle.levels}
    assert "Prior Day High" in names
    assert "Prior Day Low" in names


def test_poi_handles_short_history(trending_up_frame: pd.DataFrame) -> None:
    bundle = find_points_of_interest(trending_up_frame.head(3))
    # A 3-row frame should still return something (possibly empty) without raising.
    assert isinstance(bundle.levels, list)
