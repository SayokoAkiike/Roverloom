# 0016: Measured Gale heightfield as an optional terrain source

Status: Accepted by the owner (2026-11-16), as direction. The loader and schema exist; **no Gale scenario exists yet**,
because the heightfield file is on the Mac mini and not in this repository.

## Context

The owner chose Gale as the site, and asked for the most advanced visual result. Unreal and the lightweight backend
could not share a `terrain_id` for it: [`terrain.schema.json`](../../schemas/terrain.schema.json) accepted only
procedural height (`seed`, `amplitude_m`, ...). See [terrain results](../results/terrain-gale/README.md).

## Decision

- `terrain.schema.json` accepts exactly one of `height` (procedural, unchanged) or `heightfield`: a raw `r16` file
  named in the terrain document, with its sample count, height range, and SHA-256.
- `Terrain` loads the file from `scenarios/terrains/data/`, or from `ROVERLOOM_TERRAIN_DIR`, and refuses a missing
  file, a wrong size, a wrong sample count, or a hash mismatch. Heights are relative to the lowest sample, and rows
  are flipped so that row 0 is the southern edge, as for procedural terrain.
- **The raw file stays out of Git** (visual roadmap rule). Only the terrain document, with the hash, is committed.
  A clone without the file gets an error that says so, and every procedural terrain keeps working.
- `Terrain.document` is hashed into the scenario hash as before, so the hashes of all existing scenarios are unchanged.
  Rocks and soft soil on a measured terrain remain generated or hand-placed, and are labeled so; the DTM's resolving
  power is coarser than its 1 m spacing.

## Consequences

- No behavior of any existing scenario changes, so `MODEL_VERSION` and `SCORING_VERSION` stay as they are. **A
  scenario on the Gale terrain would be a new scenario**, with its own results; none are claimed.
- `max_soil_slip`, rock density, and the drive model on this ground are invented, as elsewhere. A real shape does not
  validate soil, slip, or the drive model.
- Not done: the Gale terrain document, a scenario on it, the Unreal side mapping `terrain_id` to the Landscape, and
  a size check for 1009 × 1009 in the lightweight preview (the loader accepts up to 4 million samples).
- Scenarios on this terrain must be written before any planner is run on it, if a claim is to be made.

## Benchmark relock, 2026-11-16

`world.py` is pinned, so adding the loader changed the `code:core` pin of `roverloom-bench` 2.0.0 and made 15 tests
fail. The cause was checked before relocking:

- All 15 failures were that one mismatch: 14 as `ContractError: ... code:core has changed`, and `test_league_cli` as
  `league verify` returning 2.
- The relock changed one line, `code:core`. The other 38 pins (scenarios, terrains, agents) are identical.
- Behavior check, one-off, not committed: the code at the previous commit and the new code ran every practice and
  benchmark scenario with `waypoint`, `reactive`, `replanner`, `mission-planner`, and `adaptive-planner`, each at its
  scenario's default seed. All 100 pairs of `evaluate_run` metrics matched byte for byte. This covers those agents and
  seeds only, not private seeds or other agents.
- After the relock, `league verify`, `ruff`, `mypy`, `check_repo.py`, and `pytest` (843 passed, 2 skipped) passed, on Linux.

Benchmark version, scenarios, seeds, scoring, and expected values are unchanged. Results in
[phase3](../results/phase3/README.md) were measured under the old pin; the code path they used is behaviorally
unchanged by the check above, but their recorded pin is the old one.
