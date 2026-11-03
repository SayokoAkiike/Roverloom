# Unreal wheel model experiment (Step 5a, phases A and B)

A second, separate experiment after [R0 failed twice](../unreal-physics-spike/README.md). R0's sphere wheels on driven
joints are kept unchanged as a baseline. This experiment replaces sphere contact with a wheel model written in C++.
It never feeds the Python Mission Core, which stays the reference for science evaluation and competitions.

**What this is not.** It is a simple game-style tire model, not a model of Martian regolith. It has no soil
deformation, sinkage, bulldozing, grousers, or slip-dependent traction. Friction is one Coulomb coefficient. Passing its
tests means the code does what its equations say, and that its behavior is plausible for game use. It does not mean
that any rover would behave this way on Mars.

## Physics

Units are Unreal's: cm, kg, s. Forces are kg cm/s², torques kg cm²/s². Every quantity below is per wheel, per physics
step `dt`. The body is one Chaos rigid body. Wheels are not bodies. Their spin is integrated by the model.

1. **Contact.** A ray, or a sphere sweep of the wheel's radius, from the wheel's mount along the body's down axis. The
   hit gives the contact point `p` and normal `n`.
2. **Normal load.** Suspension compression `x` from the hit distance, rate `ẋ` from the mount's velocity.
   `Fz = max(0, k x + c ẋ)`, applied along `n`. `k` gives 5 cm of static compression; `c` gives damping ratio 0.7.
3. **Contact frame.** Forward `f` and lateral `l` are the body's forward and right axes, projected onto the contact
   plane and made orthogonal.
4. **Contact velocity.** The body's velocity at `p`, split into `v_long = v·f` and `v_lat = v·l`. The ground is static.
5. **Slip.** `s = ω R − v_long`, the rim's speed relative to the ground.
6. **Longitudinal force, sticking first.** The force that makes `s` zero at the end of the step, given the wheel's
   inertia `I` and the body's effective mass `m` at `p`:
   - Driving to a target spin `ω*`: `F = m (ω* R − v_long) / dt`, needing motor torque `τ = I (ω* − ω) / dt + F R`.
   - If `|τ|` exceeds the motor's or brake's limit, `τ` is clamped and `F = (s / dt + τ R / I) / (R² / I + 1 / m)`.
   - Coasting: `τ = 0` and the same formula.
7. **Lateral force.** `Fy = −m v_lat / dt`, which stops sideways sliding within a step if friction allows.
8. **Friction circle.** If `√(F² + Fy²) > μ Fz`, both are scaled down to `μ Fz`. The wheel is then slipping or sliding.
   The motor or brake torque is recomputed against the limited force, and clamped again.
9. **Spin.** `ω ← ω + dt (τ − F R) / I`.
10. **Force on the body.** `Fz n + F f + Fy l` at `p`, with `AddForceAtLocation`. Body velocities are never written.

**Effective mass.** `1 / m = (1 / M + (r × d) · I⁻¹ (r × d)) × N`, where `r` is from the center of mass to `p`, `d` is
`f` or `l`, and `N` is the number of wheels in contact. Each wheel solves alone, so dividing by `N` keeps the wheels
together from overcorrecting. This is an approximation. Rotation axes locked on a test rig count as infinite inertia.

**Three holds are distinct.** Zero command: the motor servos to zero spin within its torque limit. Brake: the same
servo with the brake's larger limit. Coast: no torque.

**Update rate.** The model runs in the pre-physics tick. With `-UseFixedTimeStep` and Chaos's default settings, which
have no substepping and a 1/30 s maximum step, there is one physics step per frame, so the model runs once per step.
Forces apply to the next step. The CSV records `dt` on every row.

## Parameters

| Item | Value | Source |
| --- | --- | --- |
| Gravity | −371 cm/s² | Mars, set on the world |
| Wheel radius | 25 cm | `pathfinder_6w` |
| Wheel inertia | 3,750 kg cm², a 15 kg solid sphere | Assumed, as in R0 |
| Suspension rest length | 30 cm from mount to wheel center | Assumed |
| Motor torque limit | 6e5 (60 N m) per wheel | Assumed game value. A real limit, unlike R0 attempt 2 |
| Brake torque limit | 2e6 (200 N m) per wheel | Assumed |
| Friction μ | 0.6 unless a test sets it | Assumed, as in R0 |

