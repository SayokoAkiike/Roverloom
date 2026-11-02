# Scientific benchmark

`uv run roverloom study` runs every agent on every scenario and seed of four tracks. Each scenario is
evidence for one track only. See [model assumptions](model-assumptions.md) for what results can support.
No result here is evidence about real rovers, and no novelty is claimed.

| Track | Scenarios | Question |
| --- | --- | --- |
| `standard` | `science_sprint`, `science_campaign` | Does it work when nothing unusual happens? |
| `stress` | `stress_blackout`, `compound_drive_power`, `compound_late_cascade`, `compound_random` | Does it survive overlapping faults? Rates are invented, and labeled `stress_test` |
| `out_of_distribution` | `ood_rubble`, `ood_long_delay`, `ood_soft_steep` | Does it hold outside the standard range? A test confirms each scenario leaves that range |
| `misestimated_uncertainty` | `mis_inspection`, `mis_pose_bias`, `mis_both` | What if the brief's stated sensor errors are wrong? |

## Method

- Agents share scenarios and seeds, so comparisons are paired, which removes shared luck.
- Achievement has a 95% percentile bootstrap interval, seeded so that reports reproduce. With few runs such
  intervals are too narrow. Track intervals pool different scenarios and resample runs, so they describe
  these scenarios and seeds, and not missions in general.
- Success rates use Wilson intervals.
- `classify_run` names a main cause from the logs, by [fixed rules](../python/src/roverloom/study.py). It is
  a label, not a diagnosis.
- Agents report re-observe, replan, withdraw, and mismatch decisions. These are their own claims.
- Ablations switch off one behavior each: `adaptive-no-reobserve`, `adaptive-no-replan`, `adaptive-no-withdraw`.

## Information separation

[test_study.py](../python/tests/test_study.py) checks this by behavior. Changing hidden truth (uninspected
values, real sensor error, future faults, rocks out of range) leaves every message to an agent byte for byte
identical until the moment a sensor could reveal it. Canary values never appear in those messages.
This covers accidents in the simulator, not deliberate cheating by code in the same process.

## Final results

Measured 2026-11-02 on commit `2be6d9c`, with no uncommitted changes. Benchmark 2.0.0, model `kinematic-0.3`,
scoring `score-0.3`, rover `pathfinder_6w`, seeds 1000 to 1019. 1200 runs: 12 scenarios, 5 agents, 20 seeds, all
pairs complete. Windows 11, Python 3.14.7. Data and conditions are in [results/phase3](results/phase3/README.md).
No parameter was changed after these results.

