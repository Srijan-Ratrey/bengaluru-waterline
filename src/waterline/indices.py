"""Water indices, thresholds and area."""

import numpy as np
from skimage.filters import threshold_otsu

PIXEL_HA = 10 * 10 / 10_000
DW_THRESHOLDS = (0.3, 0.5, 0.7)
NDVI_VEG = 0.3  # ponytail: fixed NDVI cut for veg_frac; tune on labelled algae-covered lakes (D13)


def ndwi(c):
    """McFeeters NDWI: (Green - NIR) / (Green + NIR)."""
    return (c["B03"] - c["B08"]) / (c["B03"] + c["B08"])


def mndwi(c):
    """Xu MNDWI: (Green - SWIR1) / (Green + SWIR1)."""
    return (c["B03"] - c["B11"]) / (c["B03"] + c["B11"])


def ndvi(c):
    return (c["B08"] - c["B04"]) / (c["B08"] + c["B04"])


def threshold(index, inside, method: str = "otsu") -> float:
    """Fixed 0, or Otsu over the valid pixels inside the lake region."""
    if method == "zero":
        return 0.0
    vals = np.asarray(index)[np.asarray(inside) & np.isfinite(np.asarray(index))]
    return float(threshold_otsu(vals))


def area_ha(water) -> float:
    return float(np.asarray(water).sum()) * PIXEL_HA


def edge_ha(water, edge_m: float = 5) -> float:
    """Mixed-pixel area: shoreline length (4-neighbour water/non-water pixel edges x 10 m) x edge_m (spec 7)."""
    w = np.asarray(water, int)
    n = np.abs(np.diff(w, axis=0)).sum() + np.abs(np.diff(w, axis=1)).sum()
    return float(n) * 10 * edge_m / 10_000


def area_interval(index, inside, t: float, delta: float) -> tuple[float, float, float]:
    """(area, lo, hi) in ha: area at threshold t; lo/hi at t +/- delta, widened by the edge term."""
    water = (index > t) & inside
    edge = edge_ha(water)
    lo = max(0.0, area_ha((index > t + delta) & inside) - edge)
    return area_ha(water), lo, area_ha((index > t - delta) & inside) + edge


def iou(a, b) -> float:
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else np.nan


def measure(c, dw) -> list[dict]:
    """One row per method for a lake-year composite `c` and Dynamic World probability `dw` (same grid)."""
    inside, lake = c["inside"].values, c["lake"].values
    masks = {}
    for name, fn in [("ndwi", ndwi), ("mndwi", mndwi)]:
        idx = fn(c).values
        for how in ("otsu", "zero"):
            masks[f"{name}_{how}"] = (idx > threshold(idx, inside, how)) & inside
    has_dw = bool(np.isfinite(dw).any())  # all-NaN when measured without Earth Engine
    for p in DW_THRESHOLDS if has_dw else ():
        masks[f"dw_{p}"] = (dw >= p) & inside
    v = ndvi(c).values[lake]
    common = {
        "valid_frac": c.attrs["valid_frac"],
        "n_scenes": c.attrs["n_scenes"],
        "dw_valid_frac": float(np.isfinite(dw[inside]).mean()),
        "veg_frac": float((v[np.isfinite(v)] > NDVI_VEG).mean()),
    }
    ref = masks.get("dw_0.5")
    return [
        {"method": m, "water_area_ha": area_ha(w), "iou_dw50": iou(w, ref) if has_dw else np.nan, **common}
        for m, w in masks.items()
    ]
