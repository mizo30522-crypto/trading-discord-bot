"""Volume-weighted standard deviation bands around the POC.

This is the "STDV" component of the report — a volume-weighted standard
deviation of traded price gives bands at ±1σ / ±2σ around the POC, which act
as statistical envelopes for the value area.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StdvBands:
    """Volume-weighted standard deviation bands centred on the POC."""

    poc: float
    sigma: float
    upper_1: float
    lower_1: float
    upper_2: float
    lower_2: float
    upper_3: float
    lower_3: float

    def as_dict(self) -> dict[str, float]:
        return {
            "poc": self.poc,
            "sigma": self.sigma,
            "+1σ": self.upper_1,
            "-1σ": self.lower_1,
            "+2σ": self.upper_2,
            "-2σ": self.lower_2,
            "+3σ": self.upper_3,
            "-3σ": self.lower_3,
        }


def _typical_price(df: pd.DataFrame) -> np.ndarray:
    return ((df["high"] + df["low"] + df["close"]) / 3.0).to_numpy(dtype=float)


def volume_weighted_stdv_bands(df: pd.DataFrame) -> StdvBands:
    """Compute σ bands using volume as weight on the typical price."""
    if df.empty:
        raise ValueError("Cannot compute STDV on an empty frame.")
    tp = _typical_price(df)
    weights = df["volume"].to_numpy(dtype=float)
    total = weights.sum()
    if total <= 0:
        # No volume info — fall back to unweighted price stats so we still
        # return something usable.
        weights = np.ones_like(tp)
        total = weights.sum()
    mean = float(np.sum(tp * weights) / total)
    var = float(np.sum(weights * (tp - mean) ** 2) / total)
    sigma = float(np.sqrt(max(var, 0.0)))
    return StdvBands(
        poc=mean,
        sigma=sigma,
        upper_1=mean + sigma,
        lower_1=mean - sigma,
        upper_2=mean + 2 * sigma,
        lower_2=mean - 2 * sigma,
        upper_3=mean + 3 * sigma,
        lower_3=mean - 3 * sigma,
    )
