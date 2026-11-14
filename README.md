# LakeWatch

Satellite lake-extent tracker for Bengaluru. Measures per-lake yearly water area from Sentinel-2, with uncertainty and held-out-lake validation.

Docs: [METHODS](docs/METHODS.md) · [VALIDATION](docs/VALIDATION.md) · [LIMITATIONS](docs/LIMITATIONS.md) · [labelling guide](docs/LABELLING.md) · [full spec](lakewatch-tech-spec.md)

## Quickstart

```sh
uv sync
uv run lakewatch lakes                                   # OSM -> configs/lakes.geojson (committed, pinned)
uv run lakewatch lock                                    # -> data/scenes.lock.json + clear-day counts
export EE_PROJECT=<your-earth-engine-project>          # free non-commercial project; `uv run earthengine authenticate` once
uv run lakewatch measure                                 # all lakes x years -> data/observations.parquet
uv run lakewatch sheet                                   # per-lake PNG: years x (RGB, MNDWI, DW) -> data/sheets/
uv run lakewatch label-prep                              # frozen split + QGIS inputs; see docs/LABELLING.md
uv run lakewatch evaluate val                            # tune on val lakes; `evaluate test` once settings are frozen
uv run lakewatch trends                                  # per-lake areas + trends at the frozen method
uv run lakewatch site                                    # demo data -> site/
uv run python -m http.server -d site                     # then open http://localhost:8000 (not the file directly: OSM blocks file:// map tiles)
uv run pytest
```

`measure` caches one GeoTIFF per lake-year in `data/composites/` (bands B02-B11 median reflectance, `n_valid`, `inside`/`lake` masks, `dw_water`); open them in QGIS for hand labelling.

## Validation against hand labels (2026-11-13)

40 hand-labelled lake-years (20 lakes x 2018, 2025; one annotator). Settings were chosen on the 8 val lakes and frozen in [configs/experiment.toml](configs/experiment.toml) before the 12 test lakes were scored, once. Method: water = MNDWI > 0, veg = NDVI > 0.5 inside the lake, everything else land.

| | val (16) | **test (24)** | frozen target | test |
|---|---|---|---|---|
| Median relative area error, clean lakes | 0.13 | **0.24** | <= 0.10 | **fail** |
| Median relative area error, vegetated lakes | 0.30 | **0.25** | reported | |
| Interval coverage (nominal 0.90) | 0.88 | **0.83** | 0.80-1.00 | pass |
| Pooled IoU, water | 0.73 | **0.78** | >= 0.65 | pass |
| Pooled IoU, veg | 0.70 | **0.74** | >= 0.60 | pass |
| Pooled IoU, land | 0.33 | **0.46** | reported | |
| 2018 -> 2025 change direction correct | 6/8 | **7/12** | reported | |

- **MNDWI undercounts dark water.** On the worst test lake-years (Bagaluru 2025: 37.7 vs 56.1 ha; Chudahalli 2018; Budigere 2018), the missed water pixels have low NIR (0.02-0.03, i.e. water) but SWIR (~0.05) above green (~0.03), so MNDWI goes negative. Dynamic World gives them p 0.45-0.65. Val already showed the same bias (median -13% at MNDWI > 0). Not fixed post hoc: any fix has to be re-validated on new labelled lakes.
- **Kogilu 2018** (8.2 ha labelled, 0.8 ha by MNDWI): missed pixels have NDVI 0.37, i.e. vegetation-tinged water.
- **Dynamic World** is the best single method on large clean lakes (Madiwala IoU 0.92-0.94) but misses most of weed-margined Hosakote 2018 (21 vs 207 ha).
- **Limits:** one annotator (no agreement ceiling yet), 3 clean val lakes, small lakes dominate the interval width.

## Trends 2018-2025 (2026-11-13; 10 lakes added 2026-11-14)

`uv run lakewatch trends` -> `data/areas.parquet` (per lake-year: water area with `area_lo`/`area_hi`, and water/veg/land ha inside the lake) and `data/trends.parquet`. Per lake: Theil-Sen slope with scipy's rank-based 90% CI (used instead of a bootstrap: 8 points is too few to resample), Mann-Kendall p (Kendall tau vs year), Benjamini-Hochberg q across all 44 lakes, verdict at q < 0.1.

- **Open water:** 2 lakes shrinking (Gattahalli -1.5 ha/yr, Hommadevanahalli -0.3 ha/yr), 1 growing (Horamavu Agara +1.8 ha/yr), **31 no clear trend**.
- **Vegetation inside the lake:** 1 growing (Gattahalli), 33 no clear trend.
- **10 lakes added on request** (2026-11-14, `lakewatch add-lakes`): Agara, Hebbal, Jakkur, Rachenahalli, Kaikondrahalli, Sankey Tank, Lalbagh Tank, Puttenahalli (Yelahanka), Yellamallappa Chetty and Muthanalluru. They are well-known lakes the random draw missed, tagged `sample=added` in [configs/lakes.geojson](configs/lakes.geojson), measured only and never labelled.
  - All 10 come out as no clear trend for both water and vegetation. The nearest to a verdict is Muthanalluru, at 65 -> 13 ha and -6.5 ha/yr (90% CI -11.3 to -1.2), but q = 0.17.
  - Adding them didn't change any verdict among the 34. The counts above are for the random 34; statements about Bengaluru lakes in general should use only those.
