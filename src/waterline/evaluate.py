"""Score water and water/veg/land maps against rasterized hand labels."""

import numpy as np
import pandas as pd

from waterline.indices import PIXEL_HA, area_ha, area_interval, mndwi, ndvi, ndwi
from waterline.labels import LAND, VEG, WATER

CLASSES = {"land": LAND, "water": WATER, "veg": VEG}
WATER_T = {
    "mndwi": np.round(np.arange(-0.4, 0.41, 0.05), 2),
    "ndwi": np.round(np.arange(-0.4, 0.41, 0.05), 2),
    "dw": np.round(np.arange(0.1, 0.91, 0.1), 2),
}
VEG_T = np.round(np.arange(0.1, 0.61, 0.05), 2)


def scores(c) -> dict[str, np.ndarray]:
    """Per-pixel water score per method; a pixel is water when its score > threshold."""
    return {"mndwi": mndwi(c).values, "ndwi": ndwi(c).values, "dw": c["dw_water"].values}


def classify(score, ndvi_, inside, lake, water_t: float, veg_t: float) -> np.ndarray:
    """LAND/WATER/VEG map: water anywhere in the region, veg (NDVI > veg_t, not water) only in the lake."""
    water = (score > water_t) & inside
    veg = ~water & (ndvi_ > veg_t) & lake
    return np.where(veg, VEG, np.where(water, WATER, LAND)).astype("uint8")


def score_lake_year(c, truth: np.ndarray) -> list[dict]:
    """Pixel counts for every method x water_t x veg_t: water tp/fp/fn over the lake region,
    and the 3x3 truth-by-prediction confusion over the lake polygon (columns n_<truth>_<pred>)."""
    inside, lake = c["inside"].values, c["lake"].values
    v = ndvi(c).values
    t_lake = truth[lake]
    rows = []
    for method, s in scores(c).items():
        for wt in WATER_T[method]:
            for vt in VEG_T:
                pred = classify(s, v, inside, lake, wt, vt)
                pw, tw = pred[inside] == WATER, truth[inside] == WATER
                conf = np.bincount(3 * t_lake + pred[lake], minlength=9)
                rows.append(
                    {"method": method, "water_t": wt, "veg_t": vt,
                     "tp": int((pw & tw).sum()), "fp": int((pw & ~tw).sum()), "fn": int((~pw & tw).sum())}
                    | {f"n_{a}_{b}": int(conf[3 * i + j]) for a, i in CLASSES.items() for b, j in CLASSES.items()}
                )  # fmt: skip
    return rows


def assess(c, truth: np.ndarray, method: str, water_t: float, veg_t: float, delta: float) -> dict:
    """One lake-year at a fixed config: water area + interval vs truth (lake region), and per-class
    truth / predicted / overlap pixel counts over the lake polygon."""
    inside, lake = c["inside"].values, c["lake"].values
    s = scores(c)[method]
    pred = classify(s, ndvi(c).values, inside, lake, water_t, veg_t)
    area, lo, hi = area_interval(s, inside, water_t, delta)
    tw, pw = (truth == WATER) & inside, (pred == WATER) & inside
    row = {"area_true": area_ha(tw), "area": area, "area_lo": lo, "area_hi": hi,
           "water_iou": (tw & pw).sum() / max((tw | pw).sum(), 1)}  # fmt: skip
    for k, v in CLASSES.items():
        t, p = (truth == v) & lake, (pred == v) & lake
        row |= {f"{k}_true": int(t.sum()), f"{k}_pred": int(p.sum()), f"{k}_hit": int((t & p).sum())}
    return row


def summary(a: pd.DataFrame) -> dict:
    """Headline numbers from `assess` rows (needs lake_id, year, type = clean|veg)."""
    has = a[a.area_true > 0]
    rel = ((has.area - has.area_true) / has.area_true).abs()
    out = {
        "lake_years": len(a),
        "clean_median_rel_area_error": rel[has.type == "clean"].median(),
        "veg_median_rel_area_error": rel[has.type == "veg"].median(),
        "interval_coverage": ((a.area_true >= a.area_lo) & (a.area_true <= a.area_hi)).mean(),
    }
    for k in CLASSES:  # pooled over lake-years
        hit = a[f"{k}_hit"].sum()
        out[f"iou_{k}"] = hit / (a[f"{k}_true"].sum() + a[f"{k}_pred"].sum() - hit)
    w = a.pivot(index="lake_id", columns="year", values=["area_true", "area"])
    sign = lambda col: np.sign(w[(col, 2025)] - w[(col, 2018)])
    out["trend_sign_agreement"] = (sign("area_true") == sign("area")).mean()
    return out


def metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Add water IoU / areas / relative area error and per-class IoU (lake polygon) to count rows."""
    out = df.assign(
        water_iou=df.tp / (df.tp + df.fp + df.fn).replace(0, np.nan),
        area_pred=(df.tp + df.fp) * PIXEL_HA,
        area_true=(df.tp + df.fn) * PIXEL_HA,
    )
    out["rel_err"] = (out.area_pred - out.area_true) / out.area_true.replace(0, np.nan)
    for k in CLASSES:
        hit = df[f"n_{k}_{k}"]
        t = sum(df[f"n_{k}_{b}"] for b in CLASSES)
        p = sum(df[f"n_{a}_{k}"] for a in CLASSES)
        out[f"iou_{k}"] = hit / (t + p - hit).replace(0, np.nan)
    out["iou_3class"] = out[[f"iou_{k}" for k in CLASSES]].mean(axis=1)  # mean over classes present
    return out
