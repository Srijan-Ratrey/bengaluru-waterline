"""Cloud-masked, offset-corrected seasonal median composite around one lake."""

from concurrent.futures import ThreadPoolExecutor

import odc.stac
import rasterio
import xarray as xr
from odc.geo.geobox import GeoBox
from odc.geo.xr import xr_coords
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
    """Median reflectance per band over valid observations, plus per-pixel `n_valid` and masks:
    `inside` (lake buffered by `buffer_m`, the measurement region) and `lake` (the polygon itself)."""
    region = geom_utm.buffer(buffer_m)
    bbox = region.bounds

    def read_scene(item_offset):
        item, offset = item_offset
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
        return xr.Dataset({b: to_reflectance(ds[b], offset).where(valid) for b in BANDS})

    with ThreadPoolExecutor(16) as ex:
        stack = xr.concat(list(ex.map(read_scene, zip(items, offsets))), "time")
    out = stack.median("time")
    out["n_valid"] = stack["B03"].notnull().sum("time")
    gb = out.odc.geobox
    for name, geom in [("inside", region), ("lake", geom_utm)]:
        out[name] = (("y", "x"), geometry_mask([geom], gb.shape, gb.affine, invert=True))
    out.attrs["n_scenes"] = int((stack["B03"].where(out["inside"]).notnull().sum(("y", "x")) > 0).sum())
    out.attrs["valid_frac"] = float((out["n_valid"] > 0).where(out["inside"]).mean())
    return out


def save(ds: xr.Dataset, path) -> None:
    """All variables as float32 bands (named by description) in one GeoTIFF; attrs as tags."""
    gb = ds.odc.geobox
    names = list(ds.data_vars)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=gb.shape.y,
        width=gb.shape.x,
        count=len(names),
        dtype="float32",
        crs=gb.crs.to_wkt(),
        transform=gb.affine,
        compress="deflate",
    ) as dst:
        for i, n in enumerate(names, 1):
            dst.write(ds[n].values.astype("float32"), i)
            dst.set_band_description(i, n)
        dst.update_tags(**ds.attrs)


def load(path) -> xr.Dataset:
    with rasterio.open(path) as src:
        gb = GeoBox(src.shape, src.transform, src.crs)
        ds = xr.Dataset(
            {n: (("y", "x"), a) for n, a in zip(src.descriptions, src.read())}, coords=xr_coords(gb)
        )
        tags = src.tags()
    for m in ("inside", "lake"):
        ds[m] = ds[m] > 0
    ds.attrs = {"n_scenes": int(tags["n_scenes"]), "valid_frac": float(tags["valid_frac"])}
    return ds
