# Roverloom backlog

Development mix: Playability 45%, Physical Accuracy 30%, Visual 25%. Each task: at most three completion criteria,
at most two retries on the same cause; ideas found during a task go here, not into it.

## Integration log (feature/unreal-project, local; not pushed to GitHub)

Gates for each merge: Unreal build, automation tests, one drive or bench run, Python checks, secret scan. Undo a merge
with `git revert -m 1 <merge commit>`.

| Merged | Merge commits | Branch tip before | Gates |
| --- | --- | --- | --- |
| P1, F1 | ae2f0ba, 95f3ee7 | d1a0847 | build ok, 5/5 automation, HUD and drive logs present, pytest 818 passed |
| F2 + F1b, V1 | ed22597, 024fa94 | 95f3ee7 | build ok, 5/5 automation, turning 98%, Mars sky, pytest 821 passed |
| V1b | 6547fe7 | 9a058a4 | build ok, 5/5 automation, bench render, GPU +0.33 ms, check_repo ok |

## Done (task branches)

| Id | Branch | Result |
| --- | --- | --- |
| P1 | `rd/task-p1-hud` | Kept: HUD panel, text contrast 1.99 -> 3.93 |
| F1 | `rd/task-f1-drive-measure` | Measured: straight 98%, turning 65-66% of commanded yaw rate |
| F2/P2 | `rd/task-f2-yaw` | Kept: effective track 1.5, turning 66% -> 98% |
| V1 | `rd/task-v1-mars-light` | Kept: Mars-inspired sky and haze, horizon readable, GPU unchanged |
| F1b | `rd/task-f1b-terrain` | Measured: 25 cm step climbed; 15° ramp at 88% speed, 2/6 wheels at edges, no resets |

## Next

- P2b: chase camera that keeps the rover framed while turning at the new yaw rate.

## Ideas (not started)

- Microsoft Update Assistant started again as rdnight at 20:55 through its on-demand XPC service, though its agents
  are disabled; the dispatcher refused Unreal steps until rdnight's own process was ended (from V1b).

- 15° climb speed 88%; two wheels in contact at slope edges; 10° ramp and downhill runs (from F1b).

- Yaw-rate feedback in the drive controller, if slopes or loose ground show the 1.5 factor is not enough (from F2).
- Repeat runs for spread in every drive measurement (from F1).
- Sun angle and time-of-day variants for the Mars sky (from V1).
- HUD panel height changes as lines appear; a fixed height may read calmer (from P1).
