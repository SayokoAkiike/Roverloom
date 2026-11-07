# Roverloom backlog

Development mix: Playability 45%, Physical Accuracy 30%, Visual 25%. Each task: at most three completion criteria,
at most two retries on the same cause; ideas found during a task go here, not into it.

## Done (task branches, not pushed)

| Id | Branch | Result |
| --- | --- | --- |
| P1 | `rd/task-p1-hud` | Kept: HUD panel, text contrast 1.99 -> 3.93 |
| F1 | `rd/task-f1-drive-measure` | Measured: straight 98%, turning 65-66% of commanded yaw rate |
| F2/P2 | `rd/task-f2-yaw` | Kept: effective track 1.5, turning 66% -> 98% |
| V1 | `rd/task-v1-mars-light` | Kept: Mars-inspired sky and haze, horizon readable, GPU unchanged |

## Next

- F1b: the f1 drive script on the greybox ramp and a step: speed, tilt, wheels in contact, resets.
- P2b: chase camera that keeps the rover framed while turning at the new yaw rate.
- V2: rocks and terrain variation around the start, within the GPU budget.

## Ideas (not started)

- Yaw-rate feedback in the drive controller, if slopes or loose ground show the 1.5 factor is not enough (from F2).
- Repeat runs for spread in every drive measurement (from F1).
- Sun angle and time-of-day variants for the Mars sky (from V1).
- HUD panel height changes as lines appear; a fixed height may read calmer (from P1).
