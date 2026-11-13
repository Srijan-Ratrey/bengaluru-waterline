"""Lake-level split and hand-labelling inputs."""

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import geometry_mask

from lakewatch.lakes import SIZE_BINS

LABEL_YEARS = (2018, 2025)  # series endpoints, fixed before any labels exist
CLASSES = ("water", "veg")  # drawn as polygons; anything else inside the lake region is land
LAND, WATER, VEG = 0, 1, 2
# 6 test / 4 val / 7 train per 17 lakes walked in stratum order -> 12/8/14 for 34 lakes.
PATTERN = ["test", "train", "val", "test", "train", "test", "train", "val", "test",
           "train", "test", "train", "val", "test", "train", "val", "train"]  # fmt: skip


def split(lakes: pd.DataFrame, seed: int = 0) -> dict[str, list[str]]:
    """Lake-level test/val/train split, stratified by size bin x vegetated (median veg_frac > 0.6).

    `lakes` needs columns lake_id, area_ha, veg_frac."""
    d = lakes.assign(
        size=pd.cut(lakes["area_ha"], SIZE_BINS, right=False, labels=False),
        veg=lakes["veg_frac"] > 0.6,
        r=np.random.default_rng(seed).random(len(lakes)),
    ).sort_values(["size", "veg", "r"])
    d["set"] = np.resize(PATTERN, len(d))
    return {s: sorted(d.loc[d["set"] == s, "lake_id"]) for s in ("test", "val", "train")}


def export_8bit(c, bands: list[str], scale: float, path) -> None:
    """3-band uint8 GeoTIFF of `bands` stretched to 0..`scale` reflectance, for viewing in QGIS."""
    gb = c.odc.geobox
    arr = np.stack([np.nan_to_num(np.clip(c[b].values / scale, 0, 1)) * 255 for b in bands]).astype("uint8")
    with rasterio.open(
        path, "w", driver="GTiff", height=gb.shape.y, width=gb.shape.x, count=3, dtype="uint8",
        crs=gb.crs.to_wkt(), transform=gb.affine, photometric="RGB",
    ) as dst:  # fmt: skip
        dst.write(arr)


def rasterize(polys: gpd.GeoDataFrame, c) -> np.ndarray:
    """Hand-label polygons of one lake-year -> uint8 LAND/WATER/VEG on composite `c`'s grid.

    Veg is clipped to the lake polygon, then wins over water (docs/LABELLING.md). Pixel-centre rule."""
    gb = c.odc.geobox
    out = np.full(gb.shape, LAND, "uint8")
    for cls, val, clip in (("water", WATER, None), ("veg", VEG, c["lake"].values)):
        geoms = [shapely.make_valid(g) for g in polys.geometry[polys["class"] == cls]]
        if geoms:
            m = geometry_mask(geoms, gb.shape, gb.affine, invert=True)
            out[m if clip is None else m & clip] = val
    return out


def empty_labels(path, crs) -> None:
    """GeoPackage layer to draw in: one polygon per patch, with lake_id, year, class, annotator."""
    cols = {"lake_id": pd.Series(dtype=str), "year": pd.Series(dtype=int),
            "class": pd.Series(dtype=str), "annotator": pd.Series(dtype=str)}  # fmt: skip
    # Explicit type: an empty layer otherwise gets geometry "Unknown" and QGIS opens it as a plain table.
    gpd.GeoDataFrame(cols, geometry=gpd.GeoSeries([], crs=crs)).to_file(
        path, layer="labels", driver="GPKG", geometry_type="Polygon"
    )
