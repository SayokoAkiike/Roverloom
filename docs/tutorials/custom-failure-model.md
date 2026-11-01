# Custom Failure Model Tutorial

## Use existing events

```json
"faults": [
  { "type": "dust_storm", "start_time_s": 500, "duration_s": 120, "severity": 0.6, "category": "mars_inspired" }
],
"fault_generators": [
  { "type": "comm_blackout", "rate_per_hour": 4, "duration_s": 15, "max_count": 2, "category": "mars_inspired" }
]
```

| Type | Effect in this model |
| --- | --- |
| `wheel_drive_failure` | Permanent: less speed and turning, and yaw bias. Missing wheels map to the nearest on that side |
| `comm_blackout` | Commands and observations are lost; interrupts transmission |
| `sensor_dropout` | No range returns |
| `sensor_noise_burst` | Noise grows by up to 11x with severity |
| `dust_storm` | Range falls by up to 70%, and solar output by up to 100%, with severity |
| `slip_burst` | Slip rises by up to 0.6 with severity |
| `immobilized` | Wheels turn, but the rover does not move |
| `power_brownout` | Extra load of up to 500 W with severity |

## Label honestly

- `mars_inspired`: a plausible *kind* of event. Timing and size are still game values, not measurements.
- `stress_test`: deliberately artificial.

**Do not describe rates or magnitudes as coming from NASA or any mission unless you cite a source that
says so.** No current value has such a source.

## Add a new model

1. Add its type in `schemas/scenario.schema.json`, for both `fault` and `fault_generators`.
2. Apply it in `MissionSession.step` through `Effects`, or in the sensors. See `_severity(...)`.
3. Keep random draws independent of whether it is active, so other random streams stay aligned.
4. Do not reveal it in `Observation` unless a real sensor would.
5. Test its start, end, effect, and reproducibility. See `tests/test_science_skills.py`.
6. Increase `MODEL_VERSION`, because old logs no longer reproduce, and lock a new benchmark.
7. Describe it in [lightweight-models.md](../lightweight-models.md), and plan how Unreal will model it.
