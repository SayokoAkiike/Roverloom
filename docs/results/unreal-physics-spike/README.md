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

## Results: R0 attempt 1, 2026-11-03

**R0 failed.** R1 was not started. Batch `r0-20261103`, at commit `84471d7`, 26 runs.

| Test | Measured | Result |
| --- | --- | --- |
| Drive sign probe | +2.0003 and −2.0003 rad/s for ±2 | Pass |
| Free fall | −371.0001 cm/s², no wheel touching | Pass |
| Static | Height range 0.0000 cm; lowest wheel center 24.9992 cm | Pass |
| Straight, 60 Hz | Peak 0.377 cm/s, mean 0.187 cm/s, for 50 cm/s commanded | **Fail** |
| Turn, 60 Hz | Yaw rate −0.0000 °/s, for 28.178 °/s commanded | **Fail** |
| Time step | End X differs by 50%; total yaw by 75% | **Fail** |
| Stability | 600 s completed, speed ≤ 12.4 cm/s, wheel centers ≥ 24.996 cm, tilt ≤ 0.003° | Pass, but not meaningful: the rover barely moved |

Reported without a threshold:

| Item | Measured |
| --- | --- |
| Slope, holding with zero drive target | Slid downhill at 157, 354, 548, and 738 cm/s at 5°, 10°, 15°, and 20°; wheels rolled with the motion |
| Slope, climbing | No angle climbed. Every rover moved downhill |
| Obstacle | No step climbed. The rover moved 11.5 cm in 40 s and never reached the step at 300 cm |
| Repeatability, `-Deterministic` | Five identical end poses, to the precision recorded. The rover moved only 5.8 cm, so this is weak evidence |
| Repeatability, real time | End X 3.089 to 3.101 cm, a range of 0.012 cm |
| Performance, real time | 111.7 FPS mean; frame time p50 8.9 ms, p95 10.2 ms, p99 11.3 ms, max 24.5 ms; 6,703 frames. `r.VSync = "0"` was applied. The scene is trivial, so this says nothing about Mars terrain |

Runner checks over all 26 runs: every exit code 0, no new crash report, no forced stop, peak resident memory at most
2,219 MB, free memory at least 41%, swap 3,429 MB before and 3,421 MB after. Every run listened on `*:1985`. 15 Python
errors from the `EditorToolset` plugin's `init_unreal.py` appear in each `-game` log, and did not stop a run.

### Cause, from diagnostic runs that are not gated

The torque limit was set as if it were 100 N m, and was far too low in effect. Chaos converts the limit to a position
impulse of `limit × dt²` (`PBDJointCachedSolverGaussSeidel.cpp`, `FAxisConstraintDatas::SetMaxForce`).
Batch `diag-torque-20261103`, straight driving, with only the limit changed:

| Limit | 60 Hz mean speed | 120 Hz mean speed |
| --- | --- | --- |
| 1e6 (the R0 value) | 0.187 cm/s | 0.094 cm/s |
| 6e7 | 49.990 cm/s, 95% in 1.30 s, slip 0.000 | 49.992 cm/s, 95% in 1.28 s |
| 0 (no limit) | Identical to 6e7 | Identical to 6e7 |

At 6e7 the limit no longer binds. At 10° and 6e7, the rover climbed at 50.5 cm/s, but still slid downhill at 35 cm/s
while holding a zero drive target. That remains unexplained. The exact relation between the setting and the torque
delivered is not measured.

These runs used a command-line override, `-SpikeDriveMaxTorque`, added after the gated runs. They change no
threshold, and are not R0 results.

### Correction to the cause above

The calibration below shows that the conversion is not the cause. With an unloaded wheel, the limit behaves as a torque
in kg cm²/s². The drive stalls on the ground for another reason, described below.

## Torque calibration, 2026-11-03

Batch `calib-20261103`, 54 runs, none gated. Every run exited normally, with no crash report and no forced stop. Free
memory stayed at 41% or more.

**Unit and conversion.** In the source, `SetAngularDriveParams` takes the limit as a torque. Chaos converts it to a
position impulse of `limit × dt²`, and checks the drive's accumulated impulse against it in both its position and
velocity passes. Velocity drive torque is `1.5 × damping × speed error`, where 1.5 is
`p.Chaos.JointConstraint.AngularDriveDampingScale`.

**Measured on a free wheel.** The chassis is pinned and the wheel is held at 0 or 2 rad/s. An opposing torque is added
with `AddTorqueInRadians`, rising tenfold every 3 s. The table gives the applied torque at which the wheel first lags
by 0.5 rad/s.

