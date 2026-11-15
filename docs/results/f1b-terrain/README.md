# F1b: the 25 cm step and the 15-degree ramp, 2026-11-07

**Status: measurement only (drive model P and F2's controller unchanged). Completion criteria met: both scripts ran to
the end; per-phase values recorded; no physics or controller change.** One run each; Mac mini, `rdnight`,
`-RenderOffscreen`; branch on top of F2 (`rd/task-f2-yaw`).

| Script, phase | Command | Mean speed | Max tilt | Fewest wheels | Body height at end | Resets |
| --- | --- | --- | --- | --- | --- | --- |
| `f1-step` approach, 18 s | 0.5 m/s | 0.496 (99%) | 1.18° | 6/6 | 0.700 m | 0 |
| `f1-step` over the step, 16 s | 0.5 m/s | 0.501 (100%) | 7.92° | 4/6 | 0.950 m (+0.25, on top) | 0 |
| `f1-ramp15` cross to the lane, 30 s | 0.5 m/s | 0.497 (99%), 0.64 m drift | 1.17° | 6/6 | 0.700 m | 0 |
| `f1-ramp15` climb, 26 s | 0.5 m/s | 0.442 (88%) | 17.87° | 2/6 | 3.290 m (top) | 0 |
| `f1-ramp15` stop on the slope, 6 s | 0 | slid 0.017 m | 18.29° | 2/6 | 3.248 m | 0 |

Quarter turns reached 87–94% of the commanded yaw rate (3.27 s each, no stop between crossing and turning, so the
turn-right phase still carried 0.15 m/s of forward speed). Two wheels in contact happen at the ramp's edges, where the
body bridges the slope's start or top; on the slope itself the rover held position with the drive braked.

Ideas for the backlog, not part of this task: speed loss on the 15° climb (88%); four or fewer wheels in contact at
slope edges; the 10° ramp and a downhill run.
