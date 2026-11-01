# Lightweight models

Model version `kinematic-0.1`. **All of these are unvalidated approximations for games and
early autonomy research.** No parameter has been fitted to, or compared with, real rover data.
Do not cite these results as physical predictions.

The purpose of this backend is fast, reproducible mission logic. Physics fidelity is left to
future work.

| Model | What it does | What it omits |
| --- | --- | --- |
| Motion | Velocity and yaw-rate limits with linear ramps; unicycle kinematics at 10 Hz | Dynamics, suspension, tipping, wheel-level forces |
| Terrain | Heightfield; slope changes speed, slip, and power; heading only | Pitch and roll in pose, tilt limits |
| Slip | `soil + factor × abs(slope) + noise`, clamped | Terramechanics, sinkage, slip-dependent traction |
| Wheel failure | Scales speed and turn capacity, adds yaw bias toward the failed side | Dragging forces, wheel geometry |
| Collision | Rocks and map edges stop the rover; turning stays possible | Climbing over rocks, damage |
| Power | Idle + `m g (Crr + slope) v / efficiency` + turning | Solar, thermal, battery chemistry; no regeneration |
| Sensing | Gaussian noise on pose, yaw, speed, and ranges; ideal rays against circles | Dust, occlusion by terrain, drift, cameras |
| Communications | Fixed latency, independent random loss, blackouts | Bandwidth, jitter, orbital windows |

Rover values in `rovers/standard_6w.json` are game values. The 0.5 m/s top speed is
deliberately much faster than real planetary rovers, to keep missions short.

## Timing

Simulation step 0.1 s. Observations are produced every 0.5 s. Commands take the configured
latency each way, and a command older than 2 s is replaced with a stop.

## Reproducibility

Each subsystem has its own random stream derived from the seed, and fault schedules are drawn
before the mission. Therefore:

- Identical inputs give byte-identical logs on the same platform and Python version.
- Every agent faces the same faults for a given seed.
- Results across operating systems may differ in the last digits, as `math` functions can round
  differently. Byte equality across platforms is not claimed or tested.

Runs through the bridge repeat with each other, but they can differ from in-process runs
because messages are rounded to six decimals.

## Scoring

`score-0.1`, out of 100, implemented in `roverloom.evaluate`:

- 60 × fraction of targets reached.
- On success only: up to 20 for remaining time, and up to 20 for remaining energy.
- Minus 2 per collision event, with a floor of 0.

A fault counts as recovered when the rover travels 1 m after it. Permanent faults are measured
from their start, and temporary ones from their end. This is a simple proxy: traveling is not
the same as making progress toward the target.

## Measured baseline results

Measured on 2026-11-02 at model `kinematic-0.1`, on a Ryzen AI 5 340 laptop, ten seeds per
row. These describe sample agents on these practice scenarios only.

| Scenario | Agent | Success | Mean score | Mean time on success (s) | Mean collisions | Fault recovery |
| --- | --- | --- | --- | --- | --- | --- |
| `demo_traverse` | stop | 0% | 0.0 | - | 0.0 | 0% |
| `demo_traverse` | waypoint | 0% | 9.0 | - | 5.5 | 35% |
| `demo_traverse` | reactive | 60% | 57.3 | 862 | 1.3 | 100% |
| `demo_traverse` | replanner | 100% | 83.5 | 702 | 0.0 | 100% |
| `boulder_gap` | stop | 0% | 0.0 | - | 0.0 | - |
| `boulder_gap` | waypoint | 0% | 0.0 | - | 2.5 | - |
| `boulder_gap` | reactive | 90% | 76.4 | 387 | 0.0 | - |
| `boulder_gap` | replanner | 100% | 79.0 | 299 | 4.5 | - |
| `example_reach_position` | waypoint | 100% | 91.2 | 220 | 0.0 | 100% |
| `example_reach_position` | replanner | 100% | 91.2 | 220 | 0.0 | 100% |

Command: `uv run roverloom compare --scenarios demo_traverse,boulder_gap,example_reach_position --agents stop,waypoint,reactive,replanner --seeds 1,2,3,4,5,6,7,8,9,10`.

Benchmark from `uv run roverloom benchmark`, single process, without file logging:

| Agent | Steps per second | Multiple of real time |
| --- | --- | --- |
| stop | 49,000 | 4,900× |
| waypoint | 40,000 | 4,000× |
| reactive | 37,500 | 3,750× |
| replanner | 8,600 | 860× |

Writing and hashing logs takes additional time. Full schema validation is the slowest part of
reading a run, and is skipped only for runs just written by the same process.

The numbers vary by machine and load. Rerun the commands to reproduce them.
