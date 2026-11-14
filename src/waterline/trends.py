"""Per-lake-year areas at the frozen method, and per-lake trends (spec 8)."""

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, kendalltau, theilslopes

from waterline.evaluate import CLASSES, classify, scores
from waterline.indices import PIXEL_HA, area_interval, ndvi


def areas(c, method: str, water_t: float, veg_t: float, delta: float) -> dict:
    """Water area + interval over the lake region, and water/veg/land ha over the lake polygon."""
    inside, lake = c["inside"].values, c["lake"].values
    s = scores(c)[method]
    area, lo, hi = area_interval(s, inside, water_t, delta)
    pred = classify(s, ndvi(c).values, inside, lake, water_t, veg_t)[lake]
    return {"area": area, "area_lo": lo, "area_hi": hi} | {
        f"{k}_ha": float((pred == v).sum()) * PIXEL_HA for k, v in CLASSES.items()
    }


def trend(years, values, alpha: float = 0.1) -> dict:
    """Theil-Sen slope (units/yr) with its (1 - alpha) CI, and Mann-Kendall p (= Kendall tau vs time)."""
    slope, _, lo, hi = theilslopes(values, years, alpha=1 - alpha)
    tau, p = kendalltau(years, values)
    return {"slope": slope, "slope_lo": lo, "slope_hi": hi, "tau": tau, "p": p}


def trends(a: pd.DataFrame, col: str, alpha: float = 0.1) -> pd.DataFrame:
    """Per-lake trend of `col`, with Benjamini-Hochberg q across lakes and a plain-language verdict."""
    t = pd.DataFrame({lake: trend(g.year, g[col], alpha) for lake, g in a.groupby("lake_id")}).T
    t["p"] = t.p.fillna(1.0)  # constant series (e.g. always 0 ha) -> no trend
    t["q"] = false_discovery_control(t.p.astype(float))
    t["verdict"] = np.select(
        [(t.q < alpha) & (t.slope < 0), (t.q < alpha) & (t.slope > 0)],
        ["shrinking", "growing"],
        "no clear trend",
    )
    return t.rename_axis("lake_id").reset_index()
