# Benchmark Reproduction Guide

Run from `python/`, with [uv](https://docs.astral.sh/uv/).

```shell
uv run roverloom league verify
uv run roverloom league run
```

`verify` refuses to continue if any scenario, terrain, rover, built-in agent source, or model, scoring,
or builder version differs from [the benchmark file](../benchmarks/roverloom-bench-v1.json).

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

Benchmark `roverloom-bench` 1.0.0, model `kinematic-0.2`, scoring `score-0.2`, five public seeds,
measured 2026-11-02 on the development laptop. **All of it is an unvalidated game model.**

Rover Design League, standard agent `mission-planner`:

| Rank | Rover | Score | Success | Science sent | Energy (Wh) | Fault recovery |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `hauler_8w` | 79.3 | 100% | 11.7 | 151.7 | 81% |
| 2 | `pathfinder_6w` | 69.3 | 100% | 10.4 | 126.9 | 83% |
| 3 | `scout_4w` | 12.3 | 0% | 1.7 | 82.5 | 91% |

The scout has no sample arm, so it cannot reach the science thresholds. This table shows that design
changes results. It does not show a best design: the score ignores design cost, so the most expensive
rover currently wins. Balancing this is open work.

Autonomy League, `pathfinder_6w`:

| Rank | Agent | Score | Success | Science sent |
| --- | --- | --- | --- | --- |
| 1 | `cap-mock` | 75.5 | 100% | 6.22 |
| 1 | `mission-planner` | 75.5 | 100% | 6.22 |
| 3 | `replanner` | 33.9 | 40% | 0.0 |
| 4 | `reactive` | 19.5 | 24% | 0.0 |
| 5 | `waypoint` | 1.9 | 0% | 0.0 |
| 6 | `stop` | 0.0 | 0% | 0.0 |

`cap-mock` matches `mission-planner` because it uses the same rules (tied entries rank by name).
`replanner`, `reactive`, and `waypoint` score only on waypoint missions, since they do no science.

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
