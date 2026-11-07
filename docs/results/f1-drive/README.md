# F1: drive model P on flat ground, commanded against measured, 2026-11-07

**Status: measurement only; drive model P is unchanged. One run. Turning reaches about two thirds of the commanded yaw
rate; straight driving tracks within 2%.**

## Method

`-RoverDrive=f1-flat` (this branch) sends a fixed script through the keyboard's command path: settle 3 s, straight 8 s
at the speed limit, stop 4 s, spin left 8 s at the yaw-rate limit, stop 4 s, arc left 8 s at half of both, stop 4 s.
Each phase logs commanded values and measured ones: mean forward speed and mean yaw rate (from the body's velocities,
integrated over the phase), displacement along and across the heading the phase started with, heading change,
maximum tilt, fewest wheels in contact, frames whose command was clamped, and rig resets.

Mac mini (Apple M4, macOS 27.0.1, UE 5.8.4), night user `rdnight`, `-RenderOffscreen`, 1600 × 900, run `f1-flat-v1`
(`game f1-flat-v1 45 f1-flat`). Flat ground at the start position; no slope or step yet.

## Results

| Phase | Command | Mean speed | Mean yaw rate | Displacement | Heading | Max tilt | Wheels | Resets |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| straight, 8.01 s | 0.500 m/s | 0.491 m/s (98%) | 0 | 3.932 m along, 0.000 m across | 0.0° | 1.18° | 6/6 | 0 |
| stop, 4.01 s | 0 | 0.010 m/s | 0 | 0.036 m along | 0.0° | 1.45° | 6/6 | 0 |
| spin left, 8.01 s | 0.4918 rad/s | 0 | 0.3246 rad/s (66%) | 0 | 149.0° (225° commanded) | 0.00° | 6/6 | 0 |
| stop, 4.00 s | 0 | 0 | 0.0030 rad/s | 0 | 0.7° | 0.00° | 6/6 | 0 |
| arc left, 8.01 s | 0.250 m/s, 0.2459 rad/s | 0.239 m/s (96%) | 0.1599 rad/s (65%) | 1.430 m along, 1.078 m across | 73.4° | 0.32° | 6/6 | 0 |
| stop, 4.00 s | 0 | 0.003 m/s | 0.0017 rad/s | 0.008 m along | 0.4° | 0.80° | 6/6 | 0 |

No frame was clamped. Rendering stayed at 83–86 fps, GPU 11.1–11.5 ms.

## Reading

- Straight driving follows the command (98% of speed, no lateral drift) and stops within 4 cm.
- Yaw rate reaches 65–66% of the command in both the spin and the arc. A skid-steer rover turns by scrubbing its
  wheels sideways, so a shortfall is expected; its size here is a measurement of model P, not a validated value.
- For a player, turning feels slower than the HUD's yaw limit suggests. That is a Playability finding (P2) as much as a
  physics one (F2).

## Next

- F1: add slope and step presets on the greybox ramps, with the same per-phase log.
- F2 candidates, to register before any change: a yaw-rate feedback term in the skid-steer targets (controller, not the
  contact model), judged by yaw tracking ≥ 90% with no loss in straight tracking, tilt, or resets; and Phase C's open
  questions stay untouched.
- Limits: one run, flat ground, one friction value (0.6); no repeat runs yet for spread.
