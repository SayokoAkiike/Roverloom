# Gale in Unreal: Landscape, materials, rocks, light presets, 2026-11-16

**What this is:** the first visual pass on a real-terrain level, made on the Mac mini (Apple M4, 16 GB, macOS 27.0.1, UE 5.8.4,
Metal). It is looks only. No physics, collision, or drive value was changed (`RoverDrive`, `CommandRouter`, `RoverPawn`, and the
WheelSpike code are untouched, and the rock scatter has no collision). The site is derived from a HiRISE DTM with generated
detail; Earth textures and rocks stand in for Martian ones, so none of this says anything about soil or rock behavior.

## What was built

| Part | How | Where |
| --- | --- | --- |
| Site Landscape, 1009 x 1009 at 1 m | `gale_site.r16` through `URoverloomLandscapeLibrary::ImportR16Landscape` (new, editor-only C++), Z scale 17.562%, as `gale_site.json` | `scripts/unreal/build_gale_level.py`, `Rover/GaleLandscape.{h,cpp}` |
| Site origin | The rover starts on the calmest patch near the center, 2 m west and 38 m south of it (largest slope over 20 m is 4.8 deg at a 4 m baseline; the center's own window reaches 11.4). That patch is the world origin, at z = 0 | `build_gale_level.py` |
| Horizon Landscape, 5.6 km square at 5.55 m | Cut from the same DTM by `scripts/terrain/hirise_horizon.py`, on the site's vertical datum (the two heights at the origin differ by 1.1 cm), no collision | `docs/results/terrain-gale/horizon.json` |
| Ground material | `M_GaleLandscape`: four layers (`dry_ground_01` regolith, `dense_sand`, `rock_boulder_cracked` bedrock, `rocks_ground_03` gravel) weighted by slope, height, and three noises; each layer at a fine (2.2 m) and a coarse (52 m) tile, the coarse one fading in with distance, plus a large-scale brightness noise; pulled toward a tan | `scripts/unreal/build_gale_material.py` |
| Rocks | 691 instances of four Poly Haven rocks, seed 20261116, none within 4.5 m of the straight lane (3 m behind to 42 m ahead) or 8 m of the start, no collision, no Lumen or shadow cost for pebbles, culled by size | `SpawnScatter` in `RoverPlaygroundGameMode.cpp` |
| Light presets | `-RoverLight=noon\|afternoon\|sunset`: sun height 58, 22, 2.5 deg; fixed exposure 10.5, 11.3, 11.4; a warmer, dustier sunset | `SpawnLights` |
| Render profiles | `-RoverProfile=dev` (software Lumen) and `-RoverProfile=capture` (more Lumen rays, virtual shadow maps) | `ApplyProfile` |
| Haze | A blue-grey height fog that starts at 400 m, so the horizon ridges recede. **The owner asked for a bluish haze. It is a chosen look: Mars's own day haze is butterscotch, and its blue is a glow near the sun at sunset.** | `SpawnLights` |
| Sky | Unreal's Sky Atmosphere, tuned by eye. **No Poly Haven HDRI is used**: the site has no Mars-like one, and a day HDRI would give an Earth-blue sky | `SpawnLights` |

The Landscape gets the rover's existing physical material (friction and restitution as the greybox blocks have), and the start
height comes from a trace to the ground, so the rover drives on the same friction numbers as before. At the origin the traced
ground is z = -0.0 cm, as built. Only the origin was checked against the heightfield, not other points.

`-RoverLight` and `-RoverExposure=EV` (a tuning override) are command-line options. Without `-RoverLight`, the original look is
unchanged. `DefaultEngine.ini` now sets `r.GenerateMeshDistanceFields=True`, which software Lumen needs.

## Images

Same cameras, same 1280 x 720 window, rover at rest. Before is the V2 rover on the greybox ground.

| | Before (greybox ground) | After (Gale Landscape) |
| --- | --- | --- |
| Chase | [before_chase.jpg](before_chase.jpg) | [landscape_chase.jpg](landscape_chase.jpg) |
| Mast | [before_mast-20-m.jpg](before_mast-20-m.jpg) | [landscape_mast-20-m.jpg](landscape_mast-20-m.jpg) |
| Front hazard | [before_front-hazard.jpg](before_front-hazard.jpg) | [landscape_front-hazard.jpg](landscape_front-hazard.jpg) |

| Step | Without | With |
| --- | --- | --- |
| Rocks, chase | [rocks_off_chase.jpg](rocks_off_chase.jpg) | [rocks_on_chase.jpg](rocks_on_chase.jpg) |
| Rocks, mast | [rocks_off_mast.jpg](rocks_off_mast.jpg) | [rocks_on_mast.jpg](rocks_on_mast.jpg) |

Light presets, chase camera, `-RoverProfile=dev`: [noon](light_noon_chase.jpg), [afternoon](light_afternoon_chase.jpg),
[sunset](light_sunset_chase.jpg). Capture profile at 1600 x 900: [chase](capture_afternoon_chase_1600x900.jpg),
[mast](capture_afternoon_mast_1600x900.jpg). The landscape and rock shots in the first two tables were taken before the light
presets, so they use the original sun and exposure. Which one is nicer is a judgment, and nobody but the model has looked at them.

## Frame time

Windowed 1280 x 720, two 10 s windows after the first, one run per row, other apps open. The display holds 60 fps, so a row at
60 fps says only that the frame fits in 16.7 ms. **Two identical rows (no rocks, afternoon) read 42.7 and 37.5 fps in separate runs**,
so differences under about 5 fps are within the noise of this setup.

| Configuration | fps | GPU ms |
| --- | --- | --- |
| Greybox ground, V2 rover, Lumen off (the drive-comparison runs) | 60.0 | 14.1 to 14.2 |
| Gale site Landscape, Lumen off | 58.2 to 60.0 | 14.4 to 14.5 |
| Gale, `dev` (software Lumen), no rocks | 42.1 to 42.7 | 21.1 to 21.5 |
| Gale, `dev`, 1,140 rocks, all casting shadows | 25.4 | 35.5 |
| Gale, `dev`, 691 rocks (the shipped setting) | 34.3 | 27.6 |
| Gale, `capture`, 1280 x 720 | 15.6 | 60.9 |
| Gale, `capture`, 1600 x 900 | 10.9 | 88.9 |

`dev` stays above the 30 fps floor, with rocks. `capture` runs far below real time, and the HUD says "Frame slower than the physics
limit": **do not drive or record `capture` as a real-time run.** Use it for stills.

## Not done, and why

- **Niagara (wheel dust, drifting dust, dust devils): not done.** Editor Python in UE 5.8.4 loads the template systems
  (`FountainLightweight`, `DirectionalBurstLightweight`, `MinimalLightweight`) but exposes no way to read or set their emitters
  or parameters (`scripts/unreal/probe_niagara.py`), so they cannot be styled as dust from code. Authoring a system needs the
  Niagara editor, by hand.
- **Decals (tracks, drifts, rock shadows, rover dust): not done.** Nothing was made or measured.
- **Movie Render Queue / Graph: not run.** The plugin's Mac binaries are present in UE 5.8.4, but no sequence was built and no render
  attempted, so there is no error to report. Stills came from screenshots, which this machine caps at 1600 x 900 for a window.
  No video was made.
- **Terrain checks against the DTM beyond the origin:** not done. The earlier import check was on the heightfield file, not the
  Landscape in Unreal.
- **Distance haze and sky are looks, not models.** All light values were set by eye.
- **No person has judged any image.** Photorealism is not claimed.
- The horizon Landscape is 18.2% interpolated (the DTM reaches 2.8 km east and west of the site, so the 10 km asked for does not exist
  in this product); 81.8% of its samples are measured at 5.55 m, averaged from 1 m posts.

## Reproduce

Needs the HiRISE download (`hirise_site.py --download`, then `hirise_site.py` and `hirise_horizon.py`) and the Poly Haven files
(`scripts/assets/polyhaven_fetch.py`), all outside Git. Then, from the repository root, with the editor closed:

```shell
Build.sh RoverloomEditor Mac Development -project="$PWD/unreal/Roverloom.uproject"
for s in import_polyhaven build_gale_material build_rock_materials build_gale_level; do
  UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="$PWD/scripts/unreal/$s.py" -unattended -nullrhi
done
UnrealEditor unreal/Roverloom.uproject "/Game/Licensed/Gale/Gale?game=/Script/Roverloom.RoverPlaygroundGameMode" \
  -game -windowed -ResX=1280 -ResY=720 -RoverLight=afternoon -RoverProfile=dev -RoverShotDir=<dir>
```

Build with the editor closed: while an editor runs, the build writes numbered hot-reload libraries that a separate game process does
not load, and the game then runs old code. The shaders for `M_GaleLandscape` compile on the first run, which takes minutes; until
they finish the ground shows Unreal's grey checker.
