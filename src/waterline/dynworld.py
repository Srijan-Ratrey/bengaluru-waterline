"""Dynamic World V1 water probability (Earth Engine) on a composite's exact grid."""

import ee
import numpy as np
import shapely


def init(project: str) -> None:
    ee.Initialize(project=project)


def water_prob(geobox, start: str, end: str) -> np.ndarray:
    """Mean DW `water` probability over [start, end) per pixel of `geobox`; NaN where DW has no clear obs."""
    region = ee.Geometry(shapely.geometry.mapping(geobox.extent.to_crs("EPSG:4326").geom))
    img = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(start, end)
        .filterBounds(region)
        .select("water")
        .reduce(ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True))
    )
    a = geobox.affine
    arr = ee.data.computePixels(
        {
            "expression": img,
            "fileFormat": "NUMPY_NDARRAY",
            "grid": {
                "dimensions": {"width": geobox.shape.x, "height": geobox.shape.y},
                "affineTransform": {
                    "scaleX": a.a,
                    "shearX": a.b,
                    "translateX": a.c,
                    "shearY": a.d,
                    "scaleY": a.e,
                    "translateY": a.f,
                },
                "crsCode": f"EPSG:{geobox.crs.epsg}",
            },
        }
    )
    return np.where(arr["water_count"] > 0, arr["water_mean"], np.nan).astype("float32")
