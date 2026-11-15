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
results are not rejudged. A design draft is in [phase-c-design.md](phase-c-design.md); it is not implemented.

## Code

| File | Role |
| --- | --- |
| `unreal/Source/Roverloom/WheelSpike/WheelModel.h`, `.cpp` | The equations above, with no engine world access, so they can be unit tested |
| `unreal/Source/Roverloom/WheelSpike/WheelRig.h`, `.cpp` | One body, contact traces, effective mass, forces, DOF locks |
| `unreal/Source/Roverloom/WheelSpike/WheelSpikeGameMode.h`, `.cpp` | Scenarios and CSV records, like R0's |
| `unreal/Source/Roverloom/WheelSpike/WheelModelTest.cpp` | Unit tests of the equations |
| `scripts/wheel_spike.py` | Plan, runner reuse, and judgment against the criteria above |

## Results: phases A and B, attempt 1, 2026-11-03

**Phase A failed on A6 and phase B on B4, both holding on a slope.** The other 13 tests passed. Phase C was not started.
Batch `wheel-ab-20261103` at commit `89d1269`, 17 runs. Smoke runs `smoke-20261103`, of A1 and B1 only, preceded it.

| Test | Measured | Result |
| --- | --- | --- |
| A1, ray | Load error 0.0000; compression range 0.0000 cm | Pass |
| A1s, sphere sweep | The same | Pass |
| A2, ray | 50.000 cm/s; mean slip 0.000 cm/s; 95% in 0.30 s | Pass |
| A2s, sphere sweep | The same | Pass |
| A3, wheel spin, μ 0.05 | 159 slipping steps, traction 1.000 × μ Fz; acceleration 18.550 cm/s² for 18.55 | Pass |
| A4, locked braking, μ 0.1 | Spin 0.000 rad/s; deceleration 37.100 cm/s² for 37.10; stopped in 33.28 cm | Pass |
| A5, sideways sliding, μ 0.3 | Peak 57.5 cm/s; deceleration 111.300 cm/s² for 111.30; 0.000 cm/s at 4 s | Pass |
| **A6, 10° slope, μ 0.6, brake** | **Creep 1.074 cm/s** | **Fail** |
| A7, 10° slope, μ 0.1, brake | Sliding at 27.887 cm/s² for 27.887 | Pass |
| A8, time step | Time to 95%: 0.0% different; stopping distance: 0.63% | Pass |
| B1, straight | 50.000 cm/s; yaw rate 0.000 °/s; each wheel's load 52,774.75, which is M g / 2 | Pass |
| B2, spin in place | 28.178 °/s for 28.178; lateral slip 0.000 cm/s | Pass |
| B3, stop | Below 0.5 cm/s in 0.53 s | Pass |
| **B4, 10° slope, μ 0.6, zero command** | **Creep 6.222 cm/s** | **Fail** |
| B5, time step | End X 0.08% different; total yaw 0.06% | Pass |

Every run completed, with no NaN, speeds of 168 cm/s or less, and traction never outside the friction circle. Runner
checks over the 17 runs: every exit code 0, no new crash report, no forced stop, peak resident memory at most 2,271 MB,
free memory at least 39%, and swap unchanged at 3,389 MB. Unit tests passed: `Roverloom.WheelSpike.Model`, with R0's two.

### Causes of A6 and B4, from diagnostic runs that are not gated

Batch `diag-hold-20261103`.

1. **Sticking ignores gravity.** The traction solve zeroes the contact velocity at the end of a step, assuming no other
   force. Gravity then adds `g sin θ dt` along the slope during the next step. A6's creep is exactly that:

   | Step | Predicted | Measured |
   | --- | --- | --- |
   | 60 Hz | 1.0737 cm/s | 1.0737 cm/s |
   | 120 Hz | 0.5369 cm/s | 0.5369 cm/s |
   | 240 Hz | 0.2684 cm/s | 0.2684 cm/s |

