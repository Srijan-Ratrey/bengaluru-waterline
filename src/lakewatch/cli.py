import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
import typer
from skimage.io import imsave

from lakewatch import lakes as lakes_mod
from lakewatch import stac
from lakewatch.composite import composite
from lakewatch.indices import area_ha, mndwi, threshold

app = typer.Typer(no_args_is_help=True)
AOI = Path("configs/aoi.geojson")
LAKES = Path("configs/lakes.geojson")
LOCK = Path("data/scenes.lock.json")


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
def preview(lake: str, year: int, season: str = "winter", out: Path = Path("data/preview")):
    """Composite + MNDWI/Otsu water mask for one lake-year; writes a PNG (RGB | mask)."""
    g = gpd.read_file(LAKES).set_index("lake_id").to_crs("EPSG:32643")
    rows = [r for r in json.loads(LOCK.read_text()) if r["year"] == year and r["season"] == season]
    lake_ll = g.to_crs(4326).geometry[lake]
    pairs = [
        (it, r["boa_offset"])
        for r, it in zip(rows, stac.fetch_items([r["id"] for r in rows]))
        if shapely.geometry.shape(it.geometry).intersects(lake_ll)
    ]
    c = composite([it for it, _ in pairs], [o for _, o in pairs], g.geometry[lake])
    idx = mndwi(c)
    t = threshold(idx, c["inside"])
    water = (idx > t) & c["inside"]
    typer.echo(
        f"{g.name[lake]} {year} {season}: {area_ha(water):.1f} ha water (OSM {g.area_ha[lake]:.1f} ha), "
        f"otsu={t:.3f} n_scenes={c.n_scenes} valid_frac={c.valid_frac:.2f}"
    )
    rgb = np.clip(np.stack([c["B04"], c["B03"], c["B02"]], -1) / 0.3, 0, 1)
    rgb = np.nan_to_num(rgb)
    mask_img = np.where(np.asarray(water)[..., None], [0.1, 0.4, 1.0], rgb * 0.5)
    mask_img[~np.asarray(c["inside"])] *= 0.3
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{lake}_{year}_{season}.png"
    imsave(path, (np.concatenate([rgb, mask_img], 1) * 255).astype("uint8"))
    typer.echo(f"-> {path}")
