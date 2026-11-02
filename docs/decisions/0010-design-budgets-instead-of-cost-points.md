# ADR 0010: Design classes, not cost points

Status: Accepted, 2026-11-02.

## Context

The Rover Design League ranked rovers by mission score, which ignored cost, so the most expensive rover
won. The efficiency term also used each rover's own battery as its budget, so a bigger battery earned a
better score.

## Decision

- Cost never becomes points. Any conversion rate would be an invented number deciding the outcome.
- Designs compete inside classes defined by budgets. Each class has its own ranking.
- A leaderboard reports `mean_achievement`, which has no efficiency or cost, and `robustness`, the worst
  scenario's achievement. It also reports `design_cost` and `pareto` over these three measures.
- Hard constraints refuse a design and list every broken rule: volume, peak power, compute capacity, and
  part compatibility.
- Efficiency uses a fixed `reference_energy_wh` per mission.
- `roverloom rover --explain` and `roverloom design-study` trace an outcome to a part, by changing one
  thing at a time.

## Consequences

- There is no overall winner across classes, which is the honest result.
- Class limits are themselves invented numbers, recorded in [model assumptions](../model-assumptions.md).
- `score-0.3` and `builder-0.2` make earlier leaderboards incomparable, so benchmark v1 is archived.
