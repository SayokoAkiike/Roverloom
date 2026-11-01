# Rover Builder

Compiles a rover design into simulator parameters. Rules are in
[rover_builder.py](../python/src/roverloom/rover_builder.py), version `builder-0.1`.
**These are simplified game rules, not validated wheel, soil, or power models.**

Standard designs (from `uv run roverloom rover`):

| | `scout_4w` | `pathfinder_6w` | `hauler_8w` |
| --- | --- | --- | --- |
| Wheels | 4 | 6 | 8 |
| Mass (kg) | 389.7 | 853.5 | 1328.4 |
| Cost | 27.6 | 58.6 | 84.1 |
| Speed limit (m/s) | 0.40 | 0.50 | 0.60 |
| Climb limit (slope) | 0.62 | 0.54 | 0.45 |
| Soil slip scale | 1.00 | 0.88 | 0.68 |
| Idle power (W) | 211 | 261 | 279 |
| Power | Solar, 180 W nominal | Solar, 360 W nominal | RTG, 90 W |
| Range sensor | 10 m, 7 beams | 12 m, 9 beams | 18 m, 11 beams |
| Control period (s) | 1.0 | 0.5 | 0.5 |
| Sample arm | No | Yes | Yes |

The legacy `rovers/standard_6w.json` is plain parameters, and still works.

See the [Custom Rover Tutorial](tutorials/custom-rover.md) and
[measured comparison](benchmark-reproduction.md#measured-results).

## Known limits

- The score ignores cost, so a more expensive rover tends to win.
- Solar output has no day and night cycle.
- Wheel count affects only aggregated values. No wheel-level dynamics exist.
- Plausibility checks are coarse, and a design can pass them and still be unrealistic.
