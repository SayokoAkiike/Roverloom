# Architecture

Status: initial design. Only the data contracts and their tests exist today.

## Goals

- Run the same mission and evaluation on a lightweight simulator and on
  high-fidelity Unreal Engine.
- Keep research and evaluation code in Python, free of any engine dependency.
- Stay a single repository with few moving parts until real needs say otherwise.

## Overview

```text
             schemas/  (versioned JSON Schema contract)
                 |                     |
      scenarios/ |                     | Action / Observation
      mission +  v                     v
      faults  +---------+        +-----------+
              | Backend | <----> |   Agent   |  python/ or human driver
              +---------+        +-----------+
              Lightweight sim (planned, Python)
              Unreal Engine   (planned, unreal/)
                   |
                   | Telemetry (JSON Lines)
                   v
              +-----------+
              | Evaluator |  python/, needs only scenario + telemetry
              +-----------+
```

## Components

| Path | Responsibility | State |
| --- | --- | --- |
| `schemas/` | Action, Observation, Telemetry, Mission, Scenario | Draft v0 |
| `scenarios/` | Declarative missions, environment, and faults | One example |
| `python/` | Agent SDK, planners, lightweight simulator, evaluator | Contract tests only |
| `unreal/` | Terrain, physics, rendering, manual driving | Not started |
| `scripts/` | Automation and repository checks | Hygiene check |

## The shared contract

A backend is any program that loads a scenario, accepts Actions, emits
Observations, and writes Telemetry. Three rules keep backends interchangeable:

1. **Evaluation reads files, not simulators.** The evaluator takes a scenario
   and a telemetry log. A lightweight run and an Unreal run are scored by the
   same code, and a result can be re-scored later.
2. **Fidelity differences are declared.** Terrain is referenced by a `terrain_id`
   that each backend maps to its own representation, such as a heightmap or an
   Unreal level. Results are only comparable within the same scenario version
   and backend; competition rules should state which backend is authoritative.
3. **Agents do not see ground truth by accident.** Observation is what a rover
   can sense. Telemetry is ground truth for evaluation. Faults are in the
   scenario, and an agent must not receive them unless a sensor would reveal them.

### Conventions

- SI units, stated in field names (`_m`, `_s`, `_mps`, `_radps`).
- Site frame is right-handed: +X east, +Y north, +Z up. Quaternions are `[x, y, z, w]`.
- Unreal uses left-handed centimeters. Conversion happens only inside `unreal/`:
  `UE.X = 100 * x`, `UE.Y = -100 * y`, `UE.Z = 100 * z`. Rotations need the
  matching handedness conversion and must be covered by tests when implemented.
- Each document carries `schema_version`. Breaking changes increase it.

## Agent to Unreal transport (undecided)

Decide this when the first agent drives an Unreal rover, not before. Requirements:
deterministic stepping, and the same message schemas as the lightweight backend.
Unreal MCP is not a candidate for this runtime role: it is an editor tool, runs
serially on the game thread, has no authentication, and is experimental.

## Vertical slice boundary

The next phase needs only `unreal/`: terrain, a six-wheeled rover, manual control,
and if cheap, a telemetry log conforming to the schema. No networking, agents, or
competition services.

## Deliberately excluded

Microservices, a backend plugin framework, and online competition infrastructure.
Each will be designed when a concrete feature needs it.
