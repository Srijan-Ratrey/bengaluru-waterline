"""Per-lake-year areas at the frozen method, and per-lake trends (spec 8)."""

import itertools

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, norm, rankdata

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


def trend(x: pd.DataFrame, alpha: float = 0.1) -> dict:
    """Seasonal Kendall test (exact, by permuting whole years) and seasonal Theil-Sen slope (units/yr)
    with its (1 - alpha) CI.

    `x`: index = year (complete years only), one column per season. One column is plain Mann-Kendall.
    Seasons of the same year are not independent (both follow the previous monsoon), so the test permutes
    years with all their seasons together: a second season that only repeats the first adds no evidence.
    With one season this is the exact Mann-Kendall test."""
    years, v = x.index.to_numpy(float), x.to_numpy(float)
    n = len(years)
    i, j = np.triu_indices(n, 1)
    m = np.sign(v[None] - v[:, None]).sum(-1)  # m[a, b] = sum over seasons of sign(v[b] - v[a])
    # ponytail: exhaustive up to 9 years (362,880 orders); a fixed-seed sample of 200k beyond that.
    perms = (
        np.array(list(itertools.permutations(range(n))))
        if n <= 9
        else np.random.default_rng(0).permuted(np.tile(np.arange(n), (200_000, 1)), axis=1)
    )
    s_obs = m[i, j].sum()
    p = float((np.abs(m[perms[:, i], perms[:, j]].sum(1)) >= abs(s_obs)).mean())
    # Slope CI: rank method (as scipy.theilslopes) on all within-season slopes, with Var(S) including the
    # covariance between seasons (Hirsch & Slack 1984); its diagonal is the usual tie-corrected MK variance.
    d, r = np.sign(v[j] - v[i]), rankdata(v, axis=0)
    var = float(((d.T @ d) + 4 * (r.T @ r) - n * (n + 1) ** 2).sum() / 3)
    slopes = np.sort(((v[j] - v[i]) / (years[j] - years[i])[:, None]).ravel())
    c, k = norm.ppf(1 - alpha / 2) * np.sqrt(max(var, 0)), len(slopes)
    lo, hi = int(np.round((k - c) / 2)) - 1, int(np.round((k + c) / 2))
    return {"slope": float(np.median(slopes)), "slope_lo": slopes[max(lo, 0)],
            "slope_hi": slopes[min(hi, k - 1)], "p": p, "n_years": n}  # fmt: skip


def trends(a: pd.DataFrame, col: str, alpha: float = 0.1, possible_p: float = 0.05) -> pd.DataFrame:
    """Per-lake trend of `col` over every season in `a` (column `season`, default one season), with
    Benjamini-Hochberg q across lakes and a plain-language verdict. Years missing a season are dropped."""
    a = a if "season" in a else a.assign(season="winter")
    t = pd.DataFrame(
        {
            lake: trend(g.pivot(index="year", columns="season", values=col).dropna().sort_index(), alpha)
            for lake, g in a.groupby("lake_id")
        }
    ).T.astype(float)
    t["q"] = false_discovery_control(t.p)
    # "possibly": p < possible_p for this lake alone, but not after the correction across lakes. At
    # p < 0.05 about 1 in 20 lakes with no real change would get this label by chance.
    sure, maybe, down, up = t.q < alpha, t.p < possible_p, t.slope < 0, t.slope > 0
    t["verdict"] = np.select(
        [sure & down, sure & up, maybe & down, maybe & up],
        ["shrinking", "growing", "possibly shrinking", "possibly growing"],
        "no clear trend",
    )
    return t.rename_axis("lake_id").reset_index()