**Rig A, single wheel.** A 40 cm box of 142.25 kg, one sixth of `pathfinder_6w`'s mass, on one wheel under its center.
All rotation is locked, so the rig only translates.

**Rig B, two wheels.** A 60 × 150 × 40 cm box of 284.5 kg, one third of the rover's mass, with wheels at Y ±103.7 cm,
the rover's half track. Roll and pitch are locked; yaw is free.

## Tests and pass criteria, fixed before the gated runs

Fixed step at 60 Hz unless stated. Each scenario settles for 2 s first. Every run must also complete with no NaN, speed
under 1,000 cm/s, and every recorded traction within `μ Fz` to a relative 1e-6.

| ID | Rig, setup | Pass |
| --- | --- | --- |
| A1 | A, at rest, ray | Over 4–6 s: mean `Fz` within ±1% of `M g`; compression range < 0.1 cm |
| A1s | A, at rest, sphere sweep | The same |
| A2 | A, drive to 2 rad/s from 2 s, ray | Mean speed over 8–12 s within 50 cm/s ±2%; mean |slip| < 1 cm/s |
| A2s | A2 with sphere sweep | The same |
| A3 | A, μ 0.05, drive to 2 rad/s from 2 s | While slipping (rim faster than body by > 1 cm/s): `F` within ±2% of `μ Fz`; body acceleration within ±5% of `μ g` |
| A4 | A, μ 0.1, drive 2–7 s, brake from 7 s | While sliding locked: spin |ω| < 0.01 rad/s; body deceleration within ±5% of `μ g` |
| A5 | A, μ 0.3, push sideways at 2 μ M g for 2.0–2.5 s | After the push, while sliding: lateral deceleration within ±5% of `μ g`; lateral speed < 0.1 cm/s by 1.5 s after the push |
| A6 | A, 10° slope, μ 0.6, brake | Mean downhill speed over 4–6 s < 0.1 cm/s |
| A7 | A, 10° slope, μ 0.1, brake | Downhill acceleration within ±5% of `g (sin 10° − 0.1 cos 10°)`, 27.9 cm/s² |
| A8 | A2 and A4 at 120 Hz | Time to 95% speed, and stopping distance, within 5% of 60 Hz |
| B1 | B, both wheels to 2 rad/s from 2 s | Mean speed over 8–12 s within 50 cm/s ±2%; mean |yaw rate| < 0.5 °/s |
| B2 | B, spin in place at 28.178 °/s from 2 s | Mean yaw rate over 6–10 s within ±5%, correct sign; mean |lateral slip| < 1 cm/s |
| B3 | B, drive 2–7 s, zero command from 7 s | Speed below 0.5 cm/s within 2 s of the stop command |
| B4 | B, 10° slope, μ 0.6, zero command | Mean downhill speed over 4–6 s < 0.1 cm/s |
| B5 | B1 and B2 at 120 Hz | End position along X, and total yaw, within 2% of 60 Hz |

Recorded on every row: time, `dt`, body pose and velocity, and for each wheel the contact flag, compression, `Fz`, `F`,
`Fy`, `μ Fz`, spin, target spin, motor and brake torque, `v_long`, `v_lat`, slip, and whether friction saturated.

Phase C, six wheels, needs the owner's approval, and its criteria will be fixed separately before it runs. Old R0
results are not rejudged.

## Code

| File | Role |
| --- | --- |
| `unreal/Source/Roverloom/WheelSpike/WheelModel.h`, `.cpp` | The equations above, with no engine world access, so they can be unit tested |
| `unreal/Source/Roverloom/WheelSpike/WheelRig.h`, `.cpp` | One body, contact traces, effective mass, forces, DOF locks |
| `unreal/Source/Roverloom/WheelSpike/WheelSpikeGameMode.h`, `.cpp` | Scenarios and CSV records, like R0's |
| `unreal/Source/Roverloom/WheelSpike/WheelModelTest.cpp` | Unit tests of the equations |
| `scripts/wheel_spike.py` | Plan, runner reuse, and judgment against the criteria above |

## Results

Not yet run.
