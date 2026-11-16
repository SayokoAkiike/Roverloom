# Gale detail pass: grain size, ground material, light presets, colour, 2026-11-16

**What this is:** the second visual pass on the Gale level, on the Mac mini (Apple M4, 16 GB, UE 5.8.4, Metal). It answers the
owner's complaints that the ground and light lacked detail, and that rocks and grains were too even to look like Mars. Looks only: no
physics, collision, or drive value changed, and every stone has no collision. The textures and rocks are Earth's; **colour does the
work of making them read as Mars, and none of the colours is a measured Martian one.** First pass: [gale-landscape](../gale-landscape/README.md).

## What changed

| Part | Before | Now |
| --- | --- | --- |
| Stones and rocks | 691 instances, four size classes | **32,434 instances**, bounded power-law radius from **3 cm to 1.5 m** (number larger than r falls as r^-1.9): 7,685 to 6 cm, 13,811 to 15 cm, 9,353 to 40 cm, 1,326 to 90 cm, 259 larger. Random yaw, tilt of up to 15 deg, squash and stretch, **half buried**, fixed seed. No collision. Off a 5 m wide straight lane and 3 m around the start (the old gap was 9 m and 8 m, which left the near ground bare) |
| Ground material | four layers, two tile scales | the same four layers, plus a 37 cm micro-relief normal, two large-scale colour noises, **sand ripples**, and **wind-drifted sand** (light ochre, ripples) against **gravelly ground** (dark brown) with stones in the drift edges |
| Colour | one tan tint | each layer desaturated and given its own red-brown or ochre tint, patches that swing between reddish and ochre over hundreds of metres, then contrast |
| Light presets | one sun height and exposure each | noon, afternoon, sunset each set sun height and direction, light colour, dust scattering, sky light, haze colour, and exposure |
| Dev profile | TSR | TAA (about 2.5 ms cheaper on this Mac); `capture` keeps TSR |

## Light presets in numbers

Mast, chase, and front-hazard cameras, 1280 x 720, `-RoverProfile=dev`, rover at rest at the origin. Mean sRGB values 0 to 255 outside the HUD
box, luma = 0.2126 R + 0.7152 G + 0.0722 B on those values ([`preset_stats.txt`](preset_stats.txt) has every region). Sky is the top strip of the frame.

| Camera | Preset | Sun above horizon | Whole image R, G, B | Luma | Sky luma | Sky B/R |
| --- | --- | --- | --- | --- | --- | --- |
| Chase | noon | 58 deg | 131.6, 90.1, 70.4 | 97.5 | 175.9 | 0.74 |
| Chase | afternoon | 22 deg | 124.7, 76.2, 51.5 | 84.7 | 151.2 | 0.61 |
| Chase | sunset | 5.5 deg | 90.1, 36.3, 27.1 | 47.1 | 140.6 | 0.86 |
| Mast | noon | | 138.8, 96.5, 73.9 | 103.9 | 170.2 | 0.69 |
| Mast | afternoon | | 126.3, 76.8, 50.5 | 85.4 | 142.6 | 0.54 |
| Mast | sunset | | 104.9, 46.6, 35.4 | 58.2 | 126.3 | 0.77 |
| Front hazard | noon | | 143.6, 85.9, 60.5 | 96.3 | 160.8 | 0.62 |
| Front hazard | afternoon | | 124.7, 65.1, 39.2 | 75.9 | 126.7 | 0.44 |
| Front hazard | sunset | | 100.6, 31.4, 22.9 | 45.5 | 105.7 | 0.58 |

The presets differ clearly: sunset is about half as bright as noon, with its sky turning from butterscotch (B/R 0.6 to 0.7) to a violet that is
bluer relative to red (0.77 to 0.86), and afternoon has the warmest ground (B/R 0.31 to 0.41). **The first try did not**: noon came out darker than
afternoon because the exposures were set apart; they now share one exposure, and sunset's is higher. Side by side:
[chase](presets_chase.jpg), [mast](presets_mast-20-m.jpg), [front hazard](presets_front-hazard.jpg) (noon, afternoon, sunset, left to right).

