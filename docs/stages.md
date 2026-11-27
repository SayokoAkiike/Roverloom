# Race stages on real Mars terrain

Five race stages stand on HiRISE terrain models of real places. This page says where each one is, what is
measured and what is chosen by eye, and how to build them. Race rules are in [race.md](race.md).

**Status, 2026-11-28.** Gale, Noctis and Amazonis are built and raced on the owner's Mac. Lyot (winter dunes) and the
north polar dunes (the "ghost forest") were added in a cloud session: their terrain files, brightness maps, courses,
material looks, light presets and vork concept scenes were made and checked there. Their Unreal steps (materials,
levels, MOLA far fields) **have not been run yet**, and no game screenshot of them exists.

## The stages

| Stage | Place | HiRISE DTM (CC0) | What the ground is like |
| --- | --- | --- | --- |
| Gale | Gale crater floor, 5.5° S, 137.3° E | `DTEEC_063319_1745_052242_1745_A01`, 1 m | See [terrain-gale](results/terrain-gale/README.md) |
| Noctis | Noctis Labyrinthus, 11.3° S, 96.4° W | `DTEEC_027526_1685_027592_1685_A01`, 1 m | The floor of a trough. A layered spur hooks into the floor; wind-blown ridges lie to the north-east; a trough wall rises some hundreds of metres to the east |
| Amazonis | Amazonis Planitia, 22.2° N, 157.2° W | `DTEED_025827_2025_025893_2025_A01`, 2 m | Smooth, dust-mantled plains with few rocks. A sinuous channel runs into a chain of large pits |
| Lyot (winter dunes) | Lyot Crater dune field, 49.18° N, 29.04° E | `DTEEC_053406_2295_053894_2295_A01`, 1.1 m | Dark crescent dunes (barchans) 5 to 15 m high, scattered over a bright crater floor, their slip faces to the east. Raced in northern winter |
| Olympia (ghost forest) | North polar dune field, Olympia Undae, 80.34° N, 96.37° E | `DTEPC_062937_2605_062555_2605_A01`, 1 m | Long, thin dark dunes with tails, lying south-west to north-east over bright, ice-cemented ground with a band of rough, broken ground. Raced in northern spring |

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
- Lyot Crater in winter: "Frosted Dunes in the Depths of Winter", taken two days after the northern winter solstice with
  the sun about 7° above the horizon, at 49.186° N, 29.006° E: the same dunes as this DTM. The caption says that frost, a
  mixture of carbon dioxide and water ice, covers the colder, north-facing half of each dune but not the warmer
  south-facing half. In the image the dunes are frosted all over but for their steep slip faces, and the floor between
  them is bare apart from thin streaks. [ESP_074942_2295](https://hirise.lpl.arizona.edu/ESP_074942_2295),
  [ESP_053406_2295](https://hirise.lpl.arizona.edu/ESP_053406_2295) ("Dune Field in Lyot Crater").
- The north polar dunes in spring: dark streaks on frosted dunes that look like trees standing on snow, from a 2008
  HiRISE image near the north pole. The HiRISE team's explanation: dark basaltic sand, exposed as the spring sun turns the
  carbon dioxide frost to gas, slides down the frosted slopes; the streaks cast no shadow, which shows they are not
  trees. [Space.com](https://www.space.com/7775-strange-mars-photo-includes-tantalizing-tree-illusion.html),
  [ESP_062937_2605](https://hirise.lpl.arizona.edu/ESP_062937_2605) ("North Polar Dune Forms and Frost", this DTM).

## Measured, interpolated, and chosen

| Part | Source | Measured? |
| --- | --- | --- |
| Ground shape, 1 km around the course | HiRISE DTM, resampled to 1 m posts | Shape at the DTM's post spacing is measured. Amazonis's posts are 2 m, so its 1 m posts are interpolated |
| Ground shape, about 5 km around | The same DTM, averaged | Measured where the strip has data; 17 % (Noctis) and 16 % (Amazonis) of the square is outside the strip and filled by interpolation. See `horizon.json` |
| Distant relief, 200 km | MOLA 463 m DEM, as for Gale (`mola_far.py --site`) | Interpolated map; not yet made for these stages |
| Light and dark pattern on the ground | HiRISE RED orthoimage, with its shading divided out (`hirise_albedo.py`) | A relative brightness from one greyscale photo. The sun direction is fitted to the DTM's shading; see `albedo.json`. Not a measured albedo or colour |
| Colours, layering bands on rock, sky, haze, rocks | `build_gale_material.py` (`LOOKS`), the game's light presets | Chosen by eye, `mars_inspired` |
| Where frost lies (Lyot, Olympia) | Rules in `LOOKS`: frost on pole-facing slopes and on dune sand except steep slip faces (Lyot); frost over the ground except where dark sand has cleared, but kept on slip faces (Olympia) | The rules follow the HiRISE captions above; where the dune sand is comes from the measured brightness map. The amounts and colours are chosen by eye. No frost is measured |
| Dark streaks (Olympia), floor streaks (Lyot) | Noise stretched along one direction in `LOOKS`. The Olympia direction (downslope 135°, north-west) is the commonest facing of the site's steep slopes, measured on its heightfield | Their places and sizes are generated, not measured |
| Low winter and polar sun | Light presets `winter` (7° up, from the south-west, as in ESP_074942_2295) and `polar` (13° up) | The sun's height for Lyot follows the image; colours are chosen by eye |

The shading fit was good on Amazonis (R² 0.66, ambient share 0.29) and weak on Noctis (R² 0.23), where the ground's own
light and dark beds outweigh the shading; there the ambient share was held at 0.15. Cast shadows (pit floors, the lee of
cliffs) cannot be divided out and are set to the mean brightness: 2 % of the Noctis site and 18 to 21 % of the horizon
squares, mostly the pits.

Lyot and Olympia are far from the equator. Their DTMs are equirectangular (true to scale only on the equator; at 49° N a
square cut there would stretch 1.5 times east to west) and polar stereographic. Both are therefore cut in a local
stereographic frame centred on the site (`scripts/terrain/local_frame.py`), where a metre is a metre in every direction.
On both, the dark ground is the dunes themselves, so nothing is set to the mean as a shadow (`albedo_shadow_cut` 0); the
shading fit is weak (R² 0.39 and 0.12). 19 % of the Olympia horizon square is outside the strip and filled.

## Courses

Routed with [`scripts/terrain/route_course.py`](../scripts/terrain/route_course.py): A* on the 4 m-baseline slope, no
point whose slope within 3 m reaches 10 degrees, then straight shortcuts where every metre stays under it.

| Course | Length | Steepest on path | Notes |
| --- | --- | --- | --- |
| `noctis_spur` | 333 m, four flags | 7.5° | Round the west tip of the layered spur, climbing 8 m; supply at flag 2 |
| `noctis_sprint` | 157 m, two flags | 7.5° | The first half of Noctis Spur |
| `amazonis_rim` | 351 m, four flags | 9.1° | Across the plain past the channel to a pit rim; the finish is 45 m from an edge where the DTM drops over 50 m in 40 m |
| `amazonis_sprint` | 160 m, two flags | 9.1° | The last two flags of Amazonis Rim |
| `lyot_slalom` | 410 m, three flags | 5.4° | Lyot Frost Slalom: between frosted barchans across the crater floor; supply at flag 1 |
| `lyot_sprint` | 156 m, two flags | 4.0° | The first leg of Lyot Frost Slalom |
| `ghost_forest` | 431 m, three flags | 8.9° | Ghost Forest: over the tail of a linear dune, across the rough band, out onto open frosted ground |
| `ghost_sprint` | 223 m, two flags | 8.9° | The first two flags of Ghost Forest |

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
(Amazonis has a quarter of Gale's, the polar dunes a tenth), and the stage's own light: `winter` for Lyot, `polar` for the
polar dunes, unless `--light` is given.

## Concept renders with vork

[`scripts/vork/stage_concept.py`](../scripts/vork/stage_concept.py) writes vork scenes of each stage from the same
terrain and brightness files, with the V2 rover on a course. Render them on the Mac as in
[vork-concept-renders.md](vork-concept-renders.md). Every image is labeled **"Concept render (vork), not a game
screenshot"** ([ADR 0015](decisions/0015-vork-for-concept-renders.md)).

The Lyot and Olympia scenes colour the ground with the same frost and streak rules as the Unreal material, so the
concept renders and the game follow one set of rules. Draft renders of the four new shots were made in a cloud session
on the CPU (`--no-fog --resolution 800 450`, `std/previs`) to check framing and the rules; they are rough and are not
kept in the repository.

```shell
python3 scripts/vork/stage_concept.py --out unreal/Saved/StageConcept
```

```shell
vork render unreal/Saved/StageConcept/noctis_spur.json --profile std/final --out noctis_spur.png
```
