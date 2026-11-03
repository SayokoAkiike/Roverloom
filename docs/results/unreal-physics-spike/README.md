# Unreal physics spike (Step 5a)

An independent experiment with Chaos rigid bodies in UE 5.8.4 on the M4 Mac. **It does not feed the Python Mission
Core**, which remains the reference for science evaluation and competitions. No record here is a contract log, and none
is scored. Whether Unreal later becomes a backend with its own authority (option X in the design) is not decided.

Results are rigid-body approximations with simplified contact. At best they are plausible for game use. They are not
validated against rover data or terramechanics.

## Criteria, fixed before the gated runs

This section was committed before the first gated run, and must not change after results exist. The thresholds are in
[`scripts/physics_spike.py`](../../../scripts/physics_spike.py).

| Test | Run | Pass |
| --- | --- | --- |
| Drive sign probe | Chassis pinned, ±50 cm/s rim speed | Every wheel spins at ±2 rad/s ±10%, forward positive |
| Free fall | Dropped from 5 m | Vertical acceleration from 0.1 to 0.6 s is −371 cm/s² ±1%, with no wheel touching |
| Static | 15 s at rest on flat ground | Body height range < 0.5 cm over 10–15 s; wheel centers sink ≤ 1 cm |
| Straight | 50 cm/s step after 3 s | Reaches 47.5 cm/s; peak ≤ 55 cm/s; mean over 13–23 s within ±5% |
| Turn | 28.178 °/s yaw rate step after 3 s, no forward speed | Measured yaw rate over 13–23 s has the commanded sign, within ±10% |
| Time step | Straight and turn at 60 and 120 Hz | End position along X, and total yaw, differ by < 5% |
| Stability | 600 s of random commands, seed 42, with 10 cm blocks | Completes, speed ≤ 200 cm/s, wheel centers ≥ 20 cm, tilt ≤ 60° |

**R0 passes only if every row passes.** R1 starts only after R0 passes.

Reported without a threshold:

- **Slope**, 5°, 10°, 15°, 20°: holds if drift over 5–10 s is under 0.5 cm/s; climbs if mean speed over 20–30 s is
  at least 25 cm/s. Slip is recorded.
- **Obstacle**, 10, 25, 50 cm steps: climbed if every wheel ends on top and tilt stays below 45°. R1 is judged later at
  25 cm. R0 has no suspension, so its result is only a baseline.
- **Repeatability**: five runs each with `-Deterministic -FPS=60` and in real time. The spread of the end pose is
  reported. Zero spread is not assumed.
- **Performance**: 60 s of driving in real time at 1280 × 720, with `r.VSync 0` requested. Frame time percentiles,
  peak resident memory, and minimum free memory.
- **Axle load**: Chaos's joint force output read from 44 to 3161 at rest before the gated runs, against a weight near
  283,000 kg cm/s². It is recorded, and not judged, because it is not usable as a measurement here.

## Setup

| Item | Value |
| --- | --- |
| Engine | UE 5.8.4 Launcher build, `UnrealEditor -game` with the Development editor target |
| Machine | Apple M4 Mac (Mac16,10), 16 GB, macOS 27.0.1 |
| Map | `/Engine/Maps/Entry`, with everything spawned by C++ from `/Engine/BasicShapes`. No project assets |
| Gravity | −371 cm/s², set on the world at run time. Project settings unchanged |
| Rover | `pathfinder_6w` values compiled at `e5a48f1`: 853.5 kg, wheel radius 25 cm, wheel centers at X ±97.6 and 0 cm, Y ±103.7 cm |
| Assumptions | Wheels 15 kg each; body box 200 × 150 × 40 cm, 55 cm above ground; friction 0.6 on every surface; restitution 0; damping 0 |
| Wheels | Spheres of radius 25 cm. Wheel width is not represented |
| Joints | One joint per wheel. Twist free; other axes locked. Twist velocity drive in force mode, damping 1e7, torque limit 1e6 kg cm²/s² (100 N m) |
| Drive | Skid steering. Rim speed `v ± yaw rate × 103.7 cm`, wheel spin = rim speed ÷ 25 cm. The drive target is in revolutions per second; its sign was measured by the probe |
| Sleep | Every body is woken on each frame, because a new drive target does not wake a sleeping body |
| Time | `-UseFixedTimeStep -FPS=60` unless stated. Physics steps once per frame. Time starts when the joints exist |

Every run's record is in `unreal/Saved/PhysicsSpike/<batch>/`, which Git ignores: a CSV per frame, the run's settings,
the engine log, and the runner's memory, crash, and port checks in `runs.jsonl`.

## Failures found before the gated runs

1. The joints were created before Chaos had created the bodies. All six joints failed silently, and the body and wheels
   fell separately. Joints are now made on the first frame on which every body exists.
2. Bodies fell asleep, and a new drive target did not wake them, so no wheel turned.
3. With the drive sign assumed positive, the probe turned every wheel backward at exactly the commanded speed.
4. The joint force output was unusable, as described above.

## Results

Not yet run.
