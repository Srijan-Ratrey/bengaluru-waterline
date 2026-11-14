import datetime as dt
import json
import tomllib
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import typer
from skimage.io import imsave

from lakewatch import composite as comp
from lakewatch import dynworld, labels, stac, trends
from lakewatch import evaluate as evaluation
from lakewatch import lakes as lakes_mod
from lakewatch.indices import measure as measure_lake_year
from lakewatch.indices import mndwi, ndvi

app = typer.Typer(no_args_is_help=True)
AOI = Path("configs/aoi.geojson")
LAKES = Path("configs/lakes.geojson")
LOCK = Path("data/scenes.lock.json")
COMPOSITES = Path("data/composites")
OBS = Path("data/observations.parquet")
SPLIT = Path("configs/split.json")
LABELS = Path("data/labels/labels.gpkg")
EXPERIMENT = Path("configs/experiment.toml")


@app.command()
def lakes(per_bin: int = 12, seed: int = 0):
    """Fetch OSM lake candidates and write a size-stratified selection to configs/lakes.geojson."""
    cands = lakes_mod.fetch(shapely.geometry.shape(json.loads(AOI.read_text())))
    picked = lakes_mod.select(cands, per_bin, seed)
    picked.to_file(LAKES, driver="GeoJSON")
    typer.echo(f"{len(cands)} candidates -> {len(picked)} lakes in {LAKES}")
    typer.echo(picked[["lake_id", "name", "area_ha"]].round(1).to_string())


@app.command()
def lock(years: str = "2018-2025", max_cloud: float = 50):
    """Pin every scene per year x season window to data/scenes.lock.json and print counts."""
    y0, y1 = map(int, years.split("-"))
    rows = stac.lock(json.loads(AOI.read_text()), range(y0, y1 + 1), max_cloud)
    LOCK.parent.mkdir(exist_ok=True)
    LOCK.write_text(json.dumps(rows, indent=1))
    # Scenes from adjacent tiles on the same day count once.
    clear = {(r["year"], r["season"], r["datetime"][:10]) for r in rows if r["cloud_cover"] < 20}
    days = Counter((y, s) for y, s, _ in clear)
    typer.echo(f"{len(rows)} items -> {LOCK}\nclear days (tile cloud < 20%) per year x season:")
    typer.echo("year  " + "  ".join(f"{s:>12}" for s in stac.SEASONS))
    for y in range(y0, y1 + 1):
        typer.echo(f"{y}  " + "  ".join(f"{days[(y, s)]:>12}" for s in stac.SEASONS))


@app.command()
def sheet(
    only: str = typer.Option("", help="Comma-separated lake_ids (default: all)"),
    out: Path = Path("data/sheets"),
):
    """Per-lake PNG from cached composites: rows = true colour, MNDWI>0, DW>=0.5; one column per year."""
    names = gpd.read_file(LAKES).set_index("lake_id")["name"]
    out.mkdir(parents=True, exist_ok=True)
    for lake in only.split(",") if only else names.index:
        cols = []
        for path in sorted(COMPOSITES.glob(f"{lake}_*.tif")):
            c = comp.load(path)
            inside = c["inside"].values[..., None]
            rgb = np.nan_to_num(np.clip(np.stack([c["B04"], c["B03"], c["B02"]], -1) / 0.3, 0, 1))
            dim = np.where(inside, rgb * 0.5, rgb * 0.15)
            blue = np.array([0.1, 0.4, 1.0])
            masks = [
                (mndwi(c).values > 0) & c["inside"].values,
                (c["dw_water"].values >= 0.5) & c["inside"].values,
            ]
            tiles = [rgb] + [np.where(m[..., None], blue, dim) for m in masks]
            cols.append(
                np.concatenate([np.pad(t, ((2, 2), (2, 2), (0, 0)), constant_values=1) for t in tiles], 0)
            )
        if not cols:
            continue
        dst = out / f"{lake}.png"
        imsave(dst, (np.concatenate(cols, 1) * 255).astype("uint8"), check_contrast=False)
        typer.echo(f"{names[lake]} ({len(cols)} years) -> {dst}")


