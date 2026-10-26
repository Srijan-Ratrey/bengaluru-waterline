import numpy as np
import xarray as xr

from lakewatch.composite import to_reflectance
from lakewatch.indices import area_ha, mndwi, ndwi, threshold
from lakewatch.stac import parse_boa_offset


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
