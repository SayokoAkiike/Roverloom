# Race stages on real Mars terrain

Three race stages stand on HiRISE terrain models of real places. This page says where each one is, what is
measured and what is chosen by eye, and how to build them. Race rules are in [race.md](race.md).

**Status, 2026-11-27.** The terrain files, ground-brightness maps, routed courses and scene generators were made and
checked in a cloud session. The Unreal steps for Noctis and Amazonis (materials, levels) and the MOLA far fields
**have not been run yet**, and no game screenshot of either stage exists.

## The stages

| Stage | Place | HiRISE DTM (CC0) | What the ground is like |
| --- | --- | --- | --- |
| Gale | Gale crater floor, 5.5° S, 137.3° E | `DTEEC_063319_1745_052242_1745_A01`, 1 m | See [terrain-gale](results/terrain-gale/README.md) |
| Noctis | Noctis Labyrinthus, 11.3° S, 96.4° W | `DTEEC_027526_1685_027592_1685_A01`, 1 m | The floor of a trough. A layered spur hooks into the floor; wind-blown ridges lie to the north-east; a trough wall rises some hundreds of metres to the east |
| Amazonis | Amazonis Planitia, 22.2° N, 157.2° W | `DTEED_025827_2025_025893_2025_A01`, 2 m | Smooth, dust-mantled plains with few rocks. A sinuous channel runs into a chain of large pits |

What the HiRISE team and NASA wrote about these places, which the stage looks follow:

- Noctis Labyrinthus: troughs that appear to be collapse pits and faults at the western end of Valles Marineris; light-
  and dark-toned layered beds over 300 m thick in places, some with hydrated minerals; dune fields between buttes.
  [ESP_027526_1685](https://hirise.lpl.arizona.edu/ESP_027526_1685) ("Layered Floor of Noctis Labyrinthus"),
  [PSP_005400_1685](https://hirise.lpl.arizona.edu/PSP_005400_1685), [ESP_014353_1685](https://hirise.lpl.arizona.edu/ESP_014353_1685).
- Amazonis Planitia: one of the smoothest plains on Mars, young lava flows with few craters, covered by dust; dust devils
  and their tracks; pit chains with meandering channels, which one HiRISE author interprets as volcanic.
  [ESP_025893_2025](https://hirise.lpl.arizona.edu/ESP_025893_2025) ("Pits and Channels in Amazonis Planitia", the stereo
  partner of this DTM), [ESP_026249_2025](https://hirise.lpl.arizona.edu/ESP_026249_2025),
  [ESP_036429_1925](https://hirise.lpl.arizona.edu/ESP_036429_1925).

## Measured, interpolated, and chosen

| Part | Source | Measured? |
| --- | --- | --- |
| Ground shape, 1 km around the course | HiRISE DTM, resampled to 1 m posts | Shape at the DTM's post spacing is measured. Amazonis's posts are 2 m, so its 1 m posts are interpolated |
| Ground shape, about 5 km around | The same DTM, averaged | Measured where the strip has data; 17 % (Noctis) and 16 % (Amazonis) of the square is outside the strip and filled by interpolation. See `horizon.json` |
| Distant relief, 200 km | MOLA 463 m DEM, as for Gale (`mola_far.py --site`) | Interpolated map; not yet made for these stages |
| Light and dark pattern on the ground | HiRISE RED orthoimage, with its shading divided out (`hirise_albedo.py`) | A relative brightness from one greyscale photo. The sun direction is fitted to the DTM's shading; see `albedo.json`. Not a measured albedo or colour |
| Colours, layering bands on rock, sky, haze, rocks | `build_gale_material.py` (`LOOKS`), the game's light presets | Chosen by eye, `mars_inspired` |

The shading fit was good on Amazonis (R² 0.66, ambient share 0.29) and weak on Noctis (R² 0.23), where the ground's own
light and dark beds outweigh the shading; there the ambient share was held at 0.15. Cast shadows (pit floors, the lee of
cliffs) cannot be divided out and are set to the mean brightness: 2 % of the Noctis site and 18 to 21 % of the horizon
squares, mostly the pits.

## Courses

Routed with [`scripts/terrain/route_course.py`](../scripts/terrain/route_course.py): A* on the 4 m-baseline slope, no
point whose slope within 3 m reaches 10 degrees, then straight shortcuts where every metre stays under it.

| Course | Length | Steepest on path | Notes |
| --- | --- | --- | --- |
| `noctis_spur` | 333 m, four flags | 7.5° | Round the west tip of the layered spur, climbing 8 m; supply at flag 2 |
| `noctis_sprint` | 157 m, two flags | 7.5° | The first half of Noctis Spur |
| `amazonis_rim` | 351 m, four flags | 9.1° | Across the plain past the channel to a pit rim; the finish is 45 m from an edge where the DTM drops over 50 m in 40 m |
| `amazonis_sprint` | 160 m, two flags | 9.1° | The last two flags of Amazonis Rim |

Slopes are from the DTM. The Unreal rover's climbing ability is not measured here, and nothing about traversability on
Mars is claimed. At the rover's 0.5 m/s the long courses take about eleven minutes in the race model.

## Build on a Mac

```shell
brew install gdal
```

```shell
uv run --project python python scripts/setup_gale.py --site all --ue-root "/Users/Shared/Epic Games/UE_5.8"
```

Then race, for example:

```shell
uv run --project python python scripts/play_3d.py --race --course noctis_sprint --npcs 3 --ue-root "/Users/Shared/Epic Games/UE_5.8"
```

The launcher picks the stage's level, puts the rover at the course start, and sets the number of stones per stage
(Amazonis has a quarter of Gale's).

## Concept renders with vork

[`scripts/vork/stage_concept.py`](../scripts/vork/stage_concept.py) writes vork scenes of each stage from the same
terrain and brightness files, with the V2 rover on a course. Render them on the Mac as in
[vork-concept-renders.md](vork-concept-renders.md). Every image is labeled **"Concept render (vork), not a game
screenshot"** ([ADR 0015](decisions/0015-vork-for-concept-renders.md)).

```shell
python3 scripts/vork/stage_concept.py --out unreal/Saved/StageConcept
```

```shell
vork render unreal/Saved/StageConcept/noctis_spur.json --profile std/final --out noctis_spur.png
```
