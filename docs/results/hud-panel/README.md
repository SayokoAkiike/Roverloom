# HUD panel: a translucent backdrop behind the G2 HUD text, 2026-11-07

**Status: verified on the Mac mini; all eight registered checks passed. Kept on branch `rd/task-p1-hud`, not merged
or pushed.** Written by the first trial night (20261107-1622), verified 2026-11-07 against the baseline measured by the
second (20261107-1810). Checks were registered before the change was built and were not changed afterwards.

## Change

`RoverHud.{h,cpp}`: the HUD collects its lines, measures them with `GetTextSize`, draws a black rectangle at alpha 0.55
with 10 px padding behind them, then draws the same lines in the same colors and order. It logs
`Rover HUD panel: x .. y .. w .. h ..` when the rectangle changes, so image checks use the exact region.
`rd/night/shot_metrics.py`: the registered image metrics, standard library only.

Nothing else changed: no physics, camera, input, or scoring code.

## How it was run

Mac mini (Apple M4, macOS 27.0.1, UE 5.8.4), night user `rdnight`, sandboxed, `-RenderOffscreen`, 1600 × 900,
`-RoverBench=20`. Baseline: run `20261107-1810-c1-base-g`, the night branch before the change, same Unreal sources
otherwise. Variant: run `p1-hud-v1` (build, test, game). The variant's Unreal sources equal those of this branch.
Region R is the panel logged when the screenshot was taken: x 14, y 10, w 540, h 300 (the panel grows as HUD lines
appear: heights 98, 278, 300, 322, 300 during the run).

## Registered checks

| Id | Check | Pass when | Baseline | Variant | Result |
| --- | --- | --- | --- | --- | --- |
| C1 | Both screenshots exist, same size, not black | mean luma > 10 | 1600 × 900, 149.4 | 1600 × 900, 143.6 | Pass |
| C2 | Background inside R darkened | median luma ≤ 0.5 × baseline and ≤ 70 | 111.8 | 51.3 (≤ 55.9) | Pass |
| C3 | Text contrast inside R, (p99 + 5) / (median + 5) | > 1.5 × baseline | 1.99 | 3.93 (> 2.99) | Pass |
| C4 | Rest of the frame unchanged: pixels outside R + 4 px with max channel difference > 24 | ≤ 2% | — | 0.0% | Pass |
| C5 | GPU time, mean of the `Rover frames` lines | variant − baseline ≤ 0.5 ms | 10.81 ms | 10.745 ms (−0.07) | Pass |
| C6 | Unreal build of the variant | succeeds | — | succeeded, 19 s | Pass |
| C7 | Automation `Roverloom.Rover+Bridge+Module` | all pass | — | 5 of 5 | Pass |
| C8 | `pytest`, `ruff check`, `ruff format --check`, `mypy`, `check_repo.py` | all pass | — | 783 passed, 1 skipped; others clean | Pass |

Frame rate in the variant's two 10 s windows: 86.7 and 84.6 fps (baseline 86.5 and 75.5, the second window including
shutdown). One screenshot per side; the GPU difference is within the spread measured as `rdnight` today (10.7–11.3 ms), so
"no regression within 0.5 ms" is what C5 shows, not a speed-up.

## Images

| Before | After |
| --- | --- |
| ![before](before.png) | ![after](after.png) |

Downscaled to 800 × 450 from the 1600 × 900 screenshots.

## Limits

Measured on one scene and camera (Chase, rover at rest). Legibility is judged by luma statistics, not by people.
