import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import xarray as xr
from odc.geo.geobox import GeoBox
from odc.geo.xr import xr_coords

from lakewatch.composite import load, save, to_reflectance
from lakewatch.indices import area_ha, area_interval, edge_ha, measure, mndwi, ndwi, threshold
from lakewatch.labels import LAND, VEG, WATER, rasterize, split
from lakewatch.stac import parse_boa_offset
from lakewatch.trends import trends


def test_boa_offset_from_product_xml():
    new = (
        "<BOA_ADD_OFFSET band_id='0'>-1000</BOA_ADD_OFFSET><BOA_ADD_OFFSET band_id='1'>-1000</BOA_ADD_OFFSET>"
    )
    assert parse_boa_offset(new) == -1000
    assert parse_boa_offset("<BOA_QUANTIFICATION_VALUE>10000</BOA_QUANTIFICATION_VALUE>") == 0


def test_reflectance_applies_offset_and_nodata():
    dn = xr.DataArray(np.array([0, 1000, 3000]))
    np.testing.assert_allclose(to_reflectance(dn, -1000), [np.nan, 0.0, 0.2])
    np.testing.assert_allclose(to_reflectance(dn, 0), [np.nan, 0.1, 0.3])


def test_indices():
    c = {"B03": np.array([0.3, 0.1]), "B08": np.array([0.1, 0.3]), "B11": np.array([0.1, 0.3])}
    np.testing.assert_allclose(ndwi(c), [0.5, -0.5])
    np.testing.assert_allclose(mndwi(c), [0.5, -0.5])


def test_otsu_splits_water_from_land_and_area():
    idx = np.r_[np.full(50, 0.6), np.full(150, -0.4), np.nan]
    inside = np.ones(idx.shape, bool)
    t = threshold(idx, inside)
    assert -0.4 < t < 0.6
    assert area_ha(idx > t) == 0.5  # 50 pixels x 100 m^2
    assert threshold(idx, inside, "zero") == 0.0


def _toy_composite():
    """4x4 grid: left half water (green high, NIR/SWIR low), right half land."""
    gb = GeoBox.from_bbox((0, 0, 40, 40), "EPSG:32643", resolution=10)
    water = np.zeros((4, 4), bool)
    water[:, :2] = True
    band = lambda w, l: (("y", "x"), np.where(water, w, l).astype("float32"))
    c = xr.Dataset(
        {
            "B02": band(0.1, 0.1),
            "B03": band(0.3, 0.1),
            "B04": band(0.1, 0.05),
            "B08": band(0.05, 0.4),
            "B11": band(0.05, 0.3),
            "n_valid": band(3, 3),
        },
        coords=xr_coords(gb),
    )
    c["inside"] = (("y", "x"), np.ones((4, 4), bool))
    c["lake"] = (("y", "x"), water)
    c.attrs = {"n_scenes": 3, "valid_frac": 1.0}
    return c, np.where(water, 0.9, 0.1).astype("float32")


def test_measure_rows():
    c, dw = _toy_composite()
    rows = {r["method"]: r for r in measure(c, dw)}
    assert set(rows) == {"ndwi_otsu", "ndwi_zero", "mndwi_otsu", "mndwi_zero", "dw_0.3", "dw_0.5", "dw_0.7"}
    for r in rows.values():
        assert r["water_area_ha"] == 0.08  # 8 pixels
        assert r["iou_dw50"] == 1.0
    assert rows["dw_0.5"]["veg_frac"] == 0.0


def test_save_load_roundtrip(tmp_path):
    c, _ = _toy_composite()
    save(c, tmp_path / "c.tif")
    back = load(tmp_path / "c.tif")
    assert back.odc.geobox == c.odc.geobox
    assert back.attrs == c.attrs
    np.testing.assert_array_equal(back["lake"], c["lake"])
    np.testing.assert_allclose(back["B03"], c["B03"])


def test_rasterize_veg_clipped_to_lake_and_wins_over_water():
    c, _ = _toy_composite()  # lake polygon = left two columns
    polys = gpd.GeoDataFrame(
        {"class": ["water", "veg"]},
        geometry=[
            shapely.box(0, 0, 40, 20),
            shapely.box(0, 0, 40, 40),
        ],  # water: bottom half; veg: everything
        crs="EPSG:32643",
    )
    t = rasterize(polys, c)
    assert (t[:, :2] == VEG).all()  # veg inside the lake beats water
    assert (t[2:, 2:] == WATER).all() and (t[:2, 2:] == LAND).all()  # outside the lake veg is dropped


def test_area_interval():
    idx = np.array([[0.5, 0.1, -0.1, -0.5]] * 2)
    inside = np.ones(idx.shape, bool)
    assert edge_ha(idx > 0) == 2 * 10 * 5 / 10_000  # two vertical pixel edges along the shoreline
    area, lo, hi = area_interval(idx, inside, 0.0, 0.2)
    assert (area, lo, hi) == (0.04, 0.02 - 0.01, 0.06 + 0.01)


def test_split_is_disjoint_and_covers_all_lakes():
    rng = np.random.default_rng(1)
    lakes = pd.DataFrame(
        {
            "lake_id": [f"l{i}" for i in range(34)],
            "area_ha": rng.uniform(2, 300, 34),
            "veg_frac": rng.random(34),
        }
    )
    s = split(lakes)
    assert [len(s[k]) for k in ("test", "val", "train")] == [12, 8, 14]
    assert sorted(s["test"] + s["val"] + s["train"]) == sorted(lakes["lake_id"])


def test_trends_flag_only_clear_monotonic_change():
    years = np.arange(2018, 2026)
    a = pd.concat(
        [
            pd.DataFrame({"lake_id": "down", "year": years, "area": 20.0 - 2 * (years - 2018)}),
            pd.DataFrame({"lake_id": "flat", "year": years, "area": 5.0}),
            pd.DataFrame({"lake_id": "noisy", "year": years, "area": [3.0, 9, 1, 8, 2, 9, 1, 8]}),
        ]
    )
    t = trends(a, "area").set_index("lake_id")
    assert t.loc["down", "slope"] == -2 and t.loc["down", "verdict"] == "shrinking"
    assert t.loc["flat", "verdict"] == "no clear trend" and t.loc["noisy", "verdict"] == "no clear trend"