**The blue glow around the sun at sunset was not achieved.** The sunset preset puts the sun ahead and a little to the right, 5.5 deg up, with a
red sun light, a blue forward-scattering dust (Mie colour blue, anisotropy 0.93), and a blue-violet haze. The sky near the horizon does turn pale
violet-blue, but around the expected sun position the brightness and the blue-to-red ratio are flat (rings 0 to 400 px: luma 141 to 154, B/R 0.87 to
0.90), and no sun disc is visible. The sun may sit behind the fog or the ridge, and a lower fog opacity did not make it appear. This is
a violet sunset sky, not the blue halo of the Martian photographs.

## Before and after, and the near views

The before images are the ones committed in the first pass, so **the light differs**: its afternoon preset had another sun colour and exposure,
and its hazard-camera shot used the original sun. The terrain, rocks, and material are what changed most.

| Camera | Before | After (afternoon preset) |
| --- | --- | --- |
| Chase | [before_chase.jpg](before_chase.jpg) | [after_chase.jpg](after_chase.jpg) |
| Mast | [before_mast-20-m.jpg](before_mast-20-m.jpg) | [after_mast-20-m.jpg](after_mast-20-m.jpg) |
| Front hazard, at the rover's eye height | [before_front-hazard.jpg](before_front-hazard.jpg) | [after_front-hazard.jpg](after_front-hazard.jpg) |

Near views at other ground, from the front hazard camera at the rover's height, with `-RoverStartM=east,north` (site frame, metres; the start
is only for viewing): [188,-68](near_site1.jpg) shows wavy parallel sand ripples in the upper right, [408,-8](near_site2.jpg), [-292,268](near_site3.jpg),
[176,-68](near_site4.jpg). Ripples show on the drifts and fade past about 25 m. At the origin, the ground in front of the rover is cracked
regolith, and sand drifts begin farther out.

**On repeating patterns:** I looked at all of these and at six more positions, and at the debug view of the layer weights (sand, gravel,
bedrock), and I saw no tiling and no grid. The first ripple version drew concentric rings far from the origin; it was a wavelength that varied with
position, and is fixed. This is my own look, not a measurement, and nobody else has judged it.

## Frame time

Windowed 1280 x 720, two 10 s windows after the first, one run each, other apps open. The display holds 60 fps.

| Configuration | fps | GPU ms |
| --- | --- | --- |
| First pass, Dev (691 rocks, TSR) | 34.3 | 27.6 |
| **Now, Dev, at the origin, three presets** | **34.4 to 34.6** | 26.0 to 26.4 |
| Now, Dev, four other sites | 38.4 to 39.8 | 22.5 to 23.8 |
| Now, `capture` at 1280 x 720 | 15.4 | 62.5 |
| Dev with the ground material only (no stones, TSR) | 41.0 | 21.8 |

Dev holds 30 fps or more. `capture` is for stills; it falls below real time, and the HUD warns that its frame time exceeds the physics limit.

**What the stones cost, measured on the way:** 40,010 stones without Nanite ran at 4.7 fps (GPU 207 ms); with Nanite on the rocks 16.6 fps (54.7 ms);
shortening the draw distance of small stones brought it to 27 to 29 fps (31 to 32 ms); switching Dev from TSR to TAA gave the last 2.5 ms. Shadows were
not the cost (turning them off changed nothing). The draw distances are 4.5 m for stones under 6 cm, 9 m under 15 cm, 22 m under 40 cm, 70 m under 90 cm,
and 200 m for the largest, so far stones are fewer on screen than in the world.

**A bug found on the way:** the rock materials lacked the "used with Nanite" and "used with instanced static meshes" flags, so Unreal drew the rocks in its
default grey material. `build_rock_materials.py` now sets both. The first photographs of Nanite rocks in this pass were grey for that reason.

## Options and scripts

`-RoverRocks=0`, `-RoverRockScale=N` (percent of the count), `-RoverRockCull=N` (percent of the draw distances), `-RoverRockShadows=0`,
`-RoverStartM=east,north`, `-RoverFogMax=F`, as well as the earlier `-RoverLight`, `-RoverExposure`, `-RoverProfile`. New:
`scripts/unreal/enable_nanite_rocks.py` (Nanite on the rocks; `--off` reverses it), `scripts/unreal/probe_rock_material.py`. `build_gale_material.py`
takes `--debug-weights` to colour the ground by layer (sand red, gravel green, bedrock blue). Rebuild the material and the rock materials, then run the
game twice: the first run compiles shaders and builds Nanite data, and is slow.

## Not done

Niagara dust, decals, Movie Render Queue, and a human judgment of any image, as in the first pass. Nothing here validates the physics or any
property of Martian ground.
