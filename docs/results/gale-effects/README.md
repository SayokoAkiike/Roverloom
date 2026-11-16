# Gale effects pass: near ground, ruts, dust, Capture grade, Movie Render Queue, 2026-11-16

Looks only, on the Mac mini (Apple M4, 16 GB, UE 5.8.4, Metal): no physics, collision, or drive value changed, and nothing
added here has collision. The stones and textures are Earth's and the colours are chosen by eye, not measured. Earlier passes:
[gale-landscape](../gale-landscape/README.md), [gale-detail](../gale-detail/README.md).

## What was done, and what was not

| Request | Result |
| --- | --- |
| Near ground that does not look flat; fine gravel and grains around the wheels | **Done, with a limit.** Stone instances may not lie on the driving lane, and the wheels are on the lane, so the grain around the wheels is in the ground material: the real pebble texture again at 26 cm a tile, a 4.5 cm sand-grain normal, over the first 10 m. See below |
| Ruts left in the sand by every wheel, as decals | **Done.** A decal for every 14 cm each wheel rolls, along the wheel's path, in a ring of 1,800, so the oldest are overwritten |
| Dust from the wheels, thin wind-blown dust, a distant dust devil, with Mars's gravity | **Done, but not in Niagara.** See below |
| Distance haze, blue-tinted, blurring the horizon | Already in the noon preset (a blue-grey height fog from 400 m); unchanged |
| Sunset sky with the blue glow around the sun and a red-brown horizon | **Half.** The horizon is red-brown. **The blue glow around the sun is still not achieved** |
| Grade like a rover's photographs, Capture only | **Done.** Saturation 0.86, contrast 1.12, film grain 0.22, vignette 0.35, spawned only with `-RoverProfile=capture` |
| Movie Render Queue: three stills and a 30 s video | **Done through MRQ**, 1920 x 1080. The video is made but its framing is poor (see below) |

## Niagara could not be used, and why

Editor Python in UE 5.8.4 cannot edit Niagara emitters, so the other route was to copy a template system and change its parameters. A C++
probe (`-RoverNiagaraProbe`, 2026-11-16) loaded all six template systems and listed their exposed parameters:
`FountainLightweight`, `DirectionalBurstLightweight`, `MinimalLightweight`, `SimpleExplosion`, `RadialBurst`, `DirectionalBurst`.
**Every one has 0 exposed parameters**, so size, colour, lifetime, gravity, and rate cannot be set from code. Writing an emitter from C++ needs the
editor-only Niagara editing classes, which is a much larger job.