@app.command()
def measure(
    ee_project: str = typer.Option(..., envvar="EE_PROJECT", help="Earth Engine Cloud project ID"),
    only: str = typer.Option("", help="Comma-separated lake_ids (default: all)"),
):
    """Composite (cached as GeoTIFF in data/composites) + all methods for every lake-year -> observations.parquet."""
    dynworld.init(ee_project)
    g = gpd.read_file(LAKES).set_index("lake_id").to_crs(comp.CRS)
    g_ll = g.to_crs(4326)
    lock = json.loads(LOCK.read_text())
    items = dict(zip([r["id"] for r in lock], stac.fetch_items([r["id"] for r in lock])))
    lake_ids = only.split(",") if only else list(g.index)
    COMPOSITES.mkdir(parents=True, exist_ok=True)
    rows, failed = [], []
    for lake in lake_ids:
        for (year, season), recs in _group(lock).items():
            path = COMPOSITES / f"{lake}_{year}_{season}.tif"
            try:
                if path.exists():
                    c = comp.load(path)
                else:
                    recs = [
                        r
                        for r in recs
                        if shapely.geometry.shape(items[r["id"]].geometry).intersects(g_ll.geometry[lake])
                    ]
                    c = comp.composite(
                        [items[r["id"]] for r in recs], [r["boa_offset"] for r in recs], g.geometry[lake]
                    )
                    start, end = stac.SEASONS[season]
                    end_excl = dt.date.fromisoformat(f"{year}-{end}") + dt.timedelta(days=1)
                    c["dw_water"] = (
                        ("y", "x"),
                        dynworld.water_prob(c.odc.geobox, f"{year}-{start}", str(end_excl)),
                    )
                    comp.save(c, path)
                if c.attrs["valid_frac"] == 0:
                    failed.append((lake, year, "no valid pixels"))
                    continue
                base = {"lake_id": lake, "year": year, "season": season}
                rows += [base | r for r in measure_lake_year(c, c["dw_water"].values)]
                typer.echo(
                    f"{lake} {year}: n_scenes={c.attrs['n_scenes']} valid_frac={c.attrs['valid_frac']:.2f}"
                )
            except Exception as e:  # noqa: BLE001 -- keep the long run going; every failure is reported below
                failed.append((lake, year, repr(e)))
                typer.echo(f"{lake} {year}: FAILED {e!r}", err=True)
    obs = pd.DataFrame(rows)
    obs.to_parquet(OBS, index=False)
    typer.echo(f"{len(obs)} rows -> {OBS}; {len(failed)} lake-years failed")
    for f in failed:
        typer.echo(f"  {f}")
    if failed:
        raise typer.Exit(1)


@app.command()
def label_prep(out: Path = Path("data/labelling"), seed: int = 0):
    """Freeze the lake split (configs/split.json) and export QGIS inputs for test+val lakes x LABEL_YEARS."""
    g = gpd.read_file(LAKES)
    veg = pd.read_parquet(OBS).query("method == 'mndwi_zero'").groupby("lake_id")["veg_frac"].median()
    if SPLIT.exists():
        sets = json.loads(SPLIT.read_text())
        typer.echo(f"{SPLIT} exists; reusing it (delete it to re-split)")
    else:
        sets = labels.split(g.assign(veg_frac=g["lake_id"].map(veg)), seed)
        SPLIT.write_text(json.dumps({"seed": seed, **sets}, indent=1) + "\n")
    out.mkdir(parents=True, exist_ok=True)
    for lake in sets["test"] + sets["val"]:
        for year in labels.LABEL_YEARS:
            c = comp.load(COMPOSITES / f"{lake}_{year}_winter.tif")
            labels.export_8bit(c, ["B04", "B03", "B02"], 0.3, out / f"{lake}_{year}_rgb.tif")
            labels.export_8bit(c, ["B11", "B08", "B04"], 0.4, out / f"{lake}_{year}_swir.tif")
    utm = g.to_crs(comp.CRS)
    utm.to_file(out / "lakes.gpkg", layer="lakes")
    utm.assign(geometry=utm.buffer(150)).to_file(out / "lakes.gpkg", layer="lake_regions")
    if not LABELS.exists():
        LABELS.parent.mkdir(parents=True, exist_ok=True)
        labels.empty_labels(LABELS, comp.CRS)
    n = 2 * len(sets["test"] + sets["val"])
    typer.echo(
        f"test={len(sets['test'])} val={len(sets['val'])} train={len(sets['train'])}; {n} lake-years -> {out}"
    )


