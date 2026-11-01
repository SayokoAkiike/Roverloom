# Custom Mission Tutorial

1. Create `scenarios/practice/<scenario_id>.json`, following
   [science_campaign.json](../../scenarios/practice/science_campaign.json) and
   [scenario.schema.json](../../schemas/scenario.schema.json).
2. Check it: `uv run roverloom validate <scenario_id>`.
3. Try it: `uv run roverloom run --scenario <scenario_id> --agent mission-planner`, then `uv run roverloom play`.

Validation does not prove a mission can be solved, so run at least one agent through it.

## Mission types

Use `objectives` for ordered waypoints, and `science` for a campaign. Both may be combined.

```json
"science": {
  "targets": [
    { "id": "ridge", "position_m": [50, 18, 0], "radius_m": 4,
      "prior_value": 4, "true_value": 7, "inspect_s": 20, "collect_s": 60 }
  ],
  "base": { "position_m": [0, 0, 0], "radius_m": 6, "required": true },
  "data_windows": { "period_s": 300, "open_s": 100, "offset_s": 40 },
  "transmit_s_per_item": 6,
  "success_value": 10
}
```

- `prior_value` is public. `true_value` is hidden until inspected, so that estimates can mislead.
- Inspecting stores 30% of a site's value as data, and collecting stores 70%. **Only sent data scores.**
- `data_windows` are ground passes for science data. Commands use the separate command link.
- The mission succeeds when the agent ends it with enough sent value, and at base if required.
- Values are game points, not a measure of real science return.

## Terrain

Terrain files follow [terrain.schema.json](../../schemas/terrain.schema.json). `source.note` must say
truthfully where it comes from. Put `keep_clear` circles around start and sites when generating rocks.

## Practice and evaluation

| | Practice | Evaluation |
| --- | --- | --- |
| Location | `scenarios/practice/` | Outside this repository, or `scenarios/private/` (ignored) |
| `tier` | `practice` | `evaluation` |
| Seeds | Public | Private |

A private scenario loads by path, and its terrain is looked for in a `terrains/` folder beside it.
Never commit evaluation scenarios, even temporarily, because history keeps them. Give each public
scenario a `version`, and increase it when behavior changes.
