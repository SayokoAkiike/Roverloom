# F2/P2: turning that reaches the commanded yaw rate, 2026-11-07

**Status: kept on branch `rd/task-f2-yaw`. A controller calibration, not a physics change: the driven rover computes
its skid-steer left-right difference with an effective track factor of 1.5. Yaw-rate tracking went from 66% to 98% in
three runs each, with straight driving, tilt, wheel contact, and resets unchanged.**

## Cause

F1 (branch `rd/task-f1-drive-measure`) found turning at 65–66% of the commanded yaw rate. Added diagnostics split the
shortfall (flat ground, friction 0.6, drive model P unchanged):

| Phase | Yaw rate / command | Wheel spin / target | Left-right spin difference / target |
| --- | --- | --- | --- |
| spin left | 66% | 88% | 88% |
| arc left | 65% | 91% | 86% |

The wheels reach about 88% of their commanded difference; the body turns about three quarters of what that difference
would give. Most of the loss is lateral scrub of a skid-steer rover whose wheelbase (195 cm) is close to its track
(207 cm); the rest is wheel spin lagging its target under turning load. No command was clamped and the motor torque
limit (6.0e5) was not the cause.

## Change

`RoverDrive.h`: `DriveTrackScale = 1.5`; `SkidSteerTargets` takes a `TrackScale` that multiplies the turn term only,
default 1.0, which keeps phase C's `CommandSix` targets. `RoverPawn.cpp` drives with 1.5. The factor is close to
1 / 0.66, the measured shortfall; it is a calibration for this rig on flat ground, not a derived constant. The automation
test `Roverloom.Rover.SkidSteer` checks that the scale changes the turn term only and leaves straight driving alone.
No change to the contact model, friction, mass, Phase C records, scoring, or the Python Mission Core.

## Results

`-RoverDrive=f1-flat`, three runs before (F1 branch) and three after, Mac mini, `rdnight`, `-RenderOffscreen`,
1600 × 900. The runs within each side differed by at most 0.7° of heading and 0.001 m/s.

| Measure | Before (3 runs) | After (3 runs) | Criterion | Result |
| --- | --- | --- | --- | --- |
| Spin: yaw rate / command | 66% (heading 148.9–149.0°, 225° commanded) | **98%** (220.8–221.6°) | ≥ 90% | Pass |
| Arc: yaw rate / command | 65% (73.0–73.4°) | **98%** (110.4–110.7°) | ≥ 90% | Pass |
| Arc: speed / command | 95–96% | 95% | no loss beyond 2 points | Pass |
| Straight: speed / command, drift | 98%, 3.932 m along, 0.000 m across | 98%, 3.931–3.932 m, 0.000 m | unchanged | Pass |
| Max tilt (straight, stop) | 1.18°, 1.45° | 1.18°, 1.45° | not worse | Pass |
| Wheels in contact, resets, clamped frames | 6/6, 0, 0 in every phase | 6/6, 0, 0 | not worse | Pass |
| Rotation after the command stops | spin 0.7°, arc 0.4° | spin 1.5°, arc 0.7° | no overshoot that a player sees | Pass |
| Automation tests | 5 of 5 | 5 of 5 (with the new SkidSteer checks) | all pass | Pass |
| GPU, 10 s windows | 11.1–11.3 ms | 11.1–11.6 ms | ≤ 0.5 ms worse | Pass |

## Limits

Flat ground and one friction value only; on loose or sloped ground the scrub, and so the right factor, will differ. A
yaw-rate feedback term would adapt to that; it is not added yet, to keep the change minimal and free of tuning risk.
Next: the same script on the greybox ramps and a step (F1), then decide whether feedback is needed.
