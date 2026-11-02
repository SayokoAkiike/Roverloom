# API Compatibility Policy

Roverloom is pre-alpha with no public release, so anything may change. These rules exist so that changes
are detected and explained. They become commitments at version 1.0.

| Thing | Version | Breaking change means |
| --- | --- | --- |
| JSON contracts in `schemas/` | `schema_version` (0) | Removing or renaming a field, or tightening a rule |
| Simulated behavior | `MODEL_VERSION` | Any change in logs for the same inputs |
| Scoring | `SCORING_VERSION` | Any change in scores for the same logs |
| Rover formulas | `BUILDER_VERSION` | Any change in compiled parameters |
| Standard rover, scenario | Own `version` | Any change in its file |
| Built-in agent | `VERSION` | Changed decisions |
| Benchmark | `version` plus hash pins | Any change in pinned inputs, including core and agent source |
| Bridge protocol | `PROTOCOL_VERSION` (1) | Any change a current client cannot read |
| Coordinate conventions | `conventions` in the manifest, and [golden vectors](../schemas/conformance/frame_vectors.json) | Any change in the vectors |
| Python API | Package version | See below |

## Stable surfaces, for now

Keep compatible where practical, with a deprecation note otherwise:

- `Agent.reset`, `Agent.act`, `Action`, `Observation`, `MissionBrief`
- `SkillCall`, `SKILL_SPECS`, `SkillPlanner`, `LanguageModel`
- The `roverloom` commands in the README
- `telemetry`, `event`, `command_record`, `decision`, `run_manifest`, `mission_control_state`

Other modules are internal. A module's `sim`, `session`, or `Scenario` must not be used by agents.

## Rules

- Additive, optional fields keep `schema_version`. A test confirms the first v0 documents still load.
- A breaking contract change increases `schema_version`, and is recorded in an ADR with a migration path.
- A run records all versions and hashes. `load_run` rejects logs that fail integrity checks.
- `roverloom league verify` detects incompatible changes before results can be mixed.

Old benchmark files are kept in `benchmarks/archive/` as a record. They no longer verify against the code.

## Unreal

Unreal must produce the same log contracts, with its own `model_version` and `backend`. The evaluator and
Mission Control state are shared. Results are never comparable across backends.