**The substitute is `ARoverEffects`** (`Rover/RoverEffects.{h,cpp}`): the particles are simulated on the CPU and drawn as instances of a soft translucent
sphere (`M_DustParticle`). Wheel puffs: sizes 5 to 14 cm growing to 24 to 64 cm, lifetimes 1.5 to 4.8 s, opacity varying, thrown up and back with
a little drag, pulled down at **3.71 m/s^2** (about 38% of Earth's), and drifting with a 0.5 m/s wind. A thin haze of 120 large faint puffs drifts
around the rover. A dust devil of 260 puffs rises in a turning, widening column, 185 m away. A Niagara system made by hand in the editor could replace it.
With the effects on, 491 wheel puffs were alive at the busiest moment, and 131 rut decals after the `f1-flat` drive.

Images, same drive (`f1-flat`), Dev profile, afternoon preset, chase camera:

| | Effects off | Effects on |
| --- | --- | --- |
| Dust, 8 s in (rover at full speed) | [dust_off_chase.jpg](dust_off_chase.jpg) | [dust_on_chase.jpg](dust_on_chase.jpg) |
| Ruts, 44 s in (drive over) | [ruts_off_chase.jpg](ruts_off_chase.jpg) | [ruts_on_chase.jpg](ruts_on_chase.jpg) |

The dust shows behind the rear wheels and as a column at the upper right (the dust devil); the ruts are dark tread tracks that curve with the rover's turn.

## The near ground

Same cameras, afternoon preset, Dev profile, effects off, rover at rest:

| Camera | Before | After |
| --- | --- | --- |
| Chase | [grain_before_chase.jpg](grain_before_chase.jpg) | [grain_after_chase.jpg](grain_after_chase.jpg) |
| Mast | [grain_before_mast-20-m.jpg](grain_before_mast-20-m.jpg) | [grain_after_mast-20-m.jpg](grain_after_mast-20-m.jpg) |
| Front hazard (the rover's eye height) | [grain_before_front-hazard.jpg](grain_before_front-hazard.jpg) | [grain_after_front-hazard.jpg](grain_after_front-hazard.jpg) |

[A crop of the near ground](grain_closeup_before_after.jpg), before on the left and after on the right, shows the grain and the small pebbles. **At the chase
and mast distance the difference is small**; it is clearest on the hazard camera, a few metres from the wheels. The first try used cell noise and drew
a regular polka-dot pattern; it was replaced by the photographic pebble texture. Grains and pebbles are not geometry: a wheel does not climb them.

## Frame time

Windowed 1280 x 720, Dev, afternoon preset, `f1-flat` driving (two 10 s windows after the first), one run each, other apps open. The display holds 60 fps.

| Configuration | fps | GPU ms |
| --- | --- | --- |
| Dust and ruts off, driving | 34.7 | 25.9 |
| **Dust and ruts on, driving** | **33.2** | 27.1 |
| Rover at rest, before the grain and pebbles | 34.5 | 26.8 |
| Rover at rest, after | 34.4 | 26.3 |

Dev holds 30 fps or more. At 1280 x 720 the Dev profile uses TAA (see [gale-detail](../gale-detail/README.md)).

## Sunset

The sunset preset now has a red-brown haze toward the horizon and a violet-brown sky ([sunset_mast_red_brown.jpg](sunset_mast_red_brown.jpg)). **The blue glow
around the sun is not there.** I tried a blue directional glow in the height fog, then at 12 times its strength: nothing changed, because the fog does
not act on sky pixels. The sky atmosphere's own forward-scattering halo, with a blue Mie colour and an anisotropy of 0.93, did not show either, with the sun in
view (the rover turned toward it). The glow code is left in `SpawnLights` with a black colour, which turns it off.

## Capture grade and Movie Render Queue

The grade is a post-process volume spawned only for `-RoverProfile=capture`, so Dev shows the scene as it is. The values are not calibrated to any camera.

**Movie Render Queue works on this Mac** (UE 5.8.4, `MovieRenderPipeline` plugin, run from the command line, in-process executor). Three things went wrong
on the way, and are fixed in `scripts/unreal/build_mrq.py`: MRQ loads the map with its own game mode, which leaves out the rover, lights, and rocks (the
config's Game Override setting names ours); the pass `MoviePipelineDeferredPass_DetailLighting` is a lighting-only view, grey, without textures (the plain
`MoviePipelineDeferredPassBase` is right); and an empty `{sequence_name}` made hidden file names that start with a dot. A CineCamera's physical f/2.8 blurred
the rover, so the sequences use a plain camera. A still takes 17 s including 48 warm-up frames, 1920 x 1080.

| Preset | Still, 1920 x 1080, Capture | Mean R, G, B | Luma |
| --- | --- | --- | --- |
| Noon | [capture_still_noon.jpg](capture_still_noon.jpg) | 156.7, 110.6, 83.4 | 118.4 |
| Afternoon | [capture_still_afternoon.jpg](capture_still_afternoon.jpg) | 149.5, 97.9, 67.1 | 106.6 |
| Sunset | [capture_still_sunset.jpg](capture_still_sunset.jpg) | 111.3, 46.0, 29.3 | 58.7 |

Run them with `scripts/unreal/render_mrq.sh still noon|afternoon|sunset` (and `video`), after `build_mrq.py`.

**The video** (`render_mrq.sh video noon`): 900 frames at 1920 x 1080, 30 fps, Capture profile, noon preset, the rover driving the `f1-flat` script. MRQ
rendered them in 3 min 11 s, and ffmpeg joined them into `unreal/Saved/MovieRenders/Video/gale_noon_30s.mp4` (36 MB, 30.0 s, H.264). **It is outside Git:** `Saved/` is ignored,
and nothing in this repository holds it. Frames 0, 300, 600, and 899 are in [video_frames_0_300_600_899.jpg](video_frames_0_300_600_899.jpg): the rover drives away
(+X), wheel dust shows at frame 300, the ruts lie behind it, and the dust devil rises at the right of the last frame. **Its camera is a plain drift, not a follow:** the
rover leaves the frame's left edge in the second half, so the framing is poor there. A better shot needs a camera that follows the rover. The game's own time stepping
under MRQ was not checked: the drive script ran, but whether the rover moved by the same distances as in real time was not measured.

## Proposal for the README top image (not applied)

Replace the concept render at the top of `README.md` with a game image, for example `capture_still_afternoon.jpg` copied to `docs/images/game/hero.jpg`, with this caption:

```text
*A game render, not a concept render: the V2 rover model on a heightfield cut from a HiRISE terrain model of Gale crater, in Unreal Engine 5.8, Capture
profile, rendered with Movie Render Queue. The textures and rocks are Earth's, the colours are chosen by eye, and the sky and light are artistic presets. It says nothing about
real Martian ground. How it was made: docs/results/gale-effects/README.md (as a link in the README).*
```

The status paragraph would also change: it says the Unreal client is a greybox, and that Python agents do not yet drive the Unreal rover. One run of `unreal_link --agent`
did reach the target ([results](../unreal-link-g3/README.md)), and the level is no longer a greybox. I have not edited the README.

## Not done

Niagara (reason above), the blue glow at sunset, a camera that follows the rover in the video, and any human judgment of the images.