| Limit | 60 Hz, target 0 | 60 Hz, target 2 | 120 Hz, target 0 | 120 Hz, target 2 |
| --- | --- | --- | --- | --- |
| 1e6 | 1.05e6 | 1.05e6 | 1.05e6 | 5.4e5 |
| 3e6 | 3.08e6 | 3.08e6 | 3.06e6 | 5.4e5 |
| 1e7 and above, or none | 4.1e6 | 4.5e6 | 7.0e6 | 5.4e5 |

- Below the limit, lag grows with torque at 1.48e7 to 1.50e7 per rad/s, which matches 1.5 × 1e7 from the source.
- At 1e6 and 3e6, the wheel breaks away near the limit, at both rates. **On a free wheel, the limit is a torque in
  kg cm²/s², so 1e6 is 100 N m.**
- From 1e7 up, the damping law, not the limit, decides when the wheel lags 0.5 rad/s.
- **Unexplained:** at 120 Hz with a 2 rad/s target, every limit broke away at 5.4e5, which is below the limit and below
  the damping law. It did not happen at 60 Hz.

**Measured on the ground.** Straight driving, 50 cm/s commanded:

| Limit | 60 Hz | 120 Hz |
| --- | --- | --- |
| 1e6 | 0.19 cm/s, stalled | 0.09 cm/s, stalled |
| 3e6 | 49.99 cm/s, initial acceleration 14.0 cm/s² | 0.28 cm/s, stalled |
| 1e7 | 49.99 cm/s, 41.5 cm/s² | 49.99 cm/s, 42.3 cm/s² |
| 3e7, 6e7, 1e8, none | 49.99 cm/s, 57.9 cm/s², identical | 49.99 cm/s, 58.1 cm/s², identical |

Rolling the rover needs little torque. The torque implied by the measured acceleration is about 0.05e6 per wheel at 3e6,
and about 0.15e6 at 1e7. These are **estimates**, from the rover's acceleration and an assumed solid-sphere wheel inertia.
So on the ground, most of the drive's torque is lost. The loss grows as the time step shrinks. In a stall, speed is
roughly proportional to `limit × dt`. The cause is in the interaction between the joint drive and sphere contact. It is
not identified.

**Not calibrated:** the torque the wheel actually delivers to the ground, the motor's power, and the rolling loss itself.
No measured value can be given in N m for driving on the ground.

### Choice for attempt 2: limit 6e7

From 3e7 up, straight driving and the 10° slope gave identical results with any limit and with none. 6e7 therefore means
**no motor torque limit** in practice. Drive torque is set by damping alone. This is not a model of a real motor. It
cannot represent stalling on a steep slope, and it may let the rover climb what a real motor would not.

## Braking and slopes, 2026-11-03

Three holds are now distinct:

| Hold | What it does |
| --- | --- |
| Zero speed command | The motor's velocity drive targets zero, with the motor's limit |
| Motor hold | The same thing. Attempt 1's slope runs hold this way |
| Explicit brake | The velocity drive targets zero with no limit (`-SpikeHoldMode=brake`). Diagnostic only |

On 10° during the 10 s hold, the rover moved downhill at about 35 cm/s with a limit of 6e7, with the brake, with friction
0.6 or 1.0, and at 60, 120, or 240 Hz. Of that, about 20 cm/s was sliding: the front wheels were held at 0.01 rad/s or
less while the body moved. The rest was rolling: the rear wheels turned at about 0.9 rad/s, despite the brake. At the
damping law, that lag means a braking torque near 1.4e7. About 0.2e6 per wheel should hold the rover. Friction 0 slid at
483 cm/s and friction 0.1 at 210 cm/s, so the friction setting does take effect.

**Unresolved.** A rover with friction well above tan 10° (0.18) should not slide. The cause is not Coulomb friction, the
brake torque, or the time step. It is probably the same contact and drive interaction as on flat ground. Slope holding is
reported without a threshold, and attempt 2 does not change that.

The slope climbing figure in attempt 1's analysis used speed along the body. In the diagnostic run, the rover slid,
turned, rose to a 28° pitch, and drove across the slope rather than up it. From attempt 2, uphill speed, heading, and
sliding versus rolling are also reported. The threshold is unchanged.

## Attempt 2 conditions, fixed before its gated runs

- The same 26 runs, scenarios, and thresholds as attempt 1. The criteria section above is unchanged.
- Drive torque limit 6e7, chosen above. Every other setting is as in Setup.
- New report-only fields: uphill speed, heading, sliding and rolling on slopes, and the spread of end speed, pitch, and
  roll across repeated runs. They judge nothing.
- Records go to `unreal/Saved/PhysicsSpike/r0-attempt2-20261103/`. Attempt 1's records are kept unchanged.
- R1 does not start automatically, even if R0 passes.
