# Architecture

Status: the lightweight backend, evaluator, and sample agents exist and are tested. The Unreal
backend does not exist yet.

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
              Lightweight model (python/, working)
              Unreal Engine     (unreal/, planned)
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
| `schemas/` | Messages, logs, scenario, terrain, rover, and plan contracts | Draft v0 |
| `scenarios/`, `rovers/` | Declarative missions, terrain, faults, and rover parameters | Practice set |
| `python/` | Mission core, agents, evaluator, bridge, 2D preview | Working; see [models](lightweight-models.md) |
| `unreal/` | Terrain, physics, rendering, manual driving | Not started; see [plan](unreal-production-plan.md) |
| `scripts/` | Repository checks and preview capture | Working |

The 2D preview is a development tool. It reads the same logs and scenario files as other tools, and
nothing depends on it. It is not an early version of the Unreal renderer.

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

## Python to Unreal transport (proposed)

A loopback TCP bridge carrying JSON Lines that match `schemas/`; see
[unreal-integration.md](unreal-integration.md) and ADR 0005. Unreal MCP is not a
candidate for this runtime role: it is an editor tool, runs serially on the game
thread, has no authentication, and is experimental. Deterministic stepping is a
later requirement for agents and competitions.

## Vertical slice boundary

The next phase is [vertical-slice-plan.md](vertical-slice-plan.md): terrain, one
six-wheeled rover, keyboard and Python driving through the same input path, camera
switching, logs, and replay. No agents, remote networking, or competition services.

## Deliberately excluded

Microservices, a backend plugin framework, and online competition infrastructure.
Each will be designed when a concrete feature needs it.
