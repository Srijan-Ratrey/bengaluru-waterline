"""Lake boundaries from OpenStreetMap."""

import geopandas as gpd
import osmnx as ox
import pandas as pd

UTM = "EPSG:32643"
NOT_LAKES = {"drain", "wastewater", "basin", "river", "stream", "canal"}
SIZE_BINS = [2, 10, 50, float("inf")]  # ha


def fetch(aoi, min_ha: float = 2.0) -> gpd.GeoDataFrame:
    """Named, lake-like OSM water polygons of at least `min_ha` intersecting `aoi`."""
    g = ox.features_from_polygon(aoi, tags={"natural": "water", "landuse": "reservoir", "water": True})
    g = g[g.geom_type.isin(["Polygon", "MultiPolygon"]) & ~g["water"].isin(NOT_LAKES) & g["name"].notna()]
    g = g.reset_index()
    g["lake_id"] = g["element"].str[0] + g["id"].astype(str)  # w41662659, r19751547
    g["area_ha"] = g.to_crs(UTM).area / 1e4
    g = g[g["area_ha"] >= min_ha].sort_values("area_ha", ascending=False)
    # Drop polygons sitting inside a larger one (e.g. a pond mapped within a lake relation).
    pts = g.representative_point()
    nested = [any(pts.iloc[i].within(big) for big in g.geometry.iloc[:i]) for i in range(len(g))]
    return g.loc[[not n for n in nested], ["lake_id", "name", "area_ha", "geometry"]].reset_index(drop=True)


def select(g: gpd.GeoDataFrame, per_bin: int = 12, seed: int = 0) -> gpd.GeoDataFrame:
    """Size-stratified sample: `per_bin` lakes from each of 2-10, 10-50 and 50+ ha."""
    bins = pd.cut(g["area_ha"], SIZE_BINS, right=False)
    picked = g.groupby(bins, observed=True).sample(n=per_bin, random_state=seed)
    return picked.sort_values("area_ha", ascending=False).reset_index(drop=True)
