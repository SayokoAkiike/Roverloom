# 0006: Mission core layout and contract extensions

Status: Accepted (2026-11-02)

## Context

The Python side grew from contract tests to a working mission core. Several earlier choices needed
changes, and this records why and how to migrate.

## Decisions

- **`jsonschema` is a runtime dependency**, and no longer test-only, because rejecting bad configuration
  and logs at runtime is required behavior.
- **Schema version stays 0**, as all changes so far are additive and optional. Documents valid under the
  first schema remain valid, which is tested. Version 1 begins with the first breaking change or public
  release.
- **`scenarios/example_reach_position.json` moved to `scenarios/practice/`.** Terrains live in
  `scenarios/terrains/`, and rovers in `rovers/`, so that `terrain_id` and `rover_id` resolve to files.
- **Scenarios are never passed to agents.** They contain faults and noise. Agents get `MissionBrief`.
- **The package runs from a checkout.** Bundling data into a wheel was deferred, since nothing publishes one.
- **Replay is kinematic**, as planned in the vertical slice plan.
- **Preview is one dependency-free HTML file with the standard library server.** It covers both replay
  and live driving, avoiding a frontend build.
- **Bridge messages use an envelope**, `{"type": ..., "body": ...}`, because the protocol needs start and
  end messages as well as Action and Observation. The `body` values conform to the shared schemas.
  This replaces the bare messages proposed in the first draft of the integration design.
- **Watchdog is 2 s**, not the 0.5 s in the first draft, because scenario latency applies both ways and
  observations arrive every 0.5 s.

## Migration

Replace references to the old scenario path. Runs saved before this change were never published.

## Consequences

- Old logs reproduce only with their `model_version`. Any behavior change must increase it.
- Moving to a packaged distribution later requires deciding where data files are installed.
