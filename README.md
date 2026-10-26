# LakeWatch

Satellite lake-extent tracker for Bengaluru. Measures per-lake yearly water area from Sentinel-2, with uncertainty and held-out-lake validation.

Full spec: [lakewatch-tech-spec.md](lakewatch-tech-spec.md)

## Quickstart

```sh
uv sync
uv run lakewatch lakes                                   # OSM -> configs/lakes.geojson (committed, pinned)
uv run lakewatch lock                                    # -> data/scenes.lock.json + clear-day counts
export EE_PROJECT=<your-earth-engine-project>          # free non-commercial project; `uv run earthengine authenticate` once
uv run lakewatch measure                                 # all lakes x years -> data/observations.parquet
uv run lakewatch sheet                                   # per-lake PNG: years x (RGB, MNDWI, DW) -> data/sheets/
uv run lakewatch label-prep                              # frozen split + QGIS inputs; see docs/LABELLING.md
uv run pytest
```

`measure` caches one GeoTIFF per lake-year in `data/composites/` (bands B02-B11 median reflectance, `n_valid`, `inside`/`lake` masks, `dw_water`); open them in QGIS for hand labelling.

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
| D2 | OSM + manual review. Dropped `w1054822214` Vrishabhavati (river corridor) and `w1054822222` Nagarbhavi Thorai (no water any year) -> 34 lakes |
| D3 | 2018 to 2025, winter (Jan-Feb) window only. 2017 dropped (2-4 clear days); post-monsoon dropped (2-4/yr) |
| D13 | 3-class breakdown per lake-year: open water / vegetated surface / bare-or-built inside the boundary |
| D4 | Indices + U-Net (U-Net built regardless of index results) |
| D9 | Planetary Computer for Sentinel-2 (Dynamic World still via Earth Engine) |
| D10 | CLI + library |
| D12 | Licence: undecided, repo private until settled |
| D15 | Name: LakeWatch. Note: `0x101/lakewatch` and `Clnay5/lakewatch` are similar Sentinel-2 lake projects; review them before any novelty claim |
| D16 | Sentinel-2 only for v1 |

| D5/D6 | Hand labels: 20 lakes (8 val + 12 test) x 2018, 2025, drawn on the Sentinel-2 composites ([guide](docs/LABELLING.md)). Train lakes use weak labels |

Split frozen in [configs/split.json](configs/split.json), criteria in [configs/experiment.toml](configs/experiment.toml). Still on spec defaults until their gates: D7, D8, D11, D14.
- **Full run (36 lakes x 2018-2025):** 21 of 36 lakes have >60% vegetation cover inside the polygon in a typical year; open-water-only methods report them as near-empty. Median IoU vs Dynamic World p>=0.5: MNDWI>0 0.46, MNDWI+Otsu 0.30, NDWI+Otsu 0.12, so Otsu is dropped as default. This drove D13.
