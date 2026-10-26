# LakeWatch BLR: Satellite Lake-Extent Tracker for Bengaluru

Working name only. A name collision has not been checked (see D15).

**One-line pitch:** measure how the water area of Bengaluru's lakes has changed over about ten years, using free Sentinel-2 satellite imagery. Every number comes with an uncertainty, a validation score, and a reproducible pipeline. Results are shown on an interactive map.

**Audience test:** "How much has each lake shrunk since 2017, and how sure are we?" Any engineer or non-engineer can follow that.

---

## 0. How to use this document

- Decisions are marked **[D#]**. Each has options, a recommended default, and a **gate** (the point in the plan by which it must be settled).
- If you do not answer a decision, the default applies. Defaults are chosen to keep the project finishable in about 4 weeks.
- Section 12 lists every decision in one table. Section 13 lists what was verified and what was not.

---

## 1. Why this project (resume fit)

| Signal | How this project shows it |
|---|---|
| New ML area | Computer vision on remote-sensing data, which is absent from the current resume |
| Evaluation rigor | Baselines, held-out lakes, uncertainty intervals, and success thresholds fixed before running experiments |
| Engineering | A CLI and library, pinned inputs, tests, CI, and a static web demo |
| Honesty about limits | A published "where it fails" section: algae-covered lakes, small lakes, clouds |
| Local relevance | Real lakes in a real city, which makes the project memorable |

**Positioning:** do not claim "novel water detection." Water indices and segmentation of water bodies are well established. The contribution is a **reproducible, validated, per-lake change tracker** with explicit uncertainty and documented failure modes.

---

## 2. Scope

### In scope (v1)
- A fixed set of Bengaluru lakes (see D1).
- Same-season annual composites from Sentinel-2 L2A (see D3).
- Three methods, compared against each other:
  1. Water-index threshold (NDWI / MNDWI, with Otsu or fixed thresholds).
  2. Cross-check against an independent product (Dynamic World water probability).
  3. A small U-Net segmenter, built only if needed (see D4).
- Per-lake yearly water area with an uncertainty range.
- Trend estimate per lake with a confidence interval.
- Validation against hand-labelled lakes, split **by lake**.
- A static interactive map with a time slider and per-lake charts.

### Out of scope (v1)
- Water quality, pollution, or algae-bloom measurement.
- Predicting future shrinkage.
- Sub-10 m resolution or commercial imagery.
- Real-time or automated alerting.
- Whole-district or whole-state coverage.

---

## 3. Prior art and positioning

Only sources opened or returned in this research are listed. Their quality and completeness were not audited.

- [ArcGIS sample: measure shrinking lakes using deep learning](https://developers.arcgis.com/python/latest/samples/measure-shrinking-lakes-using-deep-learning/): a tutorial-style workflow.
- [Deep learning framework for lake surface closed-curve prediction](https://yorkspace.library.yorku.ca/items/8e87abc9-de96-493c-ada0-6df9df8373b4): an academic approach.
- **Dynamic World** (Google/WRI): global near-real-time land cover with a per-pixel water probability. Used here as an independent cross-check and as a source of weak labels, not as the product being built.
- No polished open-source Bengaluru-specific lake tracker was found in one search. **This is not proof that none exists.** Repeat the search before publishing (see Section 13).

**Differentiation to aim for:** pinned and reproducible inputs, held-out-lake validation, per-lake uncertainty, honest failure analysis, and a usable demo.

---

## 4. Data sources

### 4.1 Imagery: Sentinel-2 L2A
- **Access (recommended):** Microsoft Planetary Computer STAC API.
  - Catalog URL: `https://planetarycomputer.microsoft.com/api/stac/v1`
  - Collection ID: `sentinel-2-l2a`
  - Open with `pystac-client` and `planetary_computer.sign_inplace`. An API key is optional and gives more permissive access (per the official example notebook).
  - Cloud filter example: `query={"eo:cloud_cover": {"lt": 10}}`.
  - Data is stored as cloud-optimized GeoTIFF, which supports windowed reads, so you only read the pixels you need.
- **Alternatives:** Copernicus Data Space, AWS open data, Google Earth Engine (see D9).
- **Resolution:** bands used for water are 10 m (Green B3, NIR B8) and 20 m (SWIR B11, B12; resample to 10 m).
- **Revisit:** about 5 days per the Planetary Computer page. Early years may have fewer scenes (verify, see Section 13).

### 4.2 Reference and cross-check products
- **Dynamic World V1:** 10 m, available from 2015-06-27 to present, `water` band is the probability that a pixel is fully water covered, licence CC-BY 4.0 with required attribution. It is derived from single images with cloud cover of 35% or less. The documentation recommends thresholding top-1 probability to keep confident pixels. Accessed via Earth Engine.
- **S1S2-Water v1.0.1:** 65 Sentinel-1/Sentinel-2 image triplets with quality-checked binary water masks. About 170 GB. Licence: see its [Zenodo record](https://zenodo.org/records/11278238) (not confirmed here). Optional, for pre-training or sanity checks only.

### 4.3 Lake boundaries (needs a decision, see D2)
- [Inventory of Lakes, Bengaluru Metropolitan Area](https://data.opencity.in/dataset/inventory-of-lakes-bengaluru-metropolitan-area): a 2018 EMPRI report for the Karnataka Lake Conservation and Development Authority, published as **5 PDF volumes** with no shapefile or GeoJSON listed. Licence shown: public domain. Useful for lake names and reference, not for geometry.
- [Bengaluru Lake Assets Survey 2023](https://data.opencity.in/dataset/bengaluru-lake-assets-survey-data): **CSV**, licence **CC BY-NC 2.0** (non-commercial). Whether it contains geometry is not stated. Do not redistribute it inside a project with a more open licence without checking.
- **Likely route:** build the boundary set from OpenStreetMap water polygons plus manual fixes. OpenStreetMap completeness for these lakes is **unverified**.

---

## 5. System design

```
lakes.gpkg (boundaries)           AOI geojson
        │                              │
        ▼                              ▼
  STAC search ──► scene list ──► scenes.lock.json (pinned item IDs)
                                       │
                                       ▼
                     windowed read + cloud/shadow mask
                                       │
                                       ▼
                  seasonal composite per year (median of valid pixels)
                                       │
          ┌────────────────────────────┼─────────────────────────────┐
          ▼                            ▼                             ▼
  index + threshold            Dynamic World probs              U-Net (optional)
          └────────────────────────────┼─────────────────────────────┘
                                       ▼
                          water mask per lake-year
                                       ▼
          area + uncertainty + valid-pixel fraction + flags
                                       ▼
                    observations.parquet ──► trend + CI ──► site
                                       ▼
                         validation vs hand labels
```

### 5.1 Stages

1. **Boundary prep:** load lake polygons, apply a buffer (for example 100–200 m, tune in D1) to capture shrinkage and expansion, and assign stable `lake_id`s.
2. **Scene search and lock:** query STAC per year and season window. Write the chosen item IDs to `scenes.lock.json` so a rerun uses the same inputs.
3. **Masking:** use the Scene Classification Layer (SCL) to exclude cloud, cloud shadow and cirrus. Class 6 is water in the Sentinel-2 L2A SCL. **Verify the asset name and class codes in the STAC item metadata** (the official example page did not list them).
4. **Radiometry:** convert digital numbers to reflectance using the scale and offset in the STAC metadata. Sentinel-2 processing changes in 2022 introduced a reflectance offset. **Read the offset from metadata; do not hard-code it.** Mixing years without handling this would bias indices.
5. **Compositing:** per lake and year, take the median of valid observations within a fixed same-season window. Report `n_scenes` and `valid_frac`.
6. **Segmentation:** see Section 6.
7. **Measurement:** water area in hectares (one 10 m pixel is 100 m², so 100 pixels is 1 ha) plus an uncertainty range (Section 7).
8. **Trend:** per-lake slope with confidence interval (Section 8).
9. **Validation:** compare against hand labels on held-out lakes (Section 9).
10. **Publish:** build a static site from GeoJSON and Parquet (Section 11).

### 5.2 Data model

`lakes.gpkg`
- `lake_id` (stable string), `name`, `source`, `geometry`, `ref_area_ha`, `flags` (for example `vegetated`, `small`, `seasonal`).

`observations.parquet`
- `lake_id`, `year`, `season`, `method`, `water_area_ha`, `area_lo_ha`, `area_hi_ha`, `valid_frac`, `n_scenes`, `veg_flag`.

`scenes.lock.json`
- STAC item IDs, collection, datetime, cloud cover, processing baseline, per lake-year.

`labels/` (hand labels)
- One GeoTIFF or GeoPackage per labelled lake-date, plus a `labels.csv` with annotator, date, imagery source and licence.

---

## 6. Methods

### 6.1 Tier 1: index baselines (always build first)
- **NDWI** (McFeeters): (Green − NIR) / (Green + NIR).
- **MNDWI** (Xu): (Green − SWIR1) / (Green + SWIR1). Usually better at suppressing built-up areas.
- **Thresholding:** fixed threshold versus Otsu per lake-year. Compare both. A fixed threshold is stable across years but can be wrong for turbid water. Otsu adapts but can fail when a lake is almost fully dry or fully full (a single-class histogram).
- Output: binary mask plus a continuous index map for sensitivity checks.

### 6.2 Tier 2: independent cross-check
- Compare against Dynamic World `water` at a confidence threshold (for example 0.5 or higher; tune on validation lakes only).
- Report agreement (IoU) between Tier 1 and Dynamic World per lake-year. Large disagreement flags lake-years for manual review.

### 6.3 Tier 3: small U-Net (build only if Tier 1 fails on your validation lakes, see D4)
- **Library:** PyTorch with `segmentation_models_pytorch` and a small pretrained encoder (ResNet18 or 34).
- **Inputs:** Green, Red, NIR, SWIR1 (and optionally Blue, SWIR2), normalized per band.
- **Chips:** 256×256 around lake polygons plus negative background chips.
- **Loss:** BCE + Dice.
- **Labels:** hand labels (best) and/or weak labels from the agreement of MNDWI and Dynamic World (see D5). Weak labels are noisy, so keep a hand-labelled test set untouched.
- **Split:** **by lake**, never by random chip. Random chip splits leak neighbouring pixels from the same lake into both train and test and inflate scores.
- **Compute:** small enough for a free GPU notebook (see D8). CPU inference is fine.
- **Uncertainty:** probability map thresholded at several levels, or a small ensemble.

### 6.4 Known hard cases (document in the report)
- **Algae or floating vegetation** over water, common in nutrient-rich urban lakes (hypothesis: check in your own imagery). Indices can label vegetated water as land. Handle with a `veg_flag` (NDVI inside the boundary) and avoid counting it as water loss.
- **Small lakes:** at 10 m, a 1 ha lake is about 100 pixels and edge pixels dominate. Set a minimum size (D1).
- **Seasonality:** lake level swings with monsoon timing. Compare same-season composites only.
- **Construction and dry-bed activity:** dried lakebeds can look like bare soil or built-up land.
- **Shadows and haze** can mimic water. Rely on SCL masking plus `valid_frac` limits.

---

## 7. Uncertainty

Report three kinds, separately:

1. **Edge (mixed-pixel) uncertainty:** a rough bound is half a pixel (about 5 m) along the shoreline, so area uncertainty is roughly perimeter × 5 m. This is a rule of thumb, not a derived result; validate it against hand labels.
2. **Threshold sensitivity:** area at several thresholds (for example the Otsu value ± a margin, and Dynamic World at 0.3, 0.5 and 0.7).
3. **Sampling/cloud uncertainty:** `valid_frac` and `n_scenes`. Drop or flag lake-years below a minimum valid fraction (D7).

Final `area_lo` and `area_hi` combine these. Document exactly how.

---

## 8. Trend analysis

- Per lake, fit a Theil–Sen slope to annual same-season area, plus a Mann–Kendall trend test (for example with `pymannkendall`).
- **Power warning:** about 8–10 yearly points gives low statistical power. Report the slope with a bootstrap confidence interval and say plainly when the data cannot distinguish a trend from noise.
- Apply a multiple-comparison correction (for example Benjamini–Hochberg) when reporting how many lakes "significantly" shrank.
- Never claim causation. This project measures extent, not causes.

---

## 9. Validation protocol (fix this before running experiments)

### 9.1 Labels (see D5 and D6)
- Target: 20–30 lakes, spanning large, small, clean, algae-covered and seasonal, each labelled on at least 2 dates (for example one wet-season and one dry-season).
- Labelling tool: QGIS or similar. Record annotator, date and imagery source.
- Use a second annotator on a subset (about 5 lakes) to measure label agreement. This gives you a ceiling for any model.
- **Imagery licence caution:** labelling on commercial basemap imagery can conflict with its terms of service. Verify before using any basemap for labels.

### 9.2 Splits
- Split **by lake**. Keep a test set of lakes that is never used for threshold tuning or training.
- Tune thresholds only on a separate validation set of lakes.

### 9.3 Metrics
- **Pixel level:** IoU and F1 for water.
- **Area level:** relative area error per lake (the metric that matters for the headline).
- **Trend level:** sign agreement between estimated and hand-labelled area change over a lake's labelled dates.
- **Calibration of the interval:** how often the hand-labelled area falls inside `[area_lo, area_hi]`. If a nominal 90% range covers far less, the uncertainty model is wrong.
- Break results down by lake type (clean, algae-covered, small).

### 9.4 Success criteria (proposed starting points, adjust after a pilot and before the main run)
- Median relative area error on held-out clean lakes under 10%.
- Interval coverage within 10 percentage points of nominal.
- Documented failure rates on algae-covered and small lakes.

Write the final criteria into the repo before the main experiments so results cannot be tuned after the fact.

---

## 10. Repository layout

```
lakewatch-blr/
├─ README.md                 # 60-second quickstart, results, limits
├─ pyproject.toml
├─ Makefile                  # make data | make eval | make site
├─ configs/
│   ├─ aoi.geojson
│   ├─ seasons.yaml
│   └─ experiment.yaml       # thresholds, seeds, metric targets
├─ data/                     # gitignored; README explains how to fetch
│   ├─ lakes.gpkg
│   ├─ scenes.lock.json      # committed
│   └─ labels/               # committed if licence allows
├─ src/lakewatch/
│   ├─ stac.py               # search, lock, load
│   ├─ mask.py               # SCL cloud masking
│   ├─ radiometry.py         # scale/offset from STAC metadata
│   ├─ composite.py
│   ├─ indices.py            # NDWI, MNDWI
│   ├─ segment/              # threshold.py, dynworld.py, unet.py
│   ├─ measure.py            # area + uncertainty
│   ├─ trend.py
│   ├─ validate.py
│   └─ cli.py                # Typer CLI
├─ tests/
├─ notebooks/                # exploration only
├─ site/                     # static map (MapLibre or Leaflet)
├─ docs/
│   ├─ METHODS.md
│   ├─ VALIDATION.md
│   └─ LIMITATIONS.md
└─ .github/workflows/ci.yml
```

### CLI sketch
```
lakewatch lock     --aoi configs/aoi.geojson --years 2017-2025 --season post_monsoon
lakewatch composite --lock data/scenes.lock.json
lakewatch segment  --method mndwi|dynworld|unet
lakewatch measure  --out data/observations.parquet
lakewatch validate --labels data/labels --report docs/VALIDATION.md
lakewatch site     --out site/data
```

### Suggested stack
- Python 3.11+, `pystac-client`, `planetary-computer`, `odc-stac` (or `stackstac`), `xarray`, `rioxarray`, `rasterio`, `geopandas`, `shapely`, `scikit-image`, `scikit-learn`, `scipy`, `pymannkendall`.
- Optional: PyTorch, `segmentation_models_pytorch`.
- Storage: GeoPackage, Parquet, COG. DuckDB is optional for queries.
- Tooling: `uv`, `ruff`, `pytest`, Typer, Pydantic for config, GitHub Actions, Docker (optional).

---

## 11. Demo and outputs

- **Static site:** MapLibre GL JS or Leaflet, a year slider, lake polygons coloured by change, click-through to a per-lake chart with uncertainty bands and a "confidence" badge.
- **Hosting:** GitHub Pages, no server required.
- **Per-lake page:** water mask thumbnails by year, area series, trend CI, and flags (algae-covered, small, low valid fraction).
- **Honesty panel:** a visible section listing which lakes are unreliable and why.
- **Attribution:** include Copernicus Sentinel and Dynamic World attributions as required by their licences.

---

## 12. Decisions needed

Each gate is a point in the plan. If unanswered, the default is used.

| ID | Decision | Options | Default | Gate |
|---|---|---|---|---|
| D1 | Which lakes? | (a) 6 famous lakes only, (b) 25–40 lakes mixed size and condition, (c) all lakes above a size threshold | (b), with a minimum lake size of about 2 ha | Before Week 1 |
| D2 | Boundary source | OSM polygons + manual fixes, manual digitizing, KLCDA reports (PDF only) | OSM + manual fixes, after checking completeness | Week 1, day 2 |
| D3 | Time span and season windows | Start 2016 vs 2017; post-monsoon vs pre-monsoon vs both | 2017–latest, one fixed window chosen after counting valid scenes per window | Week 1 |
| D4 | Method ambition | Indices only; indices + U-Net; U-Net as primary | Indices first; add U-Net only if validation shows indices fail on a meaningful share of lakes | End of Week 2 |
| D5 | Label strategy | Hand labels only; weak labels only; both | Hand labels for test, weak labels allowed for training | Week 2 |
| D6 | Label imagery source | Label on Sentinel-2 composite itself; use another licensed high-res source | Sentinel-2 composite (check any other source's licence first) | Week 2 |
| D7 | Quality gates | Minimum `valid_frac`, minimum `n_scenes`, minimum lake size | `valid_frac` ≥ 0.8 and `n_scenes` ≥ 3, tune after pilot | End of Week 2 |
| D8 | Compute | Local CPU only; free GPU notebook for training | Local CPU for everything except U-Net training | Before Week 3 |
| D9 | Imagery access | Planetary Computer; Copernicus Data Space; Earth Engine | Planetary Computer | Before Week 1 |
| D10 | Packaging | Notebooks only; CLI + library | CLI + library | Before Week 1 |
| D11 | Demo stack | Static map on GitHub Pages; Streamlit | Static map | Week 3 |
| D12 | Licences | Code: MIT or Apache-2.0. Output data: CC BY 4.0 or CC0. Do not redistribute the CC BY-NC lake survey CSV | MIT + CC BY 4.0 for derived data | Before first publish |
| D13 | Algae-covered lakes | Count vegetated water as water; exclude; flag only | Flag with `veg_flag`; report separately | Week 2 |
| D14 | Write-up | README only; blog post; arXiv-style note | README + blog post | Week 4 |
| D15 | Name and repo | Keep `lakewatch-blr`; pick another | Check for collisions first | Before first publish |
| D16 | Extension in time | Sentinel-2 only; add Landsat for earlier years | Sentinel-2 only for v1 | Week 1 |

---

## 13. What was verified and what was not

### Verified in this research (from fetched pages)
- Planetary Computer: collection `sentinel-2-l2a`; STAC search with `pystac-client`; signing with `planetary_computer.sign_inplace`; optional API key; `eo:cloud_cover` filter; cloud-optimized GeoTIFF; revisit about 5 days; processing with Sen2Cor.
- Dynamic World V1: 10 m, 2015-06-27 to present, `water` probability band, CC-BY 4.0 with attribution, built from Sentinel-2 L1C images with cloud cover ≤ 35%, recommends thresholding top-1 probability.
- OpenCity Inventory of Lakes: 5 PDFs, public domain, no geospatial format listed, created 2023-01-06 and updated 2025-11-25.
- OpenCity Lake Assets Survey 2023: CSV, CC BY-NC 2.0, geometry not stated.
- S1S2-Water mirror: 65 triplets, about 170 GB, licence not stated on the mirror (see the Zenodo record).

### Not verified (check before relying on them)
- SCL asset name and class codes on Planetary Computer (confirm in an STAC item).
- The 2022 reflectance offset handling on Planetary Computer (confirm from `raster:bands` metadata).
- Valid-scene counts per season and year over Bengaluru, including cloud cover in monsoon months.
- OpenStreetMap completeness and accuracy for Bengaluru lake polygons.
- The S1S2-Water licence.
- Whether any open Bengaluru lake tracker already exists (run a GitHub and paper search before publishing).
- The assumption that nutrient-rich lakes are often algae-covered in satellite imagery (confirm on your own composites).
- Licensing terms for any high-resolution imagery you might use to label.

---

## 14. Plan (4 weeks)

### Week 1: foundations
- Settle D1, D2, D3, D9, D10, D16.
- Build boundary set; run STAC searches; count valid scenes per year and window; write `scenes.lock.json`.
- Implement masking, radiometry, compositing; produce a first composite for one lake and look at it.
- **Exit check:** one lake, one year, a correct visual composite and a first water mask.

### Week 2: baselines and labels
- Implement NDWI/MNDWI + thresholding and the Dynamic World cross-check.
- Start hand labelling (settle D5, D6, D13). Measure second-annotator agreement.
- Pilot validation on a few lakes; settle D7 and D4.
- **Exit check:** baseline metrics on a labelled validation set, with failures listed.

### Week 3: measurement and demo
- Area and uncertainty (Section 7); trend analysis (Section 8).
- If D4 says yes: train and evaluate the U-Net with a lake-level split (settle D8).
- Build the static site (D11).
- **Exit check:** full pipeline from `lock` to `site` runs end to end on all chosen lakes.

### Week 4: rigor and release
- Freeze success criteria (Section 9.4) if not already frozen; run the final evaluation once.
- Write METHODS, VALIDATION and LIMITATIONS docs; add tests and CI; add a demo GIF.
- Settle D12, D14, D15; publish.
- **Exit check:** a stranger can reproduce the headline numbers from the README.

---

## 15. Testing and CI

- **Unit tests:** index formulas on tiny synthetic rasters; area calculation (pixel size and CRS); trend function on synthetic series with a known slope.
- **Golden test:** a small fixed AOI with pinned scenes and expected area within a tolerance.
- **Regression gate:** a frozen mini-benchmark of labelled chips. CI fails if IoU drops below the committed threshold.
- **Reproducibility:** fixed seeds; pinned dependencies; `scenes.lock.json` committed.
- **Data hygiene:** assert no lake appears in both train and test sets.

---

## 16. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Too few clear scenes in monsoon-heavy windows | Missing lake-years | Choose the window from measured counts (D3); report coverage openly |
| Boundary polygons wrong or incomplete | Biased areas | Visual check of every lake; manual fixes; keep a boundary changelog |
| Hand labelling is slow | Delays validation | Cap at 20–30 lakes; start in Week 2; label by priority |
| Indices fail on algae-covered lakes | Misleading shrinkage | `veg_flag`; separate reporting; optional U-Net |
| Over-claiming trends from about 10 points | Credibility loss | Report CIs; state when data are inconclusive |
| Licence conflicts (CC BY-NC data, basemap terms) | Cannot publish outputs | Resolve D6 and D12 early; keep NC data out of published artifacts |
| Scope creep (water quality, forecasting, more cities) | Unfinished project | Hold to Section 2; list ideas under "future work" |

---

## 17. Resume bullet template (fill in only with measured values)

> Built and open-sourced **LakeWatch BLR**, a reproducible Sentinel-2 pipeline that measures yearly water extent for **[N]** Bengaluru lakes (**[start year]–[end year]**), with per-lake uncertainty and held-out-lake validation (median area error **[X]%**, interval coverage **[Y]%** against **[M]** hand-labelled lakes); documented failure modes on algae-covered and small lakes and published an interactive map.

Do not add the bullet until the numbers exist.

---

## 18. Definition of done

- The README quickstart reproduces the main results on a clean machine.
- Success criteria were written down before the final run, and the final results are reported against them, including misses.
- LIMITATIONS lists every known failure case with examples.
- Licences and attributions are correct for code, derived data and every input.
- The demo is live and shows uncertainty, not just a single line per lake.

---

## 19. Sources

- [Microsoft Planetary Computer: Sentinel-2 L2A example](https://nbviewer.org/github/microsoft/PlanetaryComputerExamples/blob/main/datasets/sentinel-2-l2a/sentinel-2-l2a-example.ipynb)
- [odc-stac: access Sentinel-2 on Planetary Computer](https://odc-stac.readthedocs.io/en/latest/notebooks/stac-load-S2-ms.html)
- [Dynamic World V1 (Earth Engine catalog)](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)
- [OpenCity: Inventory of Lakes, Bengaluru Metropolitan Area](https://data.opencity.in/dataset/inventory-of-lakes-bengaluru-metropolitan-area)
- [OpenCity: Bengaluru Lake Assets Survey](https://data.opencity.in/dataset/bengaluru-lake-assets-survey-data)
- [S1S2-Water (Hugging Face mirror)](https://huggingface.co/datasets/idomogalla/s1s2_water) and its [Zenodo record](https://zenodo.org/records/11278238)
- [ArcGIS: measure shrinking lakes using deep learning](https://developers.arcgis.com/python/latest/samples/measure-shrinking-lakes-using-deep-learning/)
- [Lake surface closed-curve prediction framework](https://yorkspace.library.yorku.ca/items/8e87abc9-de96-493c-ada0-6df9df8373b4)