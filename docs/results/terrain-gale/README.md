# Terrain site: Gale crater, Aeolis Mons, 2026-11-16

**Status: heightfield made and checked against its source. Not imported into Unreal**, because Unreal Engine is not
installed on the Mac mini. Nothing here changes the lightweight backend, its terrains, physics, or scoring.

The owner chose Gale on 2026-11-16, from the candidates in [site-and-look-references.md](../../site-and-look-references.md).

| Where the site is in the DTM | Site hillshade, 1 m, light from the northwest | Slope over 4 m: grey under 15°, orange to red above |
| --- | --- | --- |
| ![Hillshade of the whole HiRISE DTM with a 1 km square outlined at the lower edge of the fan](locator.jpg) | ![Hillshade of the 1 km site](hillshade.jpg) | ![Slope map of the 1 km site](slope.jpg) |

Images are made from the DTM by the script, at north up. They are not photographs.

## Source

| Item | Value |
| --- | --- |
| Product | `DTEEC_063319_1745_052242_1745_A01`, "Fan material at alcove on southwestern Aeolis Mons" |
| Listing | [USGS STAC item](https://stac.astrogeology.usgs.gov/api/collections/mro_hirise_socet_dtms/items/DTEEC_063319_1745_052242_1745_A01) |
| License | CC0-1.0 per the STAC item and [USGS documentation](https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms/) |
| Credit | NASA/JPL/University of Arizona; DTM by the University of Arizona, distributed by USGS |
| File | Cloud Optimized GeoTIFF, Float32, 5670 × 10691 at 1.0126 m, 135 MB, SHA-256 `300913c8…12bcae` |
| Downloaded | 2026-11-16, with `curl` from the public `astrogeo-ard` bucket, no sign-in. Kept in `unreal/Saved/Terrain/gale/`, outside Git |

The figure of merit (`DTFEC_…`) and one orthoimage (`ESP_052242_1745_RED_C_01_ORTHO`) were also downloaded for
inspection, 159 MB together, outside Git. Neither is used by the script yet.

## How the site was chosen

1. Slope at the DTM's 4 m overview, over every 1 km square with no nodata, stepped by 8 samples.
2. Squares with at least 93% of the area under 15° were ranked by their steepest 0.5%, so that a few features
   remain; five non-overlapping ones were outlined on a hillshade.
3. Claude Code picked the one at the lower edge of the fan: ridges, a terrace scarp, and layered ground, with a
   flatter area to start from. The owner has not yet seen the hillshade.

## Result

`python3 scripts/terrain/hirise_site.py --previews docs/results/terrain-gale`, with Homebrew `python3` and GDAL
3.13.3, on the Mac mini (Apple M4, macOS 27.0.1). Full numbers are in [site.json](site.json).

| Item | Value |
| --- | --- |
| Center | 137.31635° E, 5.52057° S (equirectangular 8139385, −327230 m) |
| Heightfield | 1009 × 1009 at 1.0 m, 1008 m across, cubic resampling; `.r16` unsigned 16-bit, 2.0 MB, outside Git |
| Heights | −3359.7 to −3269.8 m relative to the aeroid: 89.9 m of relief |
| Nodata filled | 0 samples |
| Unreal scale to use | X and Y 100%; Z 17.562% if 100% spans 512 m, which must be checked at import |
| Slope over 4 m | 93.0% of the area under 15°; 95th percentile 16.2°; maximum 37.4° |
| Slope over 1 m | 72.3% under 15°; 95th percentile 26.7°. Dominated by stereo noise, as the slope map at 1 m showed |
| Check against the source | 200 random point pairs: height difference in the `.r16` against bilinear samples of the source DTM. Median error 0.016 m, maximum 0.108 m; the 16-bit step is 0.0014 m |

The check covers the crop, resampling, and 16-bit scaling. It does not cover the Unreal import, which is
[step 8 of the pipeline](../../unreal-production-plan.md#terrain-data-pipeline) and is not done.

## Limits

- The DTM's vertical accuracy is about ±1.3 m relative to MOLA, and its resolving power is coarser than 1 m. Rocks,
  ripples, and anything finer in a scene will be generated and must be labeled so.
- A real shape does not validate soil, slip, or the drive model.
- This site is not wired to any `terrain_id`. The lightweight backend's terrains are unchanged, and runs on the two
  backends remain incomparable.
- Six percent of the area is steeper than 15° over 4 m. The test lanes stay on the flat test ground.