2. **The effective mass is wrong for wheels that push together.** On rig B, each wheel's share counts the yaw inertia
   term, as if it alone turned the body. When both push the same way, the yaw terms cancel. The share used was 23.9 kg,
   against 142.3 kg needed, so each step removes about a sixth of the creep. Predicted 6.38 cm/s, measured 6.22 cm/s at
   60 Hz, and 3.11 cm/s at 120 Hz.

Both are flaws in this model's design. Neither is a Chaos behavior. Straight driving and turning are unaffected, because
nothing but the wheels pushes the body along the ground there.

### Proposed fix, not applied

- Add the known external acceleration, gravity, to the predicted contact velocity before solving.
- Solve all wheels' traction together, either as one small linear system or with a few Gauss-Seidel passes, instead of
  splitting effective mass.

A second attempt would keep every threshold above, and needs the owner's approval.

## Attempt 2: the fix and its conditions, fixed before its runs

The owner approved both fixes on 2026-11-03, with the same 15 tests and thresholds. Attempt 1's records, diagnostics,
and verdicts above stay as they are. The attempt 1 code is at commit `89d1269`.

### Physics step order, checked in the UE 5.8.4 source

- **No substeps.** `UPhysicsSettings` defaults to `bSubstepping = false` and `bTickPhysicsAsync = false`, with
  `MaxPhysicsDeltaTime` 1/30 s, and this project's config sets none of them. So with `-UseFixedTimeStep` at 60 or
  120 Hz, each frame runs exactly one physics step of the frame's `dt`. Epic's
  [Physics Sub-Stepping page](https://dev.epicgames.com/documentation/en-us/unreal-engine/physics-sub-stepping-in-unreal-engine)
  says that when a frame is substepped N times, a force applied for one frame is applied for N consecutive steps. That
  would break a one-step solve, so substepping stays off. Every CSV row records `dt`.
- **When forces are computed and applied.** The model runs in the game mode's pre-physics tick. It reads the body's
  velocity, which is the result of the previous step, and adds its forces with `AddForceAtLocation`. Chaos turns them
  into acceleration (`AddForce`: `Acceleration += F / M`, in `ParticleHandle.h`), and gravity adds its own
  acceleration in the same step (`FPerParticleGravity::Apply`).
- **How the step integrates.** `FPBDRigidsEvolutionGBF::Integrate` does `V += Acceleration dt` and
  `W += AngularAcceleration dt` from the velocity at the start of the step. Then it moves the body and solves the
  constraints, including the DOF locks. `EndFrame` clears the accelerations after the step.
- **So gravity is not counted twice.** The velocity the model reads does not yet include this step's gravity. The model
  adds `g dt` once to its prediction, and Chaos adds it once to the body. Attempt 1's creep was exactly `g sin θ dt`,
  which agrees with this order.
- **DOF locks are on world axes.** `FBodyInstance::CreateDOFLock` with `SixDOF` uses world X and Y as its axes.

### Changes

1. **Known forces in the prediction.** Before solving traction, the model predicts the body's velocity at the end of
   the step from the forces already known: `v' = v + dt (g + (Σ Fz n + F_ext) / M)` and
   `ω' = ω + dt I⁻¹ Σ r × Fz n`. The prediction includes gravity, every wheel's normal force, and the known external
   push in A5, which the rig now applies itself. Traction then solves against `v' + ω' × r` at each contact.
2. **One joint solve for all contacts.** Each wheel in contact has two rows: longitudinal along `f` and lateral along
   `l`. The coupling between rows a and b is `K_ab = (d_a · d_b) / M + (r_a × d_a) · I⁻¹ (r_b × d_b)`. This uses the
   body's mass, its world inertia tensor, each contact's position, its normal through the contact plane, and the
   rotation axes. `I⁻¹` is the inverse of the world inertia restricted to the free rotation axes, which is zero for
   rig A and `1 / I_zz` about world Z for rig B. No mass is fixed in advance; each wheel's share follows from `K`.
3. **Projected Gauss-Seidel.** Each pass re-solves every wheel against the others' current forces, in order: the
   longitudinal force with the same sticking, servo, and torque-limit rules as attempt 1, then the lateral force, then
   the friction circle `√(F² + Fy²) ≤ μ Fz`. A wheel's motor or brake torque is clamped to its limit at every pass.
   Passes stop when no row changes any contact velocity by 1e-7 cm/s or more, or after 200 passes. Normal forces still
   come only from the suspension, so no ground force is unbounded, and no body velocity is ever written.

### Unit tests, before the runs

`Roverloom.WheelSpike.Model` now steps a small test body in Chaos's order, using the solver as written:

| Case | Checks |
| --- | --- |
| Flat | Rolling at the target needs no traction; load is `k x` |
| Slope, one contact | Braked on 10° at 60, 120, and 240 Hz: contact speed < 1e-6 cm/s after 2 s, traction `M g sin θ`, gravity's `dv` recorded |
| Several contacts | Two wheels with yaw free on 10°: no creep, total traction `M g sin θ`, no yaw. Three uneven contacts: no creep at any contact |
| Turning | Opposite targets give yaw rate `rim / half track` with no body speed |
| Friction saturation | Spin-up at μ 0.3 capped at `μ Fz`; locked slide on 10° at μ 0.1 at `g (sin θ − μ cos θ)`; combined demand on the circle |
| Torque limit | At μ 0.5 the motor's limit binds first, with no slip |
| Time step | A torque-limited start reaches the same speed after 0.5 s at 60 and 120 Hz, within 1% |
| Airborne, coasting | No ground force; no coasting torque |

All passed before the gated runs, with the module's two other tests.

### Runs and counting

- **The same plan as attempt 1.** That is 17 runs: the 13 scenarios at 60 Hz, plus A2, A4, B1, and B2 at 120 Hz.
- **The same 15 tests.** Each of the 13 scenarios is judged on its 60 Hz run. A8 and B5 compare the 120 Hz runs with
  the 60 Hz ones and also need those 120 Hz runs to pass their own scenario's criteria.
- **Phase A** passes if A1–A8 all pass, and **phase B** if B1–B5 all pass.
- **Batch** `wheel-ab-attempt2-20261103`, separate from attempt 1's.
- **The thresholds are the same** as in the table above, with no change.
- **Added report-only records.** These are not part of any pass:
  - Per row: solve passes and convergence. Per wheel: the predicted velocity change from known forces and from
    gravity alone, and the predicted slip and lateral speed at the end of the step.
  - For A6 and B4 over 4–6 s: contact velocity, gravity's `dv`, drive force, end slip, and how far the body moved.
- **The same runner checks apply.** A run stops on a crash report, a forced stop, a nonzero exit, low free memory, or
  divergence.

## Results: phases A and B, attempt 2, 2026-11-03

**All 15 tests passed, so phases A and B pass on attempt 2.** Attempt 1's failures of A6 and B4 stand as recorded above.
Batch `wheel-ab-attempt2-20261103` at commit `ca3f841`, 17 runs, with the conditions fixed in that commit.

| Test | Attempt 1 | Attempt 2 | Result, attempt 2 |
| --- | --- | --- | --- |
| A1, ray | Load error 0.0000 | The same | Pass |
| A1s, sphere sweep | The same | The same | Pass |
| A2, ray | 50.000 cm/s; slip 0.000; 95% in 0.30 s | The same | Pass |
| A2s, sphere sweep | The same | The same | Pass |
| A3, wheel spin, μ 0.05 | 18.550 cm/s² for 18.55 | The same; traction 0.99999962–1.000 × μ Fz | Pass |
| A4, locked braking, μ 0.1 | 37.100 cm/s²; 33.28 cm | The same | Pass |
| A5, sideways sliding, μ 0.3 | 111.300 cm/s²; peak 57.5 cm/s | 111.300 cm/s²; peak 55.65 cm/s | Pass |
| **A6, 10° slope, μ 0.6, brake** | **Creep 1.074 cm/s, fail** | **Mean 0.000 cm/s** | **Pass** |
| A7, 10° slope, μ 0.1, brake | 27.887 cm/s² | 27.887 cm/s² | Pass |
| A8, time step | 0.0% and 0.63% | 0.0% and 0.63% | Pass |
| B1, straight | 50.000 cm/s; yaw 0.000 °/s | The same | Pass |
| B2, spin in place | 28.178 °/s | 28.178 °/s; lateral slip 0.000 cm/s | Pass |
| B3, stop | 0.53 s | 0.32 s | Pass |
| **B4, 10° slope, μ 0.6, zero command** | **Creep 6.222 cm/s, fail** | **Mean 0.000 cm/s** | **Pass** |
| B5, time step | 0.08% and 0.06% | 0.04% and 0.06% | Pass |

**A5 and B3 changed, as the fix predicts.** A5's push is now in the prediction, so the lateral force resists it during
the push, and the peak is lower. B3 stops sooner, because the pair's longitudinal rows now see the body's whole mass.

**Slope holding, A6 and B4, over 4–6 s, from the report-only records:**

| Item | A6 | B4, each wheel |
| --- | --- | --- |
| Contact velocity at the start of each step | 0.000 cm/s | 0.000 cm/s |
| Gravity's change over a step, predicted | −1.0737 cm/s | −1.0737 cm/s |
| All known forces' change over a step | −1.0737 cm/s | −1.0737 cm/s |
| Drive force | 9,164.24 | 9,164.24 each, 18,328.5 together |
| `M g sin θ` for comparison | 9,164.24 | 18,328.5 |
| Predicted slip at the end of the step | 0.000 cm/s | 0.000 cm/s |
| Body position after 2 s | X −12.1686 cm, unchanged to the CSV's 1 µm resolution | The same |
| Solve passes; converged | 2; every step | Up to 24; every step |

The largest speed in A6 and B4 is 0.308 cm/s, at 0.12 s, while the suspension settles. It is vertical, and it
is below 0.01 cm/s after 0.5 s.

**No numerical problem was found.**
- Every run completed with no NaN.
- Speeds were at most 167 cm/s, in A7's slide.
- Traction never left the friction circle.
- The joint solve converged on every step of every run, in at most 24 passes.
- Normal loads stayed within 0.9966–1.0154 of static.
- Torques stayed within their limits: at most 6.0e5 for the motor and 1.03e6 for the brake.

**Runner checks over the 17 runs:**
- Every exit code was 0, with no new crash report and no forced stop.
- Peak resident memory was at most 2,291 MB, and free memory never fell below 42%.
- Swap stayed at 3,367 MB.
- Port 1985 still had the same listener.

**Repeatability, not gated.** Batch `repro-attempt2-20261103` repeated A5, A6, B2, and B4 with the same flags. Each
CSV is byte-identical to attempt 2's.

### Model limits that remain

- The friction circle scales the demanded force. For combined sliding, it does not point the force against the
  sliding velocity. A5 and A7 slide in one direction, so they do not test this.
- With more contacts than the body has freedoms, how traction splits between wheels is not unique. Gauss-Seidel picks
  one split, and that split depends on the wheel order. Totals and contact velocities are meaningful; single-wheel
  forces in a hold are not.
- Normal force is an explicit spring-damper, not part of the joint solve. A stiffer spring or a longer step could
  oscillate. This was not tested beyond 60 and 120 Hz.
- Each wheel has one contact, found downward. A wheel cannot hit a step's face, and the sweep's normal is the only
  sign of an edge.
- If the box itself touches the ground, Chaos's contact and this solve do not know about each other.
- Rotation was locked on every rig. A free rigid body, as a rover needs, has not been tested.
- Everything in "What this model covers" below still applies.

## Attempt 3: friction by contact slip, design note, written before the code

The owner approved this fix on 2026-11-03, after [phase C's diagnostics](phase-c-design.md#diagnostics-2026-11-03-stopped)
found sliding friction pointing 29–56° away from the slip. Attempts 1 and 2 and their records stay as they are.

### Slip velocity

`u` is the velocity of the wheel's material point at the contact, relative to the static ground, in the contact plane:

`u = (v·f − ω R, v·l)`

Here `v` is the body's velocity at the contact point and `ω R` is the rim speed. A rolling wheel has `u = 0`. Attempts 1
and 2 called `s = −u_f` the slip; the sign convention for `s` in the CSV is unchanged.

### Forces, reaction torque, and power

- **The ground's tangential force `F = (F_f, F_l)` acts on the body at the contact point.** Its reaction acts on the
  wheel at the rim, so the wheel feels `−F_f R` about its axle. The motor or brake adds `τ`:
  `I dω/dt = τ − F_f R`.
- **Power balance.** Over the wheel and the body, with no other force,
  `d/dt (½ M v² + ½ I_w ω² + ½ ωᵀ I ω) = F·v + (τ − F_f R) ω = F·u + τ ω`.
- **Two sources, kept separate.** The motor supplies `τ ω`, which can be positive or negative. The contact's friction
  power is `F·u`, which must never be positive.
- **Recorded per wheel and step.** `F·u` and `τ ω` use the end-of-step velocities that the implicit solve acts on.

### Static and kinetic friction, kept apart

The coefficient stays one value, `μ`, for both, as in the criteria. They are handled as two separate cases, with one
rule deciding between them:

1. **Stick.**
   - The solve finds the tangential force that makes the end-of-step slip zero: `u_end = 0`.
   - It does so against the body's coupled motion, the wheel's inertia, and the motor or brake.
   - If that force lies inside the friction circle, `|F| ≤ μ Fz`, it is the answer. The force is whatever holding
     needs: zero on flat ground at rest, `M g sin θ` on a slope.
2. **Slide.** If no force inside the circle can stop the slip, the contact slides. The force is then the one on the
   circle `|F| = μ Fz` that opposes the slip it leaves at the end of the step: `F = −μ Fz u_end / |u_end|`. Its
   friction power `F·u_end = −μ Fz |u_end|` is negative.

**How one wheel's solve finds the force.** The end-of-step slip is linear in the wheel's own force:
`u_end = a + W F`.
- `a` is the slip with this wheel's force removed. It includes gravity, normal loads, and the other wheels' current
  forces.
- `W` is the 2 × 2 block of the coupling `K`, times `dt`. If the motor's or brake's torque limit binds, the wheel's
  spin compliance `dt R² / I` is added to its `f` entry.

Both cases are then one problem: minimize `½ Fᵀ W F + aᵀ F` subject to `|F| ≤ μ Fz`.

**Why that problem gives the right answer.**
- **Inside the circle,** the minimum gives `u_end = 0`, which is stick.
- **On the edge,** the optimality condition is `a + W F = −λ F` with `λ ≥ 0`. So `u_end` is anti-parallel to `F`,
  and the force opposes the slip exactly.
- **Finding the edge force.** `F(λ) = −(W + λ I)⁻¹ a`. Its length falls as `λ` grows, and `λ ≤ |a| / (μ Fz)`. A
  bisection on `λ` finds the edge to machine precision.

**The answer changes continuously with `a`.** That leaves no jump at the switch between stick and slide for a step to
bounce off. Attempt 2 scaled the stick demand down to the circle instead, and its direction was not the slip's.

### Motor and brake

The motor or brake first tries to hold the target spin: `ω_end = ω*`.
- `u_f` then uses `ω* R`, and the torque that results is `τ = I (ω* − ω) / dt + F_f R`.
- If `|τ|` exceeds the limit, `τ` is clamped, and the wheel's spin becomes free. The solve then runs again with the
  spin compliance added to `W`.
- Coasting always uses `τ = 0` with the spin free.

Spin then updates as `ω_end = ω + dt (τ − F_f R) / I`, so force and reaction torque always match.

### Coupling and limits

- **Coupling across wheels** stays as in attempt 2. Projected Gauss-Seidel solves each wheel against the others'
  current forces. The `K` matrix and the known-force prediction are unchanged.
- **The settings stay as in attempt 2:** 200 passes, 1e-7 cm/s.
- **The limits:**
  - The friction circle is never exceeded.
  - Torques never exceed their limits.
  - Normal forces still come only from the suspension.
  - No velocity is written.

### Checks before any run

Unit tests on a test body stepped in Chaos's order:
- **Holding:** a slope held by static friction.
- **Sliding:** one-direction and diagonal sliding on locked and yaw-free bodies, with the force anti-parallel to the
  slip and `F·u ≤ 0`.
- **The switch:** from stick to slide under a rising push, with no oscillation.
- **Wheel spin in the slip:** a spinning wheel on a still body.
- **Motor and brake:** driving and braking within the torque limits.
- **The friction circle:** never exceeded.
- **A free six-wheel body turning in place:** no repeating cycle, with net force and torque consistent with its
  motion.
- **Time step:** the same turn at 60 and 120 Hz.

**Result before the runs.** `Roverloom.WheelSpike.Friction` passed, with the module's three other tests. Its first run
failed on two of its own checks, on rounding rather than physics. The tests were then made to measure at
floating-point precision, as listed below, and the model was not touched.

| Check | Measured |
| --- | --- |
| Local solve, demand from 24 directions | Force on the circle; worst angle to the opposing slip below 1e-6° |
| Diagonal slide on a locked and a yaw-free body | Worst angle below 1e-6°; friction power never positive beyond 1e-6 cm/s of slip times `μ Fz` |
| Stick to slide under a rising push | Force equals the push while sticking; one switch; force and speed never fall |
| Spinning wheel under a still body | Slides first, pushes forward, keeps `M v + I ω / R`, loses energy every step, then rolls |
| Six wheels, free body, turn in place for 10 s | Steady at 18.9798 °/s at both 60 and 120 Hz; no change in yaw rate over the last second; worst sliding angle 1.6e-7° at 60 Hz and 2.4e-7° at 120 Hz; net horizontal force below 6e-11 |

**The two corrections to the tests.**
- **The angle.** The first version computed it with `acos`, which loses precision near zero: about 1.2e-6°. It now
  uses `atan2` of the cross and dot products.
- **Friction power.** On a sticking wheel this is the force times the solver's residual slip, about 1e-9 cm/s. That
  left 5.7e-5 above zero. The limit is now set as a slip speed: 1e-6 cm/s times `μ Fz`.

**The six-wheel turn settles at 18.98 °/s for 28.178 °/s commanded.** This is a measurement on the test body, not a
gated result. Front and rear wheels must scrub sideways to turn in place. With Coulomb friction they slide, and the
middle wheels' motors reach their limit.

### Attempt 3 runs

- **The same plan, tests, and thresholds as attempts 1 and 2.** That is 17 runs and 15 tests, counted as before.
- **Batch** `wheel-ab-attempt3-20261103`, separate from the earlier batches.
- **Added report-only records:**
  - per wheel and step: friction power `F·u_end` and motor power `τ ω_end`;
  - per run: the largest positive friction power, and the largest angle between a sliding force and its slip.

## Results: phases A and B, attempt 3, 2026-11-03

**All 15 tests passed.** Batch `wheel-ab-attempt3-20261103` at commit `a105e1a`, 17 runs, with the conditions fixed
there. Attempts 1 and 2 stand as recorded.

| Test | Attempt 1 | Attempt 2 | Attempt 3 |
| --- | --- | --- | --- |
| A1, A1s | Pass | Pass | Pass; the same values |
| A2, A2s | Pass | Pass | Pass; 50.000 cm/s, 95% in 0.30 s |
| A3, μ 0.05 | Pass; traction 0.9999996–1.000 × μ Fz | The same | Pass; traction exactly 1.000 × μ Fz; 18.550 cm/s² |
| A4, μ 0.1 | Pass; 37.100 cm/s²; 33.28 cm | The same | Pass; the same |
| A5, μ 0.3 | Pass; peak 57.5 cm/s | Pass; peak 55.65 cm/s | Pass; the same as attempt 2 |
| A6, 10° hold | **Fail, 1.074 cm/s** | Pass, 0.000 | Pass, 0.000 |
| A7, 10° slide | Pass; 27.887 cm/s² | The same | Pass; the same |
| A8, time step | Pass; 0.0% and 0.63% | The same | Pass; the same |
| B1, B2 | Pass | Pass | Pass; 50.000 cm/s and 28.178 °/s |
| B3, stop | Pass; 0.53 s | Pass; 0.32 s | Pass; 0.32 s |
| B4, 10° hold | **Fail, 6.222 cm/s** | Pass, 0.000 | Pass, 0.000 |
| B5, time step | Pass; 0.08% and 0.06% | Pass; 0.04% and 0.06% | Pass; the same as attempt 2 |

**Why attempt 3 matches attempt 2.** Every slide in phases A and B is in one direction, so the old and new friction
agree there.

**The report-only friction records:**
- the largest friction power over `μ Fz` was 0.000 cm/s, so friction never added energy;
- every sliding force pointed against its slip, at 0.000°;
- every solve converged, in at most 23 passes.

**Runner checks over the 17 runs:**
- Every exit code was 0, with no new crash report and no forced stop.
- Peak resident memory was at most 2,210 MB, and free memory never fell below 38%.
- Swap stayed at 3,359 MB.

**A layout note.** Commit `a105e1a` dropped this page's "What this model covers" heading by mistake. It is restored
below, and its table did not change.

## What this model covers, and what it does not

| Covered, in game terms | Not covered |
| --- | --- |
| Normal load from a spring-damper | Sinkage, soil compaction, bulldozing |
| Coulomb friction limit on combined traction | Traction that depends on slip ratio or slip angle |
| Wheel spin with inertia, motor and brake torque limits | Grousers, soil shear, and the Bekker or Wong-Reece relations |
| Spinning, locking, sideways sliding | Rolling resistance from soil; it is zero here |
| One body; any number of wheels | Wheel width, tire deformation, or several contacts per wheel |

## Chaos's own vehicle systems, compared

From the UE 5.8.4 source and Epic's 5.8 pages. Neither was run.

| Aspect | Chaos Wheeled Vehicle | Chaos Modular Vehicle | This model |
| --- | --- | --- | --- |
| Status in 5.8.4 | Plugin marked Experimental, off by default | Plugin marked Experimental; its examples are Beta | Project code |
| Six wheels | "No limit on the number of wheels", per Epic's setup page | Wheel modules; not checked for count | Yes |
| Skid steering | Not documented. Per-wheel `SetDriveTorque` and `SetBrakeTorque` exist | Not documented | Yes, per-wheel targets |
| Rocker-bogie | No. Each wheel has its own raycast suspension on one body | Modules attach to a cluster union of parts; articulation is not documented | Not yet; would need bodies and joints, or kinematic links |
| Contact and forces visible | `FWheelStatus`: contact, contact point, slip angle, spring force, drive torque, skidding | Module state; not checked in detail | Every force and velocity per wheel, every step |
| Tire model | Slip graph and friction multiplier | Wheel module with slip angle limit and friction multiplier | Coulomb circle, sticking solve |
| Physics step | Has an async physics callback, `ChaosVehicleManagerAsyncCallback` | Has its own, `ChaosSimModuleManagerAsyncCallback` | Pre-physics tick, once per step |
| Setup from C++ | Movement component on a skeletal mesh; wheels are classes | Built from assets and components | Fully in C++ |
| Assets needed | Skeletal mesh with a bone per wheel, a physics asset, wheel classes | Geometry or skeletal assets for each module | None; engine basic shapes |
| Load on this Mac | Not measured | Not measured | Peak resident memory 2.3 GB in these tests |

Neither standard system fits rocker-bogie without its own work, and both need assets that this experiment avoids.
