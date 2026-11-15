# Decisions and early findings

The project log: what was decided and when, and what the first runs found. IDs (D1, D2, ...) refer to the open decisions in the original [spec](SPEC.md).

## Decisions (as of 2026-11-15)

| ID | Decision |
|---|---|
| D1 | 25-40 lakes, mixed size and condition, minimum ~2 ha |
| D2 | OSM + manual review. Dropped `w1054822214` Vrishabhavati (river corridor) and `w1054822222` Nagarbhavi Thorai (no water any year) -> 34 lakes (random sample); +10 well-known lakes added on request 2026-11-14, tagged `sample=added` |
| D3 | 2018 to 2025, winter (Jan-Feb) for maps and validation; pre-monsoon (Mar-mid May) added 2026-11-14 for trends only. 2017 dropped (2-4 clear days); post-monsoon dropped (2-4/yr) |
| D4 | Indices + U-Net (U-Net built regardless of index results; not built yet) |
| D5/D6 | Hand labels: 20 lakes (8 val + 12 test) x 2018, 2025, drawn on the Sentinel-2 composites ([guide](LABELLING.md)). Train lakes use weak labels |
| D9 | Planetary Computer for Sentinel-2 (Dynamic World, an optional cross-check, via Earth Engine) |
| D10 | CLI + library |
| D12 | Licence: MIT for code; CC BY 4.0 for derived data and hand labels; lake outlines stay ODbL (see the README's Licence section) |
| D13 | 3-class breakdown per lake-year: open water / vegetated surface / bare-or-built inside the boundary |
| D15 | Name: **Bengaluru Waterline** (2026-11-14; was LakeWatch, too close to Namma Lakes' "Bangalore Lake Watch" and two same-named repos). No "first" claims; what sets it apart is the held-out hand-labelled validation, calibrated intervals, tested trends and the water/veg/land split |
| D16 | Sentinel-2 only for v1 |

Split frozen in [configs/split.json](../configs/split.json), criteria in [configs/experiment.toml](../configs/experiment.toml). Still on spec defaults until their gates: D7, D8, D11, D14.

## Early findings (2026-10-26)

- **Reflectance offset** is not in Planetary Computer's STAC `raster:bands`; it is only in each item's `product-metadata` XML (`BOA_ADD_OFFSET`). The lock at the time had 257 items with offset 0 and 271 with -1000, so it is read per item and stored in the lock.
- **SCL** asset is `SCL` (20 m). Class codes are not in the metadata; ESA's standard codes are used.
- **Clear days** (tile cloud < 20%) per candidate window, 2017-2025: winter (Jan-Feb) 7-11/yr, pre-monsoon (Mar-mid May) 8-14/yr, post-monsoon (mid Oct-Dec) 2-4/yr. 2017 has only 2-4 in every window.
- **Lakes:** 222 named OSM candidates of at least 2 ha; 36 picked, 12 per size bin (2-10, 10-50, 50+ ha).
- **Bellandur (r19751547):** MNDWI and Dynamic World (p >= 0.5) agree at IoU 0.72-0.94 in normal years. 2020-2022 show ~86% vegetation cover inside the polygon and near-zero open water; there MNDWI+Otsu breaks (86 ha vs DW 0.6 ha in 2021) because the histogram is single-class. NDWI+Otsu is unreliable throughout.
- **Full run (36 lakes x 2018-2025):** 21 of 36 lakes have >60% vegetation cover inside the polygon in a typical year; open-water-only methods report them as near-empty. Median IoU vs Dynamic World p >= 0.5: MNDWI > 0 0.46, MNDWI+Otsu 0.30, NDWI+Otsu 0.12, so Otsu was dropped as the default. This drove D13.
