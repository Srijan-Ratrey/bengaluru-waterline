"""Water indices, thresholds and area."""

import numpy as np
from skimage.filters import threshold_otsu

PIXEL_HA = 10 * 10 / 10_000


def ndwi(c):
    """McFeeters NDWI: (Green - NIR) / (Green + NIR)."""
    return (c["B03"] - c["B08"]) / (c["B03"] + c["B08"])


def mndwi(c):
    """Xu MNDWI: (Green - SWIR1) / (Green + SWIR1)."""
    return (c["B03"] - c["B11"]) / (c["B03"] + c["B11"])


def threshold(index, inside, method: str = "otsu") -> float:
    """Fixed 0, or Otsu over the valid pixels inside the lake region."""
    if method == "zero":
        return 0.0
    vals = np.asarray(index)[np.asarray(inside) & np.isfinite(np.asarray(index))]
    return float(threshold_otsu(vals))


def area_ha(water) -> float:
    return float(np.asarray(water).sum()) * PIXEL_HA
