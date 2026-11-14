# Limitations

Every known failure case, with examples. Numbers come from [VALIDATION.md](VALIDATION.md) unless noted.

## Measurement

1. **Dark water is undercounted.**
   - Deep or dark water can have SWIR above green, which makes MNDWI negative.
   - Examples (labelled vs estimated): Bagaluru 2025, 56.1 vs 37.7 ha; Budigere 2018, 33.2 vs 22.9 ha; Chudahalli 2018, 39.3 vs 29.2 ha; Hommadevanahalli 2025, 4.0 vs 1.3 ha.
   - On test lakes the median error is −16% on clean lakes and −25% on vegetated ones, which misses the 10% target.
   - All areas and trends carry this bias.
2. **Water with vegetation in it reads as land.**
   - Kogilu 2018: 8.2 ha labelled, 0.8 ha estimated. The missed pixels have NDVI about 0.37: too green for MNDWI, not green enough to be called vegetation.
3. **Water and dark wet ground get confused.**
   - Sarjapur Doddakere 2018: 0 ha labelled, 11.4 ha estimated, on pixels with NDVI about −0.2.
   - It is unresolved whether the method or the label is wrong.
4. **Land inside the lake is the weakest class.**
   - Test IoU 0.46.
   - Grass on a dry bed and weeds on water look alike, and the line between grass and a dry bed is the fuzziest part of the labels too.
5. **Small lakes have wide intervals.**
   - At 10 m, a 2 ha lake is about 200 pixels, and shoreline pixels dominate.
   - 22 of 34 lakes have a median interval wider than their water area. The site flags them as "wide interval".
6. **Dynamic World is not a reliable check on weedy lakes.**
   - It is the best single method on large clean lakes: IoU 0.92-0.94 on Madiwala.
   - But it misses most of weed-margined Hosakote 2018: 21 ha, against 207 ha labelled.
   - So DW disagreement flags a lake-year for a look; it does not decide it.
7. **Shadows and haze** are handled only by the SCL mask.
   - SCL class 2 (dark area) is kept so that dark water isn't masked out.
   - Terrain or building shadow in that class could be counted as water. No case has been seen, but none has been looked for either.
8. **The site's map overlays are only approximate.**
   - The overlays are resampled to web-map projection with nearest-neighbour resampling, for display only.
   - The areas are computed on the original 10 m UTM grid.

## Boundaries

9. **The OSM outlines are taken as given.**
   - Two lakes were dropped (a river corridor, and a lake with no water in any year), but the others weren't redrawn.
   - Water is counted out to 150 m beyond the outline to make up for outlines drawn inside the real shoreline. Water in a nearby pond inside that 150 m also counts.

## Time

10. **Winter only (Jan-Feb).**
    - Monsoon timing changes lake levels, and one season can't show that.
    - The post-monsoon window was dropped because it has only 2-4 clear days a year.
11. **2018-2025 only.**
    - 2017 has 2-4 clear winter days and was dropped.
    - Earlier years would need Landsat, which is out of scope for v1 (D16).

## Trends

12. **There is little power to detect trends.**
    - With 8 points, 31 of 34 lakes come out as "no clear trend" for water.
    - Year-to-year swings are large. Hosakote, for example: 180, 24, 25, 22, 233, 257, 235, 22 ha.
    - "No clear trend" means the data can't tell; it does not mean the lake is stable.
13. **Per-year intervals don't feed into the slope CI.**
    - The CI reflects scatter between years only.
    - A steady bias, like the dark-water undercount, shifts every year's area but leaves the slope's CI unchanged.

## Validation

14. **One annotator.** There is no agreement ceiling, and the labeller's biases are built into every metric.
15. **Only 2 of 8 years are labelled, on 20 of 34 lakes.** Trend verdicts are checked only through the 2018 -> 2025 direction, which was right for 7 of 12 test lakes.
16. **Small validation set.** 8 validation lakes, only 3 of them clean, chose the method. The ±0.2 interval width rests on 16 lake-years.

## Scope

17. **Extent only.** Nothing here measures water depth, volume, quality or algae species, or the reasons a lake changed.
18. **No U-Net.** The planned learned model (spec §6.3, D4) is not built yet. It is the obvious next step for the dark-water and vegetated-water failures, and it would need new labelled lakes to test it.
19. **Dynamic World needs an Earth Engine account.** The cross-check only (`measure`) needs one: a free non-commercial project. The reported areas use Sentinel-2 alone.