@app.command()
def evaluate(subset: str = typer.Argument("val", help="val or test")):
    """Score every method x threshold against the hand labels of one split -> data/eval_<subset>.parquet."""
    exp = tomllib.loads(EXPERIMENT.read_text())
    if subset == "test" and "three_class_iou_water_min" not in exp["criteria"]:
        raise typer.BadParameter("freeze the 3-class target in configs/experiment.toml before scoring test")
    sets = json.loads(SPLIT.read_text())
    polys = gpd.read_file(LABELS, layer="labels")
    veg = pd.read_parquet(OBS).query("method == 'mndwi_zero'").groupby("lake_id")["veg_frac"].median()
    grid, rows = [], []
    for lake in sets[subset]:
        for year in labels.LABEL_YEARS:
            c = comp.load(COMPOSITES / f"{lake}_{year}_winter.tif")
            truth = labels.rasterize(polys[(polys.lake_id == lake) & (polys.year == year)], c)
            key = {"lake_id": lake, "year": year}
            if subset == "val":  # threshold grid for tuning; never computed on test
                grid += [key | r for r in evaluation.score_lake_year(c, truth)]
            rows.append(key | evaluation.assess(c, truth, **exp["method"]))
    if grid:
        pd.DataFrame(grid).to_parquet(f"data/eval_{subset}_grid.parquet", index=False)
    a = pd.DataFrame(rows).assign(
        type=lambda d: np.where(d.lake_id.map(veg) > exp["veg_lake_cutoff"], "veg", "clean")
    )
    a.to_parquet(f"data/eval_{subset}.parquet", index=False)
    typer.echo(a[["lake_id", "year", "type", "area_true", "area", "area_lo", "area_hi"]].round(2).to_string())
    for k, v in evaluation.summary(a).items():
        typer.echo(f"{k:32} {v:.3f}")


@app.command("trends")
def trends_cmd(alpha: float = 0.1):
    """Areas for every lake x year at the frozen method -> data/areas.parquet; per-lake trends -> data/trends.parquet."""
    cfg = tomllib.loads(EXPERIMENT.read_text())["method"]
    names = gpd.read_file(LAKES).set_index("lake_id")["name"]
    rows = [
        {"lake_id": lake, "year": int(p.stem.split("_")[1])} | trends.areas(comp.load(p), **cfg)
        for lake in names.index
        for p in sorted(COMPOSITES.glob(f"{lake}_*_winter.tif"))
    ]
    a = pd.DataFrame(rows)
    a.to_parquet("data/areas.parquet", index=False)
    w, v = trends.trends(a, "area", alpha), trends.trends(a, "veg_ha", alpha)
    t = w.merge(v[["lake_id", "slope", "q", "verdict"]], on="lake_id", suffixes=("", "_veg"))
    first, last = (a[a.year == y].set_index("lake_id")["area"] for y in (a.year.min(), a.year.max()))
    t = t.assign(name=t.lake_id.map(names), area_first=t.lake_id.map(first), area_last=t.lake_id.map(last))
    t.to_parquet("data/trends.parquet", index=False)
    cols = ["name", "area_first", "area_last", "slope", "slope_lo", "slope_hi", "q", "verdict", "verdict_veg"]
    typer.echo(t.sort_values("slope")[cols].round(2).to_string(index=False))
    typer.echo(f"\nwater (q < {alpha}, Benjamini-Hochberg): {t.verdict.value_counts().to_dict()}")
    typer.echo(f"veg:   {t.verdict_veg.value_counts().to_dict()}")


