import datetime as dt
import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import typer
from skimage.io import imsave

from lakewatch import composite as comp
from lakewatch import dynworld, stac
from lakewatch import lakes as lakes_mod
from lakewatch.indices import measure as measure_lake_year
from lakewatch.indices import mndwi

app = typer.Typer(no_args_is_help=True)
AOI = Path("configs/aoi.geojson")
LAKES = Path("configs/lakes.geojson")
LOCK = Path("data/scenes.lock.json")
COMPOSITES = Path("data/composites")
OBS = Path("data/observations.parquet")


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


def _group(lock: list[dict]) -> dict:
    out = {}
    for r in lock:
        out.setdefault((r["year"], r["season"]), []).append(r)
    return dict(sorted(out.items()))
