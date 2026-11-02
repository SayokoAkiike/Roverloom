# Benchmark Reproduction Guide

Run from `python/`, with [uv](https://docs.astral.sh/uv/).

```shell
uv run roverloom league verify
uv run roverloom league run
```

`verify` refuses to continue if any scenario, terrain, rover, built-in agent source, or model, scoring,
or builder version differs from [the benchmark file](../benchmarks/roverloom-bench-v2.json).

Outputs for each league, in `runs/league/<league>/`:

| File | Contents |
| --- | --- |
| `results.csv`, `results.json` | One row per run |
| `leaderboard.csv`, `leaderboard.json` | Ranked entries, with versions |
| `runs/` | Full logs, replayable and re-scorable |

Check a run: `uv run roverloom score RUN_DIR`, or `uv run roverloom replay RUN_DIR --html view.html`.

## What to expect

- Same platform and Python: identical logs and scores for the same inputs. Tested.
- Other platforms: small differences are possible. Byte equality is not claimed. CI runs on Linux and
  Windows; macOS has not been run.
- `wall_time_s` and environment details differ, and are excluded from a run's digest.

## Measured results

Benchmark `roverloom-bench` 2.0.0, model `kinematic-0.3`, scoring `score-0.3`, five public seeds, measured
2026-11-02 on the development laptop. **All of it is an unvalidated game model.** Data, conditions, and memory
use are in [results/phase3](results/phase3/README.md).

On a machine with limited memory, use `--workers 2` with `study` and `design-study`.

Rover Design League, standard agent `mission-planner`. Ranks are inside each class.

| Class | Rover | Cost | Achievement | Worst scenario | Score | Success | Pareto |
| --- | --- | --- | --- | --- | --- | --- | --- |
| light | `scout_4w` | 27.6 | 33.8 | 2.2 | 26.3 | 11% | Yes |
| standard | `pathfinder_6w` | 58.6 | 68.1 | 0.0 | 60.5 | 71% | Yes |
| heavy | `hauler_8w` | 84.1 | 79.4 | 0.0 | 70.9 | 86% | Yes |

Achievement by mission:

| Mission | `scout_4w` | `pathfinder_6w` | `hauler_8w` | What decides it |
| --- | --- | --- | --- | --- |
| `frugal_survey` | **80.0** | 0.0 | 0.0 | Hard energy cap, one late data window: low idle power |
| `dust_season` | 2.2 | 55.0 | **94.5** | Almost no sun, heavy load: battery and RTG |
| `stress_blackout` | 15.0 | 60.0 | **100.0** | Speed and spare wheels |
| `steep_traverse` | 65.3 | **100.0** | **100.0** | Control rate and speed |
| `canyon_survey` | 48.0 | **100.0** | **100.0** | Speed |
| `science_campaign` | 8.4 | **89.5** | **89.5** | Sample arm |
| `science_sprint` | 18.0 | **72.0** | **72.0** | Sample arm |

The most expensive rover has the best average, but it no longer wins everything, and the cheapest rover is
the only one to score on `frugal_survey`. These missions were written to create these trade-offs, so this shows
the benchmark can express them. It does not show that any design is best.

Autonomy League, `pathfinder_6w`:

| Rank | Agent | Score | Achievement | Success |
| --- | --- | --- | --- | --- |
| 1 | `cap-mock` | 75.2 | 84.3 | 100% |
| 2 | `mission-planner` | 75.2 | 84.3 | 100% |
| 3 | `replanner` | 33.9 | 40.0 | 40% |
| 4 | `reactive` | 19.5 | 24.0 | 24% |
| 5 | `waypoint` | 1.9 | 6.7 | 0% |
| 6 | `stop` | 0.0 | 0.0 | 0% |

`cap-mock` uses the same rules as `mission-planner`, and says nothing about a real language model.
For planner comparisons, see the [scientific benchmark](scientific-benchmark.md).

Full Mission League, on code commit `2be6d9c`:

| Rank | Entry | Score | Achievement | Success | Science sent |
| --- | --- | --- | --- | --- | --- |
| 1 | `hauler_8w` + `mission-planner` | 70.9 | 79.4 | 86% | 15.71 |
| 2 | `pathfinder_6w` + `mission-planner` | 60.5 | 68.1 | 71% | 13.00 |
| 3 | `scout_4w` + `mission-planner` | 26.3 | 33.8 | 11% | 5.69 |
| 4 to 6 | `scout_4w`, `pathfinder_6w`, `hauler_8w` + `reactive` | 0.0 | 0.0 | 0% | 0.00 |

`reactive` does no science, so it scores nothing on these missions. Its rows tell nothing about the rovers.

Design study, on the same commit: change in mean achievement from changing one thing, over 5 seeds.

| Rover | Change | Cost after | `science_campaign` | `dust_season` | `frugal_survey` | `steep_traverse` | `stress_blackout` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `scout_4w` | Add arm, larger chassis and battery | 36.7 | +26.6 | -2.2 | -46.7 | -40.0 | +35.0 |
| `scout_4w` | Solar to RTG | 47.4 | 0.0 | -1.1 | -80.0 | -65.3 | 0.0 |
| `pathfinder_6w` | Solar to RTG | 72.1 | 0.0 | +25.8 | 0.0 | 0.0 | -10.0 |
| `pathfinder_6w` | Remove arm | 50.6 | -59.5 | -25.0 | 0.0 | 0.0 | -30.0 |
| `pathfinder_6w` | Four wheels | 54.4 | -8.8 | -34.2 | 0.0 | -60.0 | -10.0 |
| `hauler_8w` | RTG to solar | 70.6 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| `hauler_8w` | 25% less battery | 82.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| `hauler_8w` | Remove arm | 76.1 | -61.6 | -64.5 | 0.0 | 0.0 | -70.0 |
| `hauler_8w` | Four wheels | 75.7 | -82.5 | -83.4 | 0.0 | -100.0 | -50.0 |

The builder refused 25% less battery for `scout_4w` and `pathfinder_6w`, because of peak power. Replacing the RTG on
`hauler_8w` changed no achievement, so the RTG does not explain its `dust_season` result. Its battery does not
either, within 25%. The full table is in [design_study.json](results/phase3/design_study.json).

## Private seeds

```shell
uv run roverloom league run --seeds-file ../../secret/seeds.json --out ../../secret/results
```

The file holds `{"seeds": [..]}`, outside the repository. Result and leaderboard files then leave out
seeds and record a count and hash. **Run directories still contain them**, so share only the files in
the table above. A hash of a few small integers can be guessed, so use large random seeds.

## Changing a benchmark

Any change to pinned inputs makes results incomparable:

1. Make the change, and increase the affected `version`, `MODEL_VERSION`, or `SCORING_VERSION`.
2. Copy to a new benchmark file, or increase `version`.
3. Run `uv run roverloom league lock --benchmark NAME`.
4. Do not mix leaderboards from different versions.

Do not lock merely to silence a failed `verify`. First find out what changed.
