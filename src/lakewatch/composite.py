"""Cloud-masked, offset-corrected seasonal median composite around one lake."""

import odc.stac
import xarray as xr
from rasterio.features import geometry_mask

BANDS = ["B02", "B03", "B04", "B08", "B11"]
# ESA L2A SCL classes to drop: no data, saturated, cloud shadow, cloud medium/high, cirrus.
# Class codes aren't in Planetary Computer's metadata; these follow the ESA product spec.
# ponytail: class 2 (dark area) is kept because dark water lands there in older baselines; revisit if shadows leak in.
INVALID_SCL = [0, 1, 3, 8, 9, 10]
CRS = "EPSG:32643"
RES = 10  # m


def to_reflectance(dn: xr.DataArray, offset: int) -> xr.DataArray:
    """DN -> surface reflectance; DN 0 is no data."""
    return ((dn.where(dn != 0) + offset) / 10_000).astype("float32")


def composite(items: list, offsets: list[int], geom_utm, buffer_m: float = 150) -> xr.Dataset:
    """Median reflectance per band over valid observations, plus `n_valid` per pixel and `inside` mask."""
    region = geom_utm.buffer(buffer_m)
    bbox = region.bounds
    scenes = []
    for item, offset in zip(items, offsets):
        ds = odc.stac.load(
            [item],
            bands=BANDS + ["SCL"],
            crs=CRS,
            resolution=RES,
            x=(bbox[0], bbox[2]),
            y=(bbox[1], bbox[3]),
            resampling={"*": "bilinear", "SCL": "nearest"},
        ).isel(time=0)
        valid = ~ds["SCL"].isin(INVALID_SCL)
        scenes.append(xr.Dataset({b: to_reflectance(ds[b], offset).where(valid) for b in BANDS}))
    stack = xr.concat(scenes, "time")
    out = stack.median("time")
    out["n_valid"] = stack["B03"].notnull().sum("time")
    gb = ds.odc.geobox
    out["inside"] = (("y", "x"), geometry_mask([region], gb.shape, gb.affine, invert=True))
    out.attrs["n_scenes"] = int((stack["B03"].where(out["inside"]).notnull().sum(("y", "x")) > 0).sum())
    out.attrs["valid_frac"] = float((out["n_valid"] > 0).where(out["inside"]).mean())
    return out
