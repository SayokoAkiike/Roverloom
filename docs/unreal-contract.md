# Unreal contract

What an Unreal backend must do so that agents, the evaluator, and Mission Control work unchanged.
**`unreal/` is only a skeleton, and implements nothing here.** Everything here is tested only against the lightweight backend, and a Python
stand-in that works internally in Unreal's units. A real engine may expose gaps.

## Responsibilities

| Area | Python | Unreal | Shared contract |
| --- | --- | --- | --- |
| Mission rules, faults, science, scoring | Reference implementation, and evaluator | Reimplements rules; never scores | `scenario`, `mission`, event names |
| Terrain | Heightfield from parameters | Landscape from a `terrain_id` it maps | `terrain_id`, extent |
| Physics | Kinematic model | Chaos vehicle or custom | Rover limits, telemetry |
| Rendering, cameras | Debug 2D map | Everything visual | None |
| Agents | All of them | None | Action, Observation, MissionBrief |
| Logs | Reads them | Writes them | `telemetry`, `event`, `command_record`, `run_manifest` |
| HUD | Mission Control | Its own | `mission_control_state` |

Unreal's physics and rendering are its own. Results are never comparable across backends, and a run
states its backend in the manifest.

## Frames, units, rotations

Implemented in [frames.py](../python/src/roverloom/frames.py). A C++ version must reproduce
[frame_vectors.json](../schemas/conformance/frame_vectors.json).

| Quantity | Contract (site frame) | Unreal | NED tools |
| --- | --- | --- | --- |
| Handedness | Right-handed | Left-handed | Right-handed |
| Axes | +X east, +Y north, +Z up | +X forward, +Y right, +Z up | +X north, +Y east, +Z down |
| Length | meters | centimeters | meters |
| Position | `(x, y, z)` | `(100x, -100y, 100z)` | `(y, x, -z)` |
| Velocity | m/s, same axes as position | cm/s, same conversion | same conversion |
| Quaternion | `[x, y, z, w]`, body to site | `(-x, y, -z, w)` | `q_en * q * conj(q_bf)` |
| Body axes | FLU: forward, left, up | Forward, right, up | FRD: forward, right, down |
| Yaw | radians, counterclockwise from east | degrees, `FRotator.Yaw = -deg(yaw)` | heading `= pi/2 - yaw`, clockwise from north |
| Yaw rate | rad/s, positive turns left | deg/s, `-deg(rate)` | - |
| Angular velocity | rad/s, axial vector | `(-wx, wy, -wz)` | - |

Mistakes this contract is meant to catch, each with a test:

| Mistake | Caught by |
| --- | --- |
| Forgetting to flip Y | Golden vectors; `check_run_contract` (motion disagrees with velocity) |
| Forgetting to flip yaw rate | Stand-in mission fails; yaw check in `check_run_contract` |
| Velocity left in cm/s | `check_run_contract` |
| Degrees sent as radians | Golden vectors |
| Quaternion order `wxyz` | Unit test on `Pose`, and the golden vectors |
| Treating a mirrored rotation like a position | Random rotation property tests |

`FTransform` and `FQuat` conversions happen in one file only, at the boundary. No other Unreal code
sees contract units, and no Python code sees Unreal units.

## Time

- The simulation advances in fixed steps, default 0.1 s. `time_s = step * sim_step_s`, derived from a
  step count, so that floating point error cannot accumulate.
- `Observation.time_s` is when the data was sensed. It reaches the agent later, by the link delay.
- A command applies when it arrives. With one-way delay `L`, the earliest command caused by data from
  `t` applies at `t + 2L`. `command_record.time_s` is its arrival time.
- **Lockstep** (lightweight, and Unreal's goal for competitions): the simulator waits for each reply, so
  runs reproduce. Physics needs a fixed substep, which is not yet proven in Unreal.
- **Real time** (Unreal at first): the simulator never waits. Commands apply on arrival, and runs do not
  reproduce. Such logs must not be used for rankings.

## Communications

Scenario `comms` sets one-way `latency_s` and `loss_probability`, drawn from a stream of its own. Faults
are applied by the simulator:

| Fault | Effect at the boundary |
| --- | --- |
| `comm_blackout` | Messages sent or arriving during it are lost, in both directions |
| Loss | Each message is dropped independently, using the seeded stream |
| `sensor_dropout` | `range_m` is `null` |
| `sensor_noise_burst` | Noise grows; the message format does not change |

Data windows for science are a separate link. See `mission.science.data_windows`.

## Bridge protocol, version 1

Loopback TCP, UTF-8 JSON Lines, 1 MiB per line. Each line is `{"type": ..., "body": ...}`. See the
[recorded transcript](../schemas/conformance/bridge_transcript.jsonl).

| Type | Direction | Body |
| --- | --- | --- |
| `start` | Simulator to agent | `{"protocol_version": 1, "seed": n, "brief": MissionBrief}` |
| `observation` | Simulator to agent | Observation |
| `action` | Agent to simulator | Action |
| `end` | Simulator to agent | `{}` |

The simulator listens and the agent connects. A client refuses another protocol version.

## Safety on disconnection

[`RealtimeCommandLink`](../python/src/roverloom/bridge.py) is the reference for Unreal's receiver:

1. Sockets stay off the game thread. The newest command goes in a slot, and older ones are dropped.
2. Bad input, or a lost connection, drops the client and raises nothing into the simulation. A pending
   command is discarded with it.
3. Stopping is not the link's job. `CommandRouter`'s watchdog sends zero velocity when no command has
   been accepted for 2 s of simulation time, whatever the cause.
4. A new client can connect afterward. A handover always starts from a stop.
5. In lockstep, a lost client ends the mission as `agent_error`.

## Common rover definition

A design compiles to [`rover`](../schemas/rover.schema.json) parameters, including `geometry`: wheel
positions in the FLU body frame, with the origin on the ground. Unreal builds from these numbers. It
may add meshes and physical detail, but must honor the declared limits. Telemetry fields refer to
`wheels` by these IDs. Legacy rovers without `geometry` are not usable in Unreal.

## Conformance

`roverloom.conformance.check_run_contract(run_dir)` works on any backend's logs. It checks schemas,
hashes, ordering, step timing, unit quaternions, battery range, and whether position, velocity, heading,
and yaw rate agree. [test_unreal_contract.py](../python/tests/test_unreal_contract.py) shows that it
accepts both the lightweight backend and the stand-in, and that deliberately wrong units or frames fail.

## Not settled

- Whether Chaos can be made to step deterministically in lockstep.
- Real wheel-level telemetry. Today `failed_wheels` is the only per-wheel field.
- Mapping `terrain_id` to Landscape, and how a Mars elevation tile is scaled.
- Whether the real bridge's threading holds at 10 Hz in a packaged build.
