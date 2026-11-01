# 0002: Backend-neutral contract and file-based evaluation

Status: Accepted (2026-11-02)

## Context

The same missions and scoring must work on a lightweight simulator without Unreal and
on a future high-fidelity Unreal simulator.

## Decision

- Define Action, Observation, Telemetry, Mission, and Scenario as versioned JSON Schema.
- Use JSON files for scenarios and JSON Lines for telemetry.
- The evaluator takes only a scenario and a telemetry log, and imports no backend code.
- Use SI units in a right-handed frame, and convert only at the Unreal boundary.

## Alternatives

- Protobuf or FlatBuffers: stronger typing and speed, but add a toolchain before any
  performance need exists. Could be added later as a transport encoding of the same
  model.
- Scoring inside each backend: rules would drift between implementations.

## Consequences

- Scores can be recomputed and audited from logs.
- Each backend must map a `terrain_id` to its own terrain. Physics differences remain,
  so results compare only within a backend unless rules say otherwise.
