# 0008: Rover tasks and typed skills; plans are data, never code

Status: Accepted (2026-11-02)

## Context

Science requires actions other than driving, and CaP-style agents need a safe way to act. Executing
generated code in the same process would give it the machine.

## Decision

- `Action` gains an optional `task`, checked on the rover by `ScienceSystem`, which is the only place
  holding true values.
- Skills are a fixed list with published inputs, preconditions, failures, timeouts, and resource notes.
- Model output is parsed as one JSON object, and validated against that list. It is never evaluated.
- Agents run on the same path as everything else, so skills cannot bypass rover checks.

## Consequences

Agents express less than generated programs could, until a real sandbox exists. Real models are
optional, and none is tested. This supersedes the plan format's role for mission work, while
`skill-plan` remains for simple scripts.
