"""Sentinel-2 L2A scene search and locking on Planetary Computer."""

import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import planetary_computer as pc
import pystac_client

CATALOG = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
# Same-season window (MM-DD). D3: winter chosen 2026-10-26 from clear-day counts, see README.
SEASONS = {"winter": ("01-01", "02-28")}


def client(signed: bool = True):
    return pystac_client.Client.open(CATALOG, modifier=pc.sign_inplace if signed else None)


def parse_boa_offset(xml: str) -> int:
    """BOA_ADD_OFFSET from MTD_MSIL2A.xml. Absent before processing baseline 04.00, so 0."""
    offsets = {int(v) for v in re.findall(r"<BOA_ADD_OFFSET[^>]*>([^<]+)</BOA_ADD_OFFSET>", xml)}
    assert len(offsets) <= 1, f"per-band offsets differ: {offsets}"
    return offsets.pop() if offsets else 0


def boa_offset(item) -> int:
    # Not in STAC raster:bands on Planetary Computer (checked 2026-10-26); only in the product XML.
    with urllib.request.urlopen(item.assets["product-metadata"].href, timeout=60) as r:
        return parse_boa_offset(r.read().decode())


def lock(aoi: dict, years: range, max_cloud: float = 50) -> list[dict]:
    """Every scene over `aoi` in each year x season window, with what's needed to reload it exactly."""
    cat = client()
    rows = []
    for year in years:
        for season, (start, end) in SEASONS.items():
            items = cat.search(
                collections=[COLLECTION],
                intersects=aoi,
                datetime=f"{year}-{start}/{year}-{end}",
                query={"eo:cloud_cover": {"lt": max_cloud}},
            ).item_collection()
            for it in items:
                rows.append({"year": year, "season": season, "item": it})
    with ThreadPoolExecutor(16) as ex:
        offsets = list(ex.map(lambda r: boa_offset(r["item"]), rows))
    return [
        {
            "year": r["year"],
            "season": r["season"],
            "id": r["item"].id,
            "datetime": r["item"].properties["datetime"],
            "cloud_cover": r["item"].properties["eo:cloud_cover"],
            "processing_baseline": r["item"].properties.get("s2:processing_baseline"),
            "boa_offset": off,
        }
        for r, off in zip(rows, offsets)
    ]


def fetch_items(ids: list[str]):
    """Re-fetch locked items by ID, unsigned: SAS tokens expire after ~1 h, so sign right before reading."""
    items = {it.id: it for it in client(signed=False).search(collections=[COLLECTION], ids=ids).items()}
    missing = set(ids) - set(items)
    assert not missing, f"locked items no longer in catalog: {sorted(missing)[:5]}"
    return [items[i] for i in ids]
