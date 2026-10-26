# LakeWatch

Satellite lake-extent tracker for Bengaluru. Measures per-lake yearly water area from Sentinel-2, with uncertainty and held-out-lake validation.

Full spec: [lakewatch-tech-spec.md](lakewatch-tech-spec.md)

## Decisions (as of 2026-10-26)

| ID | Decision |
|---|---|
| D1 | 25–40 lakes, mixed size and condition, minimum ~2 ha |
| D3 | 2017 to latest; one same-season window, chosen after counting valid scenes |
| D4 | Indices + U-Net (U-Net built regardless of index results) |
| D9 | Planetary Computer for Sentinel-2 (Dynamic World still via Earth Engine) |
| D10 | CLI + library |
| D12 | Licence: undecided, repo private until settled |
| D15 | Name: LakeWatch. Note: `0x101/lakewatch` and `Clnay5/lakewatch` are similar Sentinel-2 lake projects; review them before any novelty claim |
| D16 | Sentinel-2 only for v1 |

Still on spec defaults until their gates: D2, D5, D6, D7, D8, D11, D13, D14.
