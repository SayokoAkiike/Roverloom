# Competition Rules Draft

**Draft for discussion. No competition exists or is open**, and no public server runs submitted code.
Everything here runs offline on your own machine. Organizers must complete the open points below,
including legal and licensing review, before any public event.

## Leagues

| League | Fixed | Compared | Question |
| --- | --- | --- | --- |
| Autonomy | Rover | Agents | Who makes the best decisions with the same machine? |
| Rover Design | Agent | Rovers within budget | Which design serves a standard agent best? |
| Full Mission | Scenarios, budgets | Rover and agent together | Who designs and operates best overall? |

All three are implemented in `roverloom league run`. Only built-in entries and local additions run.

## Fairness

- Every entry runs every scenario and seed exactly once. A check fails the league otherwise.
- Fault schedules come only from the scenario and seed, so all entries face the same faults.
- A benchmark's versions and hashes are fixed. See [Benchmark Reproduction](benchmark-reproduction.md).
- Final standings use private scenarios and seeds, injected after submissions close.
- Rerun finalists, and compare only results from the same backend.
- Lightweight and future Unreal results are separate competitions.

## Scoring (`score-0.3`)

Science missions, out of 100:

- 70 × fraction of total science value sent.
- 10 for ending at base, after sending at least some science.
- On success: up to 10 for remaining time, and up to 10 for remaining energy.
- Minus 2 per collision, with a floor of 0.

Waypoint missions: 60 × fraction reached; on success up to 20 each for time and energy; minus 2 per collision.

Also reported: success, safety (collisions, watchdog stops, lowest battery), and fault recovery. A fault
counts as recovered when the rover travels 1 m after it, which is a proxy, not proof of progress.

Rank: mean score, then success rate, then lower energy, then name.

## Rover budgets

Designs must be real designs, not plain parameters, and fit a class. Entries are ranked inside their class,
and cost never becomes points. See [Rover Builder](rover-builder.md) and [ADR 0010](decisions/0010-design-budgets-instead-of-cost-points.md).

## Conduct

- Do not attempt to access hidden data, the evaluator, or other entries.
- Do not use assets or designs without permission. Record provenance.
- Publishing winners' code, and licenses, must be decided before any event.

## Open before any public event

- [ ] A real sandbox, with no network and resource limits. The local mock is not one.
- [ ] More evaluation scenarios, kept private.
- [ ] Prize, eligibility, and intellectual property terms. Legal review.
- [ ] Unreal Engine and asset licensing, if Unreal is used. See [licensing review](licensing-review.md).
- [ ] Appeals, tie handling across workers, and a run on real Codabench infrastructure.
