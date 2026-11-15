# Concept renders with vork, 2026-11-15

**Concept render (vork), not a game screenshot.** None of these images comes from the Unreal client, the simulator,
or any physics. They show the V2 rover model in an invented, Mars-inspired scene. See
[ADR 0015](../../decisions/0015-vork-for-concept-renders.md) and the [guide](../../vork-concept-renders.md).

| Hero, late afternoon | Side, midday | Sunset |
| --- | --- | --- |
| ![Concept render (vork), not a game screenshot: the V2 rover from the front left, late afternoon](../../images/concept/hero.jpg) | ![Concept render (vork), not a game screenshot: the V2 rover from the side, midday, mesas behind](../../images/concept/side.jpg) | ![Concept render (vork), not a game screenshot: the V2 rover nearly in silhouette, toward a low Sun](../../images/concept/sunset.jpg) |

## How they were made

| Item | Value |
| --- | --- |
| Machine | Mac mini, Apple M4 (Mac16,10), 16 GB, macOS 27.0.1 |
| Rover | `scripts/blender/build_rover.py` with Blender 5.3.0 (Homebrew cask); all its checks passed |
| Scenes | `scripts/vork/rover_concept.py`, seed 7, as changed in this step |
| Renderer | vork 0.5.1 (commit `626653ebf900`, API v2), Metal |
| Profile | `std/final`: approximate global illumination, 8 samples per pixel, denoised |
| Resolution | 1600 × 900; PNG from vork, then JPEG with ffmpeg 9.0.2 at `-q:v 2` (83–111 KB each) |
| Render time | 2.7–7.6 s per image, after shader warm-up |
| Base commit | `4682c90` plus this step's change to the scene script |

```shell
blender -b -P scripts/blender/build_rover.py -- --out unreal/Saved/RoverModel
python3 scripts/vork/rover_concept.py --out unreal/Saved/RoverConcept
vork check unreal/Saved/RoverConcept/hero.json
vork render unreal/Saved/RoverConcept/hero.json --profile std/final --out unreal/Saved/RoverConcept/hero.png
ffmpeg -i unreal/Saved/RoverConcept/hero.png -q:v 2 docs/images/concept/hero.jpg
```

## What changed in the scene script, and why

The first drafts, made with the script as committed in PR #7, were judged by Claude Code on this Mac:

| Draft problem | Change |
| --- | --- |
| Hero and side washed out: vork's physical sky is Earth's, so the sky was pale blue-white and too bright | A sky program written for this project: a butterscotch dome, paler at the horizon, with a glow and a bluish aureole around the Sun. Per-shot exposure in AgX stops |
| Haze veiled everything, and hid the Sun at sunset | Thinner dust with a 50 m scale height, so that long paths upward escape it; strength per shot |
| Rocks were smooth squashed spheres | Noisy icospheres cut by 7–11 random planes, with dust settled on their upper faces; 420 rocks with a power-law size, denser near the rover, none within 3 m of the camera |
| Mesas were rounded boxes, often out of frame | Flat-topped hills with a ragged rim, cliff, and talus, spread evenly around the horizon |
| Flat, uniform ground | A heightfield 320 m across with swells and bumps, flat within 3 m of the rover; its color varies at two scales, through vertex colors (vork does not yet allow a custom surface program together with fog) |
| Sun behind a mesa at sunset | Sun moved 7° left, into a gap |

All colors, haze, and sky are chosen by eye. They are `mars_inspired`, not measured, and were not compared with
reference photographs side by side.

## Gale site

Added 2026-11-16. **Concept render (vork), not a game screenshot.**

![Concept render (vork), not a game screenshot: the V2 rover on terrain shaped by a HiRISE DTM of Gale crater](../../images/concept/gale.jpg)

| Item | Value |
| --- | --- |
| Terrain | The [Gale heightfield](../terrain-gale/README.md), from HiRISE DTM `DTEEC_063319_1745_052242_1745_A01`: measured shape at 1 m out to 480 m from the rover, with generated bumps below 1 m and leveled within 3 m of the wheels |
| Rover spot | One of two places in the site flat to under 4° over 20 m: 144 m west and 24 m north of the site center, facing a ridge about 24 m higher and 250 m away |
| Rocks, sky, dust, color | Generated, as in the other shots; no mesas |
| Render | `std/final`, 1600 × 900, 2.7 s on the Mac mini; JPEG 93 KB |
| Credit | NASA/JPL/University of Arizona; DTM distributed by USGS; CC0 |

```shell
python3 scripts/terrain/hirise_site.py --download
python3 scripts/vork/rover_concept.py --out unreal/Saved/RoverConcept --site unreal/Saved/Terrain/gale/gale_site.r16
vork render unreal/Saved/RoverConcept/gale.json --profile std/final --out unreal/Saved/RoverConcept/gale.png
```

Three drafts went before it: the first two framed the rover from straight behind or cut it off, and the third put a
large rock in the foreground. The scene JSON of the other three shots is byte-identical to before the change.

## Known shortcomings

- **No blue glow around the setting Sun.** The sky program draws one, but the dust in front of it hides it. The
  references in [site-and-look-references.md](../../site-and-look-references.md) show one.
- The visible Sun disk is a few pixels and looks square at this size.
- Rocks are faceted at close range. The ground has no texture finer than about 0.5 m.
- The rover's flat preview colors come from the Blender script. No Unreal materials exist yet.
- Judged by one reviewer, Claude Code, not by the owner.
