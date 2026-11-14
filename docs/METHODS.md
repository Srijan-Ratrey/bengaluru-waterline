# Methods

How Bengaluru Waterline turns Sentinel-2 scenes into per-lake water, vegetation and land areas, intervals and trends. Every step below is one CLI command (see the README quickstart). Settings live in [configs/experiment.toml](../configs/experiment.toml).

## 1. Lakes (`waterline lakes`)

- **Candidates:** named OpenStreetMap water polygons of at least 2 ha inside the Bengaluru AOI ([configs/aoi.geojson](../configs/aoi.geojson)). There are 222 of them.
- **Selection:** 12 lakes per size bin (2-10, 10-50, 50+ ha), seed 0, giving 36 lakes.
- **Manual review** dropped two of them, leaving **34 lakes** (D2):
  - Vrishabhavati, because it is a river corridor rather than a lake;
  - Nagarbhavi Thorai, because it has no water in any year.
- **Added on request (2026-11-14):** 10 well-known lakes the draw missed, from the same OSM candidates (`waterline add-lakes`), tagged `sample=added`. They are measured and trended like the others, but are not part of the random sample and have no labels.
- **Pinning:** boundaries are committed in [configs/lakes.geojson](../configs/lakes.geojson) and used unchanged.

Each lake is measured over two masks:

| mask | extent | used for |
|---|---|---|
| `lake` | the OSM polygon | vegetation and land areas |
| `inside` | the polygon buffered by 150 m (the "lake region") | water area |

Water is counted out to the buffer because OSM outlines often sit inside the real shoreline.

## 2. Scenes and composites (`waterline lock`, `waterline measure`)

- **Source:** Sentinel-2 L2A from Microsoft Planetary Computer.
- **Window:** winter (1 Jan - 28 Feb), every year 2018-2025 (D3). Winter has 7-11 clear days a year. 2017 has only 2-4 and was dropped, and the post-monsoon window has 2-4 a year.
- **Pinning:** every scene ID is pinned in `data/scenes.lock.json`, with scene cloud cover below 50%.
- **Radiometry:** reflectance = (DN + offset) / 10000. The offset (0 or -1000) is read per scene from `BOA_ADD_OFFSET` in the product XML. It is not in the STAC metadata. DN 0 is treated as no data.
- **Cloud mask:** pixels are dropped when the Scene Classification Layer (SCL) class is 0, 1, 3, 8, 9 or 10. These are no data, saturated, cloud shadow, medium and high cloud, and cirrus.
  - Class 2 (dark area) is kept, because dark water falls into it.
- **Composite:** the per-pixel median of valid observations, for bands B02, B03, B04, B08 and B11.
  - Grid: 10 m, UTM 43N (EPSG:32643). B11 (20 m) is resampled bilinearly; SCL is resampled nearest-neighbour.
  - Each composite is cached as a GeoTIFF in `data/composites/`.
- **Quality gates (D7):** spec defaults are `valid_frac` >= 0.8 and `n_scenes` >= 3. Every lake-year passes: `valid_frac` is at least 0.988 and `n_scenes` is 7-27. No lake-year was dropped.

## 3. Classification (frozen method)

Per pixel, with MNDWI = (B03 - B11) / (B03 + B11) and NDVI = (B08 - B04) / (B08 + B04):

| class | rule | where |
|---|---|---|
| water | MNDWI > 0 | lake region |
| vegetation | not water and NDVI > 0.5 | lake polygon |
| land | everything else | lake polygon |

**How the method was chosen:**
- The candidates were the method (MNDWI, NDWI or Dynamic World probability), the water threshold and the NDVI threshold.
- They were scored against hand labels on the 8 validation lakes only. The full grid is in `data/eval_val_grid.parquet`.
- **MNDWI > 0** was the pre-registered default, and it also had the lowest validation area error: median |error| 0.14, against 0.22 for Dynamic World >= 0.5.
- **NDVI 0.5** gave the best 3-class validation IoU: 0.59, against 0.51 at 0.3.

**Rejected alternatives:**
- **Otsu thresholds:** median IoU against Dynamic World was 0.30 for MNDWI+Otsu and 0.12 for NDWI+Otsu, against 0.46 for MNDWI > 0. Otsu also breaks on single-class histograms. For example, Bellandur 2021 is about 86% vegetation, and MNDWI+Otsu reports 86 ha of water there where Dynamic World reports 0.6 ha.
- **Dynamic World** (Google/WRI, through Earth Engine) is kept as an independent cross-check and is not used in the reported areas.

**Vegetation (D13):** vegetation is reported as its own class rather than as water or land. Many lakes here are mostly covered by floating weeds, and an open-water-only number would read those lakes as nearly empty.

## 4. Area interval

Each water area comes with an interval `[area_lo, area_hi]`:

```
area_lo = max(0, area(MNDWI > +0.2) - E)
area_hi =        area(MNDWI > -0.2) + E
E       = (number of water/non-water pixel edges in the MNDWI > 0 map) x 10 m x 5 m
```

- **Threshold term (±0.2):** the threshold sensitivity from spec §7.2.
- **Edge term E:** half a pixel along the shoreline, from spec §7.1.
- **Cloud and sampling (§7.3):** every lake-year has `valid_frac` >= 0.988, so this adds nothing.
- **Calibration:** ±0.2 was the smallest margin that gave about 90% coverage of the hand-labelled area on validation (0.88). On test, the interval covered the labelled area in 83% of lake-years.

The interval is an empirical, calibrated range, not a derived confidence interval.

## 5. Trends (`waterline trends`)

For each lake, over the 8 winter values (2018-2025) of water area and of vegetation area:

- **Slope:** the Theil-Sen slope in ha/yr, with scipy's rank-based 90% CI. A bootstrap wasn't used because 8 points are too few to resample.
- **Mann-Kendall p:** Kendall's tau of area against year.
- **Correction:** Benjamini-Hochberg q across all 44 lakes.
- **Verdict:**
  - *shrinking* or *growing* when q < 0.1, with the slope's sign giving the direction;
  - *no clear trend* otherwise.

The per-year intervals are not propagated into the slope CI.

## 6. Outputs

| file | content |
|---|---|
| `data/observations.parquet` | every method x lake-year, from the exploration phase |
| `data/areas.parquet` | per lake-year: `area`, `area_lo`, `area_hi` (water, lake region) and `water_ha`, `veg_ha`, `land_ha` (lake polygon) |
| `data/trends.parquet` | per lake: slope, CI, p, q and verdict, for water and for vegetation |
| `data/eval_{val,test}.parquet` | per labelled lake-year: estimated area and interval against the labelled area, and per-class counts |
| `site/` | the static demo, from `waterline site` |
