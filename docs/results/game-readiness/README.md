# Game readiness: what a player can do today, 2026-11-07

Measured on `feature/unreal-project` at `dad2777` (Mac mini, `rdnight`, UE 5.8.4, `-RenderOffscreen` 1600 × 900): build
ok, automation 5 of 5, three scripted drives through the keyboard's command path. The Python Mission Core was run once
for comparison. Nothing below is described as working unless it ran here.

## The flow, step by step

| Step | In Unreal today | Evidence |
| --- | --- | --- |
| Start | **Works.** The game starts on the C++ test ground; the rover settles on six wheels in 3 s, no resets | `drive-log.txt`: settled at z 0.700 m, 6/6 |
| Drive and turn | **Works** (drive model P, provisional). Straight 98% of commanded speed; turning 98% of commanded yaw rate (F2); stops within 4 cm | `flat-after-turns.png`, log `f1-flat` |
| Cameras, HUD | **Works.** Chase, mast, hazard, free cameras; HUD with speed, yaw, tilt, wheels, watchdog, frame time, on a panel (P1) | HUD in every shot |
| Obstacles | **Partly.** The 25 cm step is climbed (tilt 7.9°, 4/6 wheels, no reset). The 15° ramp is climbed at 96% speed, but in this run the rover ended with one side off the plateau's edge (tilt 25°, 2/6 wheels, no reset); F1b's run on the same ramp ended on it. Ramp results vary between runs | `on-the-step.png`, `off-the-ramp-edge.png` |
| Science mission | **Missing in Unreal.** No targets, instruments, data, or mission logic exist in `unreal/` | Code search: no mission or science code under `unreal/Source` |
| Success, failure | **Missing in Unreal.** No objectives, no end condition; the HUD says real-time runs are not scored | HUD line 2 |
| Results screen | **Missing in Unreal** | — |
| Battery, faults, comms | **Missing in Unreal** (HUD: "Battery not modeled") | HUD |
| Mission Core link | **Missing.** The Unreal contract is specified, but there is no bridge, no run-log writer, and no scoring of Unreal runs | `docs/unreal-contract.md`, `docs/project-status.md` |

The complete mission loop exists only in the Python Mission Core (2D, its own unvalidated game model): one run of
`science_campaign` with the `mission-planner` agent, seed 1, scored 79.6, science 89.5%, 3 of 3 faults recovered,
returned to base, battery never below 66% (`python-mission-metrics.json`). A browser view (`roverloom play`) exists
there; it was not opened in this check.

**Where the Unreal experience stops:** after driving. A player can start, drive, turn, change cameras, and cross the
step and ramps, but has nothing to do, win, or lose, and no result at the end.

## Prioritized backlog to a complete player experience

| # | Item | Area | Why first |
| --- | --- | --- | --- |
| 1 | Run-log writer in Unreal (telemetry, commands, events per the contract) and `check_run_contract` on it | Playability / G2 | Every later item (scoring, results, mission) needs runs the Mission Core can read; it is G2's open item |
| 2 | One mission in Unreal: a few science targets placed on the test ground, reached and "observed" by stopping within range | Playability | Gives the player a goal; smallest version of the mission loop |
| 3 | Success and failure: all targets observed and back at start = success; time limit, tip-over, or reset = failure | Playability | Makes a run end |
| 4 | Results screen: time, distance, targets, resets, then the Mission Core's score from the run log | Playability | Closes the loop; reuses Python scoring instead of a second scorer |
| 5 | Ramp edge safety: wider ramp lanes or edge markers, and the cause of run-to-run variation on the 15° ramp | Physics / Playability | Seen in this check: the rover went off the plateau's side |
| 6 | Battery and a simple fault on the Unreal side, from the contract | Physical Accuracy | The Mission Core has them; Unreal shows "not modeled" |
| 7 | Visual targets and terrain: target markers, a few more terrain features, sun-angle variants | Visual | Needed once #2 exists |
| 8 | Camera bounce while driving and braking (P2 attempt not adopted) | Playability | Small comfort item |

Physics work on drive model P stays inside its provisional status: Phase C's failed checks remain open and are not
rewritten by these items.
