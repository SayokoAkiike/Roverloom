# V1: a Mars-inspired sky and dust haze, 2026-11-07

**Status: kept on branch `rd/task-v1-mars-light`. Criteria: a Mars-like sky color, a readable horizon (sky − ground
luma at least 20 apart), GPU no more than 0.5 ms worse; all three met. An artistic preset
(mars_inspired), not a validated atmosphere model. No change to the camera, terrain, sun direction, physics, or HUD.**

## Change (`RoverPlaygroundGameMode::SpawnLights`)

- Sky atmosphere, set through the component's setters: Mars's radius (3389.5 km), scale heights 11 km, little
  Rayleigh scattering (scale 0.0005), dust (Mie) scattering 0.02 in a warm color (0.95, 0.60, 0.32) with blue-weighted
  absorption, anisotropy 0.5, reddish ground albedo.
- Sun color slightly warm white (1.0, 0.96, 0.90); same direction and intensity.
- Height fog: dust-colored inscattering (0.55, 0.38, 0.25), density 0.01 (half the default).

Writing the atmosphere's fields directly before `FinishSpawning` compiled but did not render: two different presets
gave the same image. The setters fixed it.

## Results

Same base commit, camera (Chase), terrain, sun, and settings: `-RenderOffscreen`, 1600 × 900, `-RoverBench=20`,
Mac mini, `rdnight`. Mean colors of the 1600 × 900 screenshots: sky x 700–1580, y 20–150; ground x 200–1400,
y 700–880. Luma is Rec. 601.

| Run | Sky RGB | Ground RGB | Sky − ground luma | GPU, two 10 s windows |
| --- | --- | --- | --- | --- |
| Before (`v1-base`) | 82, 111, 139 (blue) | 204, 170, 134 | −70 | 10.69, 10.57 ms |
| Rejected: dust 0.04, default fog (`v1-mars3`) | 181, 151, 118 | 192, 156, 124 | −7: horizon lost, shadows washed out | 10.76, 10.59 ms |
| **After** (`v1-mars4`) | 167, 131, 98 (butterscotch) | 198, 161, 127 | −30: horizon readable | 10.76, 10.57 ms |

GPU time is within 0.2 ms of the baseline, inside run-to-run spread.

| Before | After | Rejected (too much dust) |
| --- | --- | --- |
| ![before](before.png) | ![after](after.png) | ![rejected](rejected-too-much-dust.png) |

## Limits

One camera, one sun angle, one screenshot per preset. Values were chosen by eye; how a real Martian sky looks varies
with dust load and time of day. Shadows are softer than before because the dusty sky adds more fill light.