**This is not a held-out evaluation.** See [how scenarios were used](#how-scenarios-and-seeds-were-used).

### Planners by track

Achievement is the share of the science value sent, 0 to 100. `adaptive` is `adaptive-planner`, and `mission` is
`mission-planner`. Intervals are 95%.

| Track | Runs per agent | `mission` achievement | `adaptive` achievement | Paired difference | Wins / losses / ties | `mission` success | `adaptive` success |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `standard` | 40 | 80.75 [78.12, 83.38] | 80.75 [78.12, 83.38] | 0.00 [0.00, 0.00] | 0 / 0 / 40 | 1.00 [0.91, 1.00] | 1.00 [0.91, 1.00] |
| `stress` | 80 | 41.76 [34.73, 48.78] | 36.12 [30.57, 41.94] | -5.64 [-12.57, +0.96] | 17 / 18 / 45 | 0.45 [0.35, 0.56] | 0.64 [0.53, 0.73] |
| `out_of_distribution` | 60 | 39.82 [28.82, 50.42] | 34.43 [24.37, 44.67] | **-5.38 [-8.86, -2.17]** | 7 / 10 / 43 | 0.47 [0.35, 0.59] | 0.42 [0.30, 0.54] |
| `misestimated_uncertainty` | 60 | 40.53 [33.00, 48.41] | 86.61 [84.81, 88.42] | **+46.08 [+37.96, +53.36]** | 50 / 5 / 5 | 0.95 [0.86, 0.98] | 1.00 [0.94, 1.00] |

Bold marks a paired interval that excludes zero.

### What each behavior contributes

Paired difference in achievement against `mission`:

| Track | Full `adaptive` | Without re-observing | Without replanning | Without withdrawing |
| --- | --- | --- | --- | --- |
| `stress` | -5.64 [-12.57, +0.96] | -5.64 [-12.86, +1.01] | -9.33 [-15.25, -3.54] | -0.36 [-6.34, +5.74] |
| `out_of_distribution` | -5.38 [-8.86, -2.17] | -5.38 [-8.96, -2.12] | -4.22 [-8.35, -0.25] | +1.42 [0.00, +4.25] |
| `misestimated_uncertainty` | +46.08 [+37.96, +53.36] | +43.04 [+34.81, +50.44] | +1.86 [+0.02, +3.94] | +46.08 [+37.66, +53.81] |

- **Replanning carries the gain under misestimated uncertainty.** It finds position error by searching. Without
  it, the gain nearly vanishes. Re-observing adds about 3 points.
- **Withdrawing causes the loss outside the standard range.** Removing it alone turns -5.38 into +1.42.
- **Withdrawing trades science for energy, with little gain in success.** Outside the standard range, energy
  exhaustion falls from 11 runs to 2 of 60, but success falls from 0.48 to 0.42. Under stress, success is 0.64 with
  it and 0.61 without, intervals overlapping, and achievement is lower. Most of the higher success of
  `adaptive` under stress comes from replanning: 0.64 with it, and 0.54 without.
- **Re-observing does nothing on the stress and out-of-distribution tracks,** since inspection there is not noisy.

### Per scenario

Achievement, and success rate. Mean of 20 seeds.

| Scenario | `mission` | `adaptive` | `no-reobserve` | `no-replan` | `no-withdraw` |
| --- | --- | --- | --- | --- | --- |
| `science_sprint` | 72.00, 1.00 | 72.00, 1.00 | 72.00, 1.00 | 72.00, 1.00 | 72.00, 1.00 |
| `science_campaign` | 89.50, 1.00 | 89.50, 1.00 | 89.50, 1.00 | 89.50, 1.00 | 89.50, 1.00 |
| `stress_blackout` | 50.00, 1.00 | 50.00, 1.00 | 50.00, 1.00 | 50.00, 1.00 | 50.00, 1.00 |
| `compound_drive_power` | 77.78, 0.65 | 54.75, 0.80 | 54.75, 0.80 | 54.75, 0.80 | 64.58, 0.70 |
| `compound_late_cascade` | 4.50, 0.00 | 22.00, 0.50 | 22.00, 0.50 | 4.50, 0.00 | 22.00, 0.50 |
| `compound_random` | 34.77, 0.15 | 17.73, 0.25 | 17.73, 0.25 | 20.48, 0.35 | 29.05, 0.25 |
| `ood_rubble` | 87.75, 1.00 | 86.00, 1.00 | 86.00, 1.00 | 86.00, 1.00 | 87.75, 1.00 |
| `ood_long_delay` | 0.00, 0.00 | 0.00, 0.00 | 0.00, 0.00 | 0.00, 0.00 | 0.00, 0.00 |
| `ood_soft_steep` | 31.70, 0.40 | 17.30, 0.25 | 17.30, 0.25 | 20.77, 0.10 | 35.95, 0.45 |
| `mis_inspection` | 81.87, 1.00 | 85.30, 1.00 | 81.87, 1.00 | 85.30, 1.00 | 85.30, 1.00 |
| `mis_pose_bias` | 20.49, 1.00 | 89.96, 1.00 | 88.32, 1.00 | 20.49, 1.00 | 89.96, 1.00 |
| `mis_both` | 19.24, 0.85 | 84.58, 1.00 | 80.52, 1.00 | 21.39, 1.00 | 84.58, 1.00 |

`ood_long_delay` scores 0 for all five: no built-in planner works with 2.5 s delay and 20% loss.
`mission` and `adaptive` have the same `success` on the standard missions because nothing goes wrong there.

### Causes of ending, and decisions

| Track | Agent | Causes (runs) | Re-observe / replan / withdraw per run |
| --- | --- | --- | --- |
| `standard` | both | success 40 | 0 / 0 / 0 |
| `stress` | `mission` | success 36, degraded mobility 42, out of time 2 | 0 / 0 / 0 |
| `stress` | `adaptive` | success 51, degraded mobility 23, insufficient science 4, out of time 2 | 0 / 1.02 / 0.49 |
| `out_of_distribution` | `mission` | success 28, out of time 16, energy exhausted 12, blocked 4 | 0 / 0 / 0 |
| `out_of_distribution` | `adaptive` | success 25, insufficient science 13, out of time 12, blocked 8, energy exhausted 2 | 0 / 2.17 / 0.37 |
| `misestimated_uncertainty` | `mission` | success 57, insufficient science 3 | 0 / 0 / 0 |
| `misestimated_uncertainty` | `adaptive` | success 60 | 8.30 / 2.70 / 0 |

## How results changed

Earlier numbers in this project's history are superseded, and should not be cited.

| Measure | Before the fixes | Final | Reason |
| --- | --- | --- | --- |
| `adaptive`, `misestimated_uncertainty` | 71.41 | 86.61 | A refused second reading made the planner abandon the sample. Fixed |
| `adaptive`, `mis_pose_bias` | 44.34 | 89.96 | The same fix |
| `mission`, `stress` | 79.62 | 41.76 | The compound scenarios were too mild, and every agent saturated. Faults were made harsher, and the time limit shorter |
| `adaptive` minus `mission`, `stress` | 0.00, all ties | -5.64 [-12.57, +0.96] | The same change. The track can now tell them apart |
| `adaptive` minus `mission`, `out_of_distribution` | -5.38 | -5.38 | Unchanged. The drop reproduces on final code |

## How scenarios and seeds were used

**No scenario in this benchmark is untouched, so none can serve as a held-out test.** All of them were run on
versions of the planners during development. Seeds 1000 to 1019 are not held out either: they were in the
full run before the fixes, and seeds 1000 to 1003 were in earlier tuning runs.

| Use during development | Scenarios |
| --- | --- |
| Scenario changed after seeing results | `compound_drive_power`, `compound_late_cascade`, `compound_random`, `ood_long_delay`, and the design missions `canyon_survey`, `dust_season`, `steep_traverse`, `frugal_survey` |
| Scenario unchanged, but its results led to planner changes | `mis_pose_bias`, `mis_both`, `ood_soft_steep` |
| Run during development, without prompting a change | `science_sprint`, `science_campaign`, `stress_blackout`, `ood_rubble`, `mis_inspection` |
| Never used | None |

The large gain under misestimated uncertainty therefore shows that the planner handles the errors it was built
to handle. A fair test needs new scenarios and seeds, chosen before looking at results, and written by someone
who has not seen the planner.
