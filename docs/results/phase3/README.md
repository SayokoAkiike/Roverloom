# Phase 3 final results

Final measurements on commit `2be6d9cbed65b550885c5d13f53e7d4a28cc2ade`. Every run recorded that commit with no
uncommitted changes. Analysis is in [scientific-benchmark.md](../../scientific-benchmark.md) and
[benchmark-reproduction.md](../../benchmark-reproduction.md). **All results describe an unvalidated game model.**

| File | Contents |
| --- | --- |
| `experiment_manifest.json` | Code commit, versions, pins, seeds, scenarios, agents, rovers, platform, memory |
| `study.json`, `study_runs.csv` | 1200 runs of the scientific study, with one row per run |
| `design_study.json` | 420 runs changing one design choice at a time |
| `full_mission_*` | 210 runs of the Full Mission League |
| `rover_design_*`, `autonomy_*` | League results, see below |

Full logs, about 16 GB, stay in the ignored `runs/` directory, and are not committed.

## Conditions

| Experiment | Command | Scenarios | Agents | Rovers | Seeds | Runs |
| --- | --- | --- | --- | --- | --- | --- |
| Full Mission | `uv run roverloom league run --league full_mission` | 7 | `reactive`, `mission-planner` | 3 | 101 to 105 | 210 |
| Design study | `uv run roverloom design-study --workers 2` | 7 | `mission-planner` | 12 variants | 101 to 105 | 420 |
| Study | `uv run roverloom study --workers 2` | 12 | 5 | `pathfinder_6w` | 1000 to 1019 | 1200 |

Worker count does not change results, which a test confirms. `design-study` was run with two workers instead
of its default, to reduce memory use.

## Resources

Windows 11, 14.1 GB of memory, Ryzen AI 5 340. Sampled every 15 s, with a stop set at 700 MB free. Each command ran
once, none was stopped or retried, and all exited 0.

| Experiment | Time | Lowest free memory | Peak Python memory |
| --- | --- | --- | --- |
| Full Mission | 199 s | 2125 MB | 153 MB |
| Design study | 322 s | 1951 MB | 288 MB |
| Study | 2130 s | 1443 MB | 321 MB |

## Autonomy and Rover Design files

These two leagues were not in the final run, and were measured earlier in the same session, before the code was
committed. Their pinned inputs still match. All 105 Rover Design runs are identical, in every recorded metric, to
the same runs in the final Full Mission League. The Autonomy files have not been confirmed that way, and
were produced by code that had uncommitted changes.
