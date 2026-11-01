# Adding a rover

Rovers are data, so a new one needs no code in the lightweight backend.

1. Copy [rovers/standard_6w.json](../rovers/standard_6w.json) to `rovers/<rover_id>.json`, and change
   `rover_id`. See [rover.schema.json](../schemas/rover.schema.json).
2. Set `"rover_id": "<rover_id>"` in a scenario.
3. Check it: `uv run roverloom validate <scenario_id>`, then run a mission.

Agents learn speed limits, size, and sensor range through `MissionBrief`, so they should adapt
without changes.

## Limits today

- Schema version 0 assumes exactly six wheels, named in `common.schema.json`.
- The lightweight backend uses wheel radius for documentation only, and it approximates the body as
  a circle. Link geometry and suspension do not exist in this model.
- The range sensor is one scanning plane, defined by bearings and maximum range.

## Future extension

These additions are planned with the Unreal rover, in this order:

1. Add suspension geometry, mass distribution, and sensor mounts as optional fields.
2. Allow other wheel counts, by defining wheels in the rover file instead of a fixed list. This is a
   breaking change for `wheel_id`, and needs a new `schema_version`.
3. Add validation of plausible values, such as center of mass against the support polygon.

For competitions, each custom rover would need limits on budget, mass, and power, so that better
parameters do not simply win. That design has not been done. The visual mesh should remain
separate from physical parameters. See [unreal-production-plan.md](unreal-production-plan.md).

Do not copy real vehicles' proprietary designs or names without checking their terms.