- **Why so few:** 8 winters is low power, and year-to-year swings are large (Hosakote: 180, 24, 25, 22, 233, 257, 235, 22 ha). "No clear trend" means the data can't tell, not that a lake is stable.
- Caveats: areas carry the test-set undercount of dark water (above); per-year intervals are not propagated into the slope CI; extent only, no causes.

## Demo site (2026-11-14)

`site/index.html` is a static page (serve the folder with any static server; opened as a file, OSM refuses the map tiles); `lakewatch site` writes its data (`site/data.js`, `site/img/`, 2.6 MB, gitignored until D12 is settled). It shows:

- a dark map with year buttons and a play button, overlaying each lake's Sentinel-2 true-colour composite (clipped to the lake region) and the frozen water/veg map;
- a searchable, sortable lake list with sparklines, and filter tiles by trend verdict;
- lake outlines coloured by trend verdict;
- per lake, an area chart with the interval band, the vegetation series and the hand-labelled areas;
- a "lakes to read with care" panel listing vegetated lakes (median veg cover > 0.6) and lakes with wide intervals (median interval wider than the area);
- the test-set misses stated up front.

`#<lake_id>` in the URL opens a lake directly. Not yet hosted: GitHub Pages on a private repo needs a paid plan, and publishing waits on D12.

## Findings so far (verified 2026-10-26)

- **Reflectance offset** is not in Planetary Computer's STAC `raster:bands`; it is only in each item's `product-metadata` XML (`BOA_ADD_OFFSET`). The lock has 257 items with offset 0 and 271 with -1000, so it is read per item and stored in the lock.
- **SCL** asset is `SCL` (20 m). Class codes are not in the metadata; ESA's standard codes are used.
- **Clear days** (tile cloud < 20%) per candidate window, 2017-2025: winter (Jan-Feb) 7-11/yr, pre-monsoon (Mar-mid May) 8-14/yr, post-monsoon (mid Oct-Dec) 2-4/yr. 2017 has only 2-4 in every window.
- **Bellandur (r19751547):** MNDWI and Dynamic World (p >= 0.5) agree at IoU 0.72-0.94 in normal years. 2020-2022 show ~86% vegetation cover inside the polygon and near-zero open water; there MNDWI+Otsu breaks (86 ha vs DW 0.6 ha in 2021) because the histogram is single-class. NDWI+Otsu is unreliable throughout.
- **Lakes:** 222 named OSM candidates of at least 2 ha; 36 picked, 12 per size bin (2-10, 10-50, 50+ ha).

## Decisions (as of 2026-10-26)

| ID | Decision |
|---|---|
| D1 | 25–40 lakes, mixed size and condition, minimum ~2 ha |
| D2 | OSM + manual review. Dropped `w1054822214` Vrishabhavati (river corridor) and `w1054822222` Nagarbhavi Thorai (no water any year) -> 34 lakes (random sample); +10 well-known lakes added on request 2026-11-14, tagged `sample=added` |
| D3 | 2018 to 2025, winter (Jan-Feb) window only. 2017 dropped (2-4 clear days); post-monsoon dropped (2-4/yr) |
| D13 | 3-class breakdown per lake-year: open water / vegetated surface / bare-or-built inside the boundary |
| D4 | Indices + U-Net (U-Net built regardless of index results) |
| D9 | Planetary Computer for Sentinel-2 (Dynamic World still via Earth Engine) |
| D10 | CLI + library |
| D12 | Licence: MIT for code; CC BY 4.0 for derived data and hand labels; lake outlines stay ODbL (see Licence) |
| D15 | Name: LakeWatch. Checked 2026-11-14: `0x101/lakewatch` (city lake water + algae kit) and `Clnay5/lakewatch` (Sentinel-2 water change, MIT) are similar and same-named. No "first" claims; what sets this one apart is the held-out hand-labelled validation, calibrated intervals and the water/veg/land split |
| D16 | Sentinel-2 only for v1 |

| D5/D6 | Hand labels: 20 lakes (8 val + 12 test) x 2018, 2025, drawn on the Sentinel-2 composites ([guide](docs/LABELLING.md)). Train lakes use weak labels |

Split frozen in [configs/split.json](configs/split.json), criteria in [configs/experiment.toml](configs/experiment.toml). Still on spec defaults until their gates: D7, D8, D11, D14.
- **Full run (36 lakes x 2018-2025):** 21 of 36 lakes have >60% vegetation cover inside the polygon in a typical year; open-water-only methods report them as near-empty. Median IoU vs Dynamic World p>=0.5: MNDWI>0 0.46, MNDWI+Otsu 0.30, NDWI+Otsu 0.12, so Otsu is dropped as default. This drove D13.

## Licence

- **Code:** MIT ([LICENSE](LICENSE)).
- **Derived data and hand labels:** CC BY 4.0. This covers the areas, trends, `data/labels/labels.gpkg` and the site's images and data.
- **Lake outlines:** [configs/lakes.geojson](configs/lakes.geojson) and the outlines in `site/data.js` come from OpenStreetMap. They stay under the [ODbL](https://opendatacommons.org/licenses/odbl/) with attribution "© OpenStreetMap contributors".
- **Imagery:** contains modified Copernicus Sentinel data 2018-2025, accessed through Microsoft Planetary Computer.
- **Dynamic World:** © Google / World Resources Institute, CC BY 4.0. Used only as a cross-check, so it is not in any published output.
