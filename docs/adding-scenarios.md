# Adding scenarios and fault models

## Add a scenario

1. Create `scenarios/practice/<scenario_id>.json`. See
   [demo_traverse.json](../scenarios/practice/demo_traverse.json) and
   [scenario.schema.json](../schemas/scenario.schema.json).
2. Use an existing terrain from `scenarios/terrains/`, or add one.
3. Check it: `uv run roverloom validate <scenario_id>`.
4. Try it: `uv run roverloom compare --scenarios <scenario_id>`.

Loading rejects schema violations, and also a start or target that is inside a rock or outside
the map. Validation does not prove that a mission is solvable, so run at least one agent through it.

Practice scenarios are tested automatically. They can be run with `--scenario <path>` too.

## Add a terrain

Terrain files follow [terrain.schema.json](../schemas/terrain.schema.json). `source.note` must say
truthfully where the terrain comes from. List `keep_clear` circles around the start and each
target when generating rocks. Rock and height generation depend only on their own seeds, so the
terrain stays fixed when the scenario seed changes.

## Use faults

Fixed faults go in `faults`. Random faults go in `fault_generators`, and are drawn from the seed
before the mission:

```json
{
  "faults": [{ "type": "wheel_drive_failure", "wheel": "rear_left", "start_time_s": 60 }],
  "fault_generators": [{ "type": "comm_blackout", "rate_per_hour": 6, "duration_s": 10, "max_count": 2 }],
  "comms": { "latency_s": 0.5, "loss_probability": 0.02 },
  "sensors": { "pose_noise_m": 0.15, "yaw_noise_rad": 0.01, "speed_noise_mps": 0.01, "range_noise_m": 0.05 }
}
```

## Add a new fault model

1. Add its type to the `fault` definition and to `fault_generators` in `scenario.schema.json`.
2. Apply it in `roverloom.sim` or `MissionSession._update_faults`. Use `_fault_active(...)` for
   faults with a duration.
3. Keep random draws independent of whether the fault is active, so other streams stay aligned.
4. Do not reveal it in `Observation` unless a real sensor would.
5. Add tests for start, end, its effect, and reproducibility.
6. Increase `MODEL_VERSION`, because old logs will no longer reproduce.
7. Document it in [lightweight-models.md](lightweight-models.md), and plan how Unreal will model it.

## Practice and evaluation scenarios

| | Practice | Evaluation |
| --- | --- | --- |
| Purpose | Learning and development | Hidden test of generalization |
| Location | `scenarios/practice/` in this repository | Outside this repository |
| `tier` | `practice` | `evaluation` |
| Seeds | Public | Private |

- `scenarios/private/` is ignored by Git, for local work only.
- A private scenario can be loaded by path. Its terrain is looked for in a `terrains/` folder beside
  it first, so private terrains can stay private too.
- Evaluation scenarios must never be committed, even temporarily. History keeps them.
- The private set should have the same schema and be similar in difficulty, but with different
  terrain, seeds, and fault timing. Hidden rules that participants cannot anticipate are unfair.
- Publish evaluation scenarios only when a competition phase ends.
