# Labelling guide

You label **20 lakes x 2 years (2018, 2025) = 40 lake-years**. These labels are the only ground truth in the project: every accuracy number comes from them. Expect 5-15 minutes per lake-year.

## Setup (once)

```sh
uv run lakewatch label-prep   # already run; regenerates data/labelling/ if needed
```

In QGIS, add:
- `data/labels/labels.gpkg` -> layer `labels` (you draw here; this file is committed)
- `data/labelling/lakes.gpkg` -> layers `lakes` (OSM boundary) and `lake_regions` (boundary + 150 m)
- for the lake-year you are on: `data/labelling/<lake_id>_<year>_rgb.tif` and `..._swir.tif`

Optional time-saver: in `labels` Layer Properties -> Attributes Form, set default values for `annotator` (your name), and for `lake_id` and `year` while you work on one lake.

## What to draw

Draw polygons in `labels` with `class` set to one of:

| class | what | where |
|---|---|---|
| `water` | open water surface you can see | anywhere inside `lake_regions` |
| `veg` | any vegetation surface: floating weeds, reeds, grass, trees, islands | inside or touching `lakes` (the boundary); it gets clipped to the boundary |

Leave everything else undrawn; it counts as **land** (bare soil, construction, roads, buildings).

**Overlaps are fine: where `veg` and `water` overlap, `veg` wins.** So trace the water's outer edge in one polygon and draw islands and weed patches on top, without cutting holes.

**Reading the images:**
- `swir` (SWIR-NIR-Red): water is black or very dark blue; vegetation is bright green; bare and built land is pink, purple or brown. Use it first.
- `rgb` (true colour): use it to check. Weed-covered water is dark, uniform green; a grassy dry bed is lighter and patchier, often with tracks.

## Rules

1. **Stay blind.** Do not open `data/composites/`, `data/sheets/` or any model mask while labelling. Looking at them biases the labels toward the methods being tested.
2. **Use only these Sentinel-2 images.** No Google or Bing basemaps: they come from a different date, and their terms may not allow labelling.
3. **Edges:** put the line through the middle of mixed edge pixels. Pixels are 10 m; do not trace finer than that.
4. **Unsure areas:** if a patch might be weed-covered water or a wet meadow, label it `veg`. Note anything doubtful in the commit message.
5. **Order:** do the **val** lakes first (they get used for tuning), then **test**.
6. **Second annotator (optional, valuable):** if someone else can label 5 of these lakes independently, with their own `annotator` name, that gives the agreement ceiling (spec 9.1).

## Lakes


**val**

| lake_id | name | OSM area (ha) |
|---|---|---|
| `w41667728` | Hosakote lake | 307.3 |
| `r2310417` | Madiwala Lake | 82.8 |
| `w1186908539` | Sarjapur Doddakere Lake | 78.5 |
| `r20742762` | Doddanekundi Lake | 36.7 |
| `w45921399` | Narasappanahalli Lake | 17.4 |
| `r17390866` | Horamavu Agara Lake | 14.4 |
| `w1092941882` | Thiagalara Chowdenahalli Lake | 8.8 |
| `w1178402477` | Hommadevanahalli Lake | 4.6 |

**test**

| lake_id | name | OSM area (ha) |
|---|---|---|
| `r19751547` | Bellandur Lake | 315.4 |
| `w1092686472` | Budigere Lake | 144.2 |
| `w43102038` | Bagaluru Kere | 52.9 |
| `w118906503` | Chudahalli Lake | 50.7 |
| `w125758396` | Gattahalli Lake | 25.6 |
| `w41667656` | Kogilu Lake | 24.1 |
| `w45741726` | Hosakere | 11.9 |
| `w904374443` | Palanahalli Lake | 7.3 |
| `w44546800` | Kowdenahalli Lake | 5.8 |
| `w560721005` | Komapana Agrahara Lake | 5.3 |
| `r18077306` | Munekolala Lake | 4.4 |
| `w28126428` | Byrasandra Lake | 2.6 |
