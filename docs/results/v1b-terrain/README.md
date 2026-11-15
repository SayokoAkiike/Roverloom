# V1b: Mars palette for the ground, outcrops, and rocks, 2026-11-07

**Status: kept and merged. Criteria: a clear visual improvement in same-condition images; build, render, and automation
tests pass; GPU no more than 0.5 ms worse. All three met.** Colors are mars_inspired, chosen by eye against V1's sky.

## Change (`RoverPlaygroundGameMode.cpp`, colors and decor only)

- Regolith (0.42, 0.24, 0.14) -> (0.46, 0.21, 0.10): rust instead of tan. Outcrops (step, ramps) (0.33, 0.20, 0.13) ->
  (0.17, 0.11, 0.08): dark basalt, so test features read against the ground. Rocks (0.25, 0.17, 0.12) ->
  (0.13, 0.09, 0.07), each shaded by 0.8-1.25.
- 36 rocks in the view ahead with a fixed seed, at x 30-80 m: beyond every test lane (the step ends at x 18 m, the
  ramps' plateaus at x 25.6 m). Shapes, collision, and friction of the test features are unchanged.

## Results

Same base commit (9a058a4), Chase camera, sun, settings: `-RenderOffscreen`, 1600 × 900, `-RoverBench=20`, Mac mini.

| Measure | Before (`v1b-base`) | After (`v1b`) |
| --- | --- | --- |
| Ground mean RGB (x 200-1400, y 700-880) | 198, 161, 127 | 208, 156, 111 (R − B 71 -> 97) |
| Sky mean RGB | 167, 131, 98 | 171, 134, 101 |
| fps, GPU (two 10 s windows) | 87.2, 10.72 / 10.93 ms | 87.1, 11.19 / 11.12 ms (+0.33 ms mean) |
| Automation | — | 5 of 5 |

| Before | After |
| --- | --- |
| ![before](before.png) | ![after](after.png) |