@app.command()
def site(out: Path = Path("site")):
    """Static demo data for site/index.html: per lake-year image overlays + data.js. Run `trends` first."""
    exp = tomllib.loads(EXPERIMENT.read_text())
    g = gpd.read_file(LAKES).set_index("lake_id")
    a = pd.read_parquet("data/areas.parquet").sort_values("year")
    t = pd.read_parquet("data/trends.parquet").set_index("lake_id").round(3)
    split = {lake: k for k, v in json.loads(SPLIT.read_text()).items() if k != "seed" for lake in v}
    veg = pd.read_parquet(OBS).query("method == 'mndwi_zero'").groupby("lake_id")["veg_frac"].median()
    truth = pd.concat(pd.read_parquet(f"data/eval_{s}.parquet") for s in ("val", "test"))
    truth = truth.set_index(["lake_id", "year"])["area_true"]
    (out / "img").mkdir(parents=True, exist_ok=True)
    lakes = []
    for lake, s in a.groupby("lake_id"):
        for p in sorted(COMPOSITES.glob(f"{lake}_*_winter.tif")):
            bounds = _overlays(comp.load(p), exp["method"], out / "img" / p.stem.removesuffix("_winter"))
        flags = {
            "vegetated": veg[lake] > exp["veg_lake_cutoff"],
            "wide interval": ((s.area_hi - s.area_lo) / s.area.clip(lower=0.5)).median() > 1,
        }
        tr = t.loc[lake, ["verdict", "slope", "slope_lo", "slope_hi", "q", "verdict_veg", "slope_veg"]]
        lakes.append(
            {"id": lake, "name": g.name[lake], "split": split.get(lake), "bounds": bounds,
             "flags": [k for k, on in flags.items() if on], "geometry": g.geometry[lake].__geo_interface__}
            | tr.to_dict()
            | s[["year", "area", "area_lo", "area_hi", "water_ha", "veg_ha", "land_ha"]].round(2).to_dict("list")
            | {"labelled": [truth.get((lake, y)) for y in s.year]}
        )  # fmt: skip
    (out / "data.js").write_text("const DATA = " + json.dumps(lakes, allow_nan=False) + ";\n")
    typer.echo(f"{len(lakes)} lakes -> {out}; open {out / 'index.html'}")


def _overlays(c, cfg: dict, stem: Path) -> list:
    """Write <stem>_rgb.jpg (true colour) and <stem>_cls.png (water blue, veg green, rest transparent),
    both reprojected to web mercator so Leaflet can place them by lat/lon bounds. Returns the bounds."""
    c["cls"] = (
        ("y", "x"),
        evaluation.classify(
            evaluation.scores(c)[cfg["method"]], ndvi(c).values, c["inside"].values, c["lake"].values,
            cfg["water_t"], cfg["veg_t"],
        ).astype("float32"),  # float + NaN nodata: as uint8, reproject treats LAND (0) as nodata and fills it
    )  # fmt: skip
    w = c[["B04", "B03", "B02", "cls"]].odc.reproject("EPSG:3857", resampling="nearest")
    rgb = np.nan_to_num(np.clip(np.stack([w.B04, w.B03, w.B02], -1) / 0.3, 0, 1))
    imsave(f"{stem}_rgb.jpg", (rgb * 255).astype("uint8"))
    rgba = np.array([[0, 0, 0, 0], [30, 110, 255, 210], [40, 190, 60, 210]], "uint8")  # LAND, WATER, VEG
    imsave(f"{stem}_cls.png", rgba[np.nan_to_num(w.cls.values).astype(int)], check_contrast=False)
    b = w.odc.geobox.extent.to_crs(4326).boundingbox
    return [[b.bottom, b.left], [b.top, b.right]]


def _group(lock: list[dict]) -> dict:
    out = {}
    for r in lock:
        out.setdefault((r["year"], r["season"]), []).append(r)
    return dict(sorted(out.items()))
