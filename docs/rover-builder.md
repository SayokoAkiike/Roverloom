# Rover Builder

Compiles a rover design into simulator parameters. Rules are in
[rover_builder.py](../python/src/roverloom/rover_builder.py), version `builder-0.2`.
**These are simplified game rules, not validated wheel, soil, or power models.**

Standard designs (from `uv run roverloom rover`):

| | `scout_4w` | `pathfinder_6w` | `hauler_8w` |
| --- | --- | --- | --- |
| Wheels | 4 | 6 | 8 |
| Mass (kg) | 389.7 | 853.5 | 1328.4 |
| Cost | 27.6 | 58.6 | 84.1 |
| Speed limit (m/s) | 0.40 | 0.50 | 0.60 |
| Climb limit (slope) | 0.62 | 0.54 | 0.45 |
| Soil slip scale | 1.00 | 0.88 | 0.68 |
| Idle power (W) | 211 | 261 | 279 |
| Power | Solar, 180 W nominal | Solar, 360 W nominal | RTG, 90 W |
| Range sensor | 10 m, 7 beams | 12 m, 9 beams | 18 m, 11 beams |
| Control period (s) | 1.0 | 0.5 | 0.5 |
| Sample arm | No | Yes | Yes |

| Class | Light | Standard | Heavy |
| Volume used (L) | 77 of 110 | 176 of 210 | 246 of 320 |

The legacy `rovers/standard_6w.json` is plain parameters. It still runs, but cannot enter a design league.

## Constraints

A design is refused with every rule it breaks listed:

| Rule | Limit |
| --- | --- |
| Class budgets | light: cost 40, 600 kg; standard: cost 70, 1000 kg; heavy: cost 100, 1600 kg |
| Volume | Parts must fit in 0.5 L per chassis kg |
| Peak power | Driving or task load, within 2 W per battery Wh |
| Compute | Low handles 9 beams, standard 21, high 32; precise pose needs more than low |
| Sample arm | Chassis of at least 250 kg |
| RTG | Chassis of at least 400 kg |
| Structure, ground pressure | As before |

All limits are invented game values. See [model assumptions](model-assumptions.md).

## Cost and achievement stay apart

Cost is never converted to points ([ADR 0010](decisions/0010-design-budgets-instead-of-cost-points.md)).
Designs rank inside their class. A leaderboard shows achievement, worst-scenario robustness, cost, and whether
a design is on the Pareto front of those three. Efficiency uses a fixed energy reference, so a bigger battery
earns nothing by itself. Results by mission are in the
[reproduction guide](benchmark-reproduction.md#measured-results).

## From a result to its cause

- `uv run roverloom rover NAME --explain` shows budgets, which part sets each limit, and what a 25% change to
  each part does, including changes the rules refuse.
- `uv run roverloom design-study` changes one design choice at a time, and reruns the missions. A
  difference between finished designs cannot say which part caused it, and an intervention can.

## Known limits

- Class limits were set where the standard rovers fall.
- Solar output has no day and night cycle.
- Wheel count affects only aggregated values. No wheel-level dynamics exist.
- Plausibility checks are coarse, and a design can pass them and still be unrealistic.
