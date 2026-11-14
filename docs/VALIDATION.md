# Validation

Everything below is measured against hand labels. The labels are the only ground truth in the project.

## Labels

- **What was labelled:** 20 lakes x 2 winters (2018, 2025), so 40 lake-years. The labels are 144 polygons: 67 water and 77 vegetation.
- **Imagery:** drawn in QGIS on the Sentinel-2 composites themselves, in true colour and SWIR false colour. No third-party basemaps were used (D6).
- **Annotator:** one person ("SR"). There is no second annotator, so the agreement ceiling is unknown.
- **Guide:** [LABELLING.md](LABELLING.md).
- **Classes:**
  - water anywhere in the lake region;
  - vegetation clipped to the lake polygon, winning over water where the two overlap;
  - everything else is land.

  The labels were rasterized with the pixel-centre rule.
- **Blindness:** while labelling, the annotator did not look at any model mask.

## Split and pre-registration

| date | step |
|---|---|
| 2026-10-26 | Split frozen in [configs/split.json](../configs/split.json): 12 test, 8 validation and 14 unlabelled lakes. Stratified by size and vegetation cover. Water-area criteria written into [configs/experiment.toml](../configs/experiment.toml). |
| 2026-10-30 to 2026-11-13 | Labelling, validation lakes first. |
| 2026-11-13 | Method, thresholds and interval width chosen on validation lakes only. 3-class IoU targets appended (validation result minus about 0.1). Then test scored **once**. |

The test lakes were never used for tuning. Nothing was changed after scoring test.

## Results

| | validation (16 lake-years) | **test (24)** | target | test result |
|---|---|---|---|---|
| Median \|relative area error\|, clean lakes | 0.13 | **0.24** | <= 0.10 | **miss** |
| Median \|relative area error\|, vegetated lakes | 0.30 | **0.25** | reported | |
| Interval coverage (nominal 0.90) | 0.88 | **0.83** | 0.80-1.00 | pass |
| Pooled IoU, water (lake polygon) | 0.73 | **0.78** | >= 0.65 | pass |
| Pooled IoU, vegetation | 0.70 | **0.74** | >= 0.60 | pass |
| Pooled IoU, land | 0.33 | **0.46** | reported | |
| 2018 -> 2025 change direction correct | 6/8 | **7/12** | reported | |

**Definitions:**
- **Relative area error** = (estimated − labelled) / labelled, for water over the lake region. Lake-years with 0 ha labelled are left out of the median.
- **Clean or vegetated:** a lake is *vegetated* if its median vegetation cover across 2018-2025 is above 0.6.
- **Coverage** is the share of lake-years whose labelled area falls inside `[area_lo, area_hi]`.

**Areas run low.** The median signed error on test is −16% for clean lakes and −25% for vegetated lakes.

### By size (test, lake-years)

| OSM lake size | n | median \|error\| | median signed error | coverage |
|---|---|---|---|---|
| 2-10 ha | 10 | 0.16 | −0.16 | 0.90 |
| 10-50 ha | 6 | 0.43 | −0.43 | 0.83 |
| 50+ ha | 8 | 0.24 | −0.16 | 0.75 |

The 10-50 ha bin is pulled down by Kogilu (see failures below). With 6-10 lake-years per bin, these medians are rough.

### Failures

A lake-year counts as a failure if |error| > 50%, or if 0 ha was labelled and more than 1 ha was estimated.

**Test: 3 of 24**

| lake-year | labelled | estimated | cause |
|---|---|---|---|
| Kogilu 2018 | 8.2 ha | 0.8 ha | Water with vegetation in it (NDVI about 0.37), which MNDWI reads as land. |
| Kogilu 2025 | 15.2 ha | 7.2 ha | Same as 2018. |
| Hosakere 2018 | 0.15 ha | 0.02 ha | A tiny area; in absolute terms the miss is negligible. |

**Validation: 4 of 16**

| lake-year | labelled | estimated | cause |
|---|---|---|---|
| Sarjapur Doddakere 2018 | 0 ha | 11.4 ha | Pixels labelled land or vegetation have MNDWI > 0 and NDVI about −0.2. Either wet dark ground or water the labels missed; unresolved. |
| Sarjapur Doddakere 2025 | 8.7 ha | 1.0 ha | Dark water missed. |
| Hommadevanahalli 2025 | 4.0 ha | 1.3 ha | Missed water has MNDWI about −0.2 and NDVI about 0.16: turbid or dark water. |
| Thiagalara Chowdenahalli 2018 | 1.3 ha | 0.5 ha | A small, patchy lake. |

### Worst clean-lake misses (test), behind the missed 10% target

| lake-year | labelled | estimated | cause |
|---|---|---|---|
| Bagaluru 2025 | 56.1 ha | 37.7 ha | Dark water. |
| Budigere 2018 | 33.2 ha | 22.9 ha | Dark water. |
| Chudahalli 2018 | 39.3 ha | 29.2 ha | Dark water. |

**Dark-water mechanism:** the missed pixels have low NIR (0.02-0.03, which is water), but their SWIR (about 0.05) is above their green (about 0.03), so MNDWI comes out negative. Dynamic World gives these pixels a water probability of 0.45-0.65. The bias was already visible on validation (median −13%). It was not corrected after test, because any fix needs new labelled lakes to validate it.

## Not validated

- Only 2018 and 2025 are labelled. The other 6 winters are unchecked, which matters most for trends.
- The 14 train lakes have no labels.
- There is no second annotator, so there is no label-agreement ceiling.
- Trend verdicts can't be checked directly. The only check is the 2018 -> 2025 direction, which was right for 7 of 12 test lakes.

## Reproduce

```sh
uv run lakewatch evaluate val    # writes the threshold grid too
uv run lakewatch evaluate test   # refuses to run unless the 3-class targets are in configs/experiment.toml
```

This needs the composites (`lakewatch measure`) and `data/labels/labels.gpkg`, which is committed.
