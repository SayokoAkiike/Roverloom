# Three compositions and a three-cut video, 2026-11-16

Capture profile, Movie Render Queue, UE 5.8.4, Apple M4 Mac mini, 1920 x 1080. Models are approximations, not validated. Looks only.
Built by `scripts/unreal/build_mrq.py`, rendered with `scripts/unreal/render_mrq.sh compa|compb|compc noon|afternoon|sunset`.

| | Noon | Afternoon | Sunset |
| --- | --- | --- | --- |
| (a) low, from the front left, wide lens (100 degrees) | [jpg](a_wide_low_noon.jpg) | [jpg](a_wide_low_afternoon.jpg) | [jpg](a_wide_low_sunset.jpg) |
| (b) from behind, toward Mount Sharp, 50 degree lens | [jpg](b_behind_sharp_noon.jpg) | [jpg](b_behind_sharp_afternoon.jpg) | [jpg](b_behind_sharp_sunset.jpg) |
| (c) wheel and dust close-up, 50 mm f/2 lens focused on the wheel | [jpg](c_wheel_dust_noon.jpg) | [jpg](c_wheel_dust_afternoon.jpg) | [jpg](c_wheel_dust_sunset.jpg) |

Notes: the sunset stills use the red-brown `sunset` preset. In (c) the exposure was set per preset (7.5, 8.2, 8.8) because the close-up is lit differently.
In (b) the mountain is faint and low in the frame. In (c) the dust is thin because the rover stands still in the still frames.

## Video

30 s, 30 fps, three cuts of 10 s, afternoon light, 900 frames. **Not in Git** (`unreal/Saved/MovieRenders/Video/`, 40 MB MP4).

1. follow from the front left while the rover drives east, then stops, the rover on the left third of the frame
2. a slow 120 degree orbit around the rover while it spins in place
3. a low camera, pushing in toward the rover as it drives an arc

The rover's timeline was measured with a probe render: it starts rolling at sequence frame 42 (the render's 48-frame warm-up shifts it).

## Dust

| Rolling, noon | Rolling, sunset |
| --- | --- |
| [jpg](dust_rolling_noon.jpg) | [jpg](dust_rolling_sunset.jpg) |

Changes: lifetimes 0.8 to 7.6 s and sizes spread by a skewed draw (most puffs small and brief, a few large and lingering); emission 10 x f + 38 x f^2 puffs a second per wheel
(f is speed over top speed); a sun-facing rim glow in the particle material. **The rim glow is not visible in the stills** (the sun is behind the camera there); not confirmed.

Frame time, Dev profile, afternoon, `f1-flat` drive, 62 s runs (previously +1.2 ms GPU from dust and ruts):

| | fps | mean ms | GPU ms |
| --- | --- | --- | --- |
| dust and ruts on | 30.7 | 30.65 | 28.95 |
| dust and ruts off | 32.4 | 29.21 | 27.58 |
| far Landscape hidden, effects on | 32.3 | 29.06 | 27.23 |

The dust costs +1.4 ms GPU, about the same as before. **Dev is 30.7 fps with everything on, above 30 but with little margin.** The far Landscape costs about 1.7 ms of that.
