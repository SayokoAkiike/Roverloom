# Custom Rover Tutorial

Rovers are data files, so a new one needs no code. **Every formula is a simplified game rule, not a
validated wheel, soil, or power model.** Rules are in
[rover_builder.py](../../python/src/roverloom/rover_builder.py) and summarized in
[lightweight-models.md](../lightweight-models.md).

## 1. Copy an example

[python/examples/rovers/my_scout.json](../../python/examples/rovers/my_scout.json) is a good start.
Run these from `python/`:

```shell
uv run roverloom rover examples/rovers/my_scout.json
uv run roverloom run --scenario science_sprint --agent mission-planner --rover examples/rovers/my_scout.json
```

## 2. Understand the trade-offs

| Field | Improves | Costs |
| --- | --- | --- |
| `wheels.count`, `width_m` | Lower ground pressure, less slip | Mass, cost, larger body in rock fields |
| `wheels.radius_m` | Higher speed limit | Mass squared with radius |
| `wheels.motor_w` | Speed limit under load, climbing | Mass, cost |
| `battery_wh` | Endurance | Mass, cost |
| `power` | Recharging; solar drops in dust, RTG does not | Mass, cost (RTG is expensive) |
| `sensors.range_*` | Earlier sight of obstacles | Idle power, mass, cost |
| `sensors.pose_grade` | Less pose noise | Cost |
| `compute` | Faster control: 1.0, 0.5, or 0.2 s | Idle power, cost |
| `tools.sample_arm` | Can collect samples, worth 70% of a site | Mass, cost |

## 3. Know the limits

A design is rejected when mass exceeds 1600 kg, cost exceeds 100, ground pressure is too high, the
chassis is under 20% of the mass it carries, or any value is outside its allowed range. Wheel counts
are 4, 6, or 8.

## 4. Record where your design came from

`provenance` is required. Use an SPDX license ID, and name the design and commit you derived from:

```json
{
  "author": "Your name",
  "license": "CC-BY-4.0",
  "derived_from": "scout_4w@1.0.0",
  "derived_from_commit": "80b4a43",
  "source_url": null
}
```

Use only designs whose license allows reuse. There is no public registry yet.

## 5. Compare it

```shell
uv run roverloom league run --league rover_design --add-rover examples/rovers/my_scout.json
```

## Change a standard rover

Increase its `version`, then lock a new benchmark version, because old results are no longer
comparable. See [Benchmark Reproduction](../benchmark-reproduction.md).
