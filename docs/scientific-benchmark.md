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
  intervals are too narrow. Pairs on one scenario share a design, so they are not independent evidence.
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

## Results

**The final study has not been completed.** The last full run, on 2026-11-02, was stopped by the system for
low memory after later fixes were made. Rerun with `uv run roverloom study`, and replace this section.
The numbers below are measurements of intermediate code, and are provisional.

### Full run before the final fixes (`pathfinder_6w`, 20 seeds)

This run found two faults, since fixed: full `adaptive-planner` lost to its own ablation, because a refused
second reading made it give up on a sample, and the stress track was so mild that every agent saturated.
Stress numbers are therefore omitted, and the `mis_pose_bias` and `mis_both` figures are stale.

| Track | `mission-planner` achievement [95%] | `adaptive-planner` achievement [95%] | Paired difference [95%] |
| --- | --- | --- | --- |
| `standard` | 80.75 [78.12, 83.38] | 80.75 [78.12, 83.38] | 0.00 (40 ties) |
| `out_of_distribution` | 39.82 [28.82, 50.42] | 34.43 [24.37, 44.67] | -5.38 [-8.86, -2.17] |
| `misestimated_uncertainty` | 40.53 [33.00, 48.41] | 71.41 [66.17, 76.58] | +30.87 [+24.28, +37.37] |

Removing withdrawal gave +1.42 [0.00, +4.25] on the out-of-distribution track. So the withdrawal rule, as
written, cost achievement there, while cutting energy exhaustion from 12 runs to 2 of 60. `ood_long_delay`
scored 0 for both planners: none of the built-in planners work with 2.5 s delay and 20% loss.

### Spot check after the fixes (3 seeds, too few for intervals)

Mean achievement on seeds 3001 to 3003:

| Scenario | `mission-planner` | `adaptive-planner` |
| --- | --- | --- |
| `compound_drive_power` | 77.8 | 77.8 |
| `compound_late_cascade` | 4.5 | 4.5 |
| `compound_random` | 34.8 | 43.0 |
| `mis_pose_bias` | 20.5 | 90.0 |

### Limits

The adaptive planner was developed while looking at these scenarios, so this is not a held-out evaluation.
See [model assumptions](model-assumptions.md#scenario-and-agent-coupling).
