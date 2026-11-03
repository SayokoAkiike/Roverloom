# Wheel model, phase C: six wheels (design draft, not implemented)

**Status, 2026-11-03.** The owner approved implementing this design. The six-wheel rig is built, and diagnostics found
a defect in the friction model, so work stopped before any gated run, as the owner instructed. **The criteria below
were not registered, and no gated run took place.** See [Diagnostics](#diagnostics-2026-11-03-stopped). R1, the
rocker-bogie, stays on hold. R0's verdicts are not rejudged.

The scientific limits in [the main page](README.md#what-this-model-covers-and-what-it-does-not) apply unchanged. This
is a game-style model and never feeds the Python Mission Core.

## Structure

| Item | Proposal |
| --- | --- |
| Body | One Chaos rigid body, a 200 × 150 × 40 cm box of 853.5 kg, the `pathfinder_6w` mass, as in R0. No DOF locks: all six freedoms are free |
| Inertia | Chaos's box inertia for that mass. The model reads it as a world tensor, and inverts all three axes |
| Wheels | Six model wheels, not bodies, mounted at X +97.6, 0, −97.6 cm and Y ±103.7 cm, 20 cm below the body's center. Radius 25 cm, spin inertia 3,750 kg cm², as in phases A and B |
| Suspension | One independent spring-damper per wheel: 5 cm static compression under `M g / 6`, damping ratio 0.7, 30 cm rest length. This is not a rocker-bogie |
| Ride height | Body center 70 cm above flat ground; underside 50 cm |
| Contact | A sphere sweep of the wheel's radius by default, because terrain has edges. A ray for comparison in the static and straight tests |
| Motor and brake | The same limits: 6e5 and 2e6 per wheel |
| Commands | Left and right linear speeds, converted at 0.25 m as in R0: `ω = v / 25 cm`. A turn in place sets rim speed `±ω_yaw × 103.7 cm` |

## Contact force calculation

The same `SolveWheels` as attempt 2, with no change to its equations:

- **Rows.** 12 rows: a longitudinal and a lateral row for each of the six wheels in contact.
- **Coupling.** `K_ab = (d_a · d_b) / M + (r_a × d_a) · I⁻¹ (r_b × d_b)`, with the full inverse world inertia. The
  rig code already handles three free axes, but no test has run it yet.
- **Prediction.** Gravity, all six normal forces, and their torques are in the prediction before traction is solved.
- **Limits.** The same friction circle and torque limits as attempt 2.
- **Passes.** Projected Gauss-Seidel, at most 200 passes, stopping below 1e-7 cm/s.
- **Not unique.** Twelve rows act on six body freedoms, so the split of traction between wheels is not unique.
  Totals, contact velocities, and the body's motion are judged. Single-wheel traction is recorded only.
- **Body contact.** If the box touches the ground, Chaos's contact is outside this solve. Every such step is recorded.

## Tests and proposed criteria

Fixed step at 60 Hz unless stated. Gravity −371 cm/s², friction 0.6. Thresholds come from R0 where R0 defined one, so
the two can be compared. The wheel model's own thresholds apply where R0 had none.

**Every run** must:
- complete, with no NaN and speed under 1,000 cm/s;
- keep traction within `μ Fz` to a relative 1e-6, and torques within their limits;
- converge the solve on every step.

| ID | Setup | Pass |
| --- | --- | --- |
| C1 | 15 s at rest, flat, sphere sweep | Body height range < 0.5 cm over 10–15 s (R0). Sum of loads within ±1% of `M g`; each wheel within ±5% of `M g / 6` |
| C1r | C1 with rays | The same |
| C2 | 50 cm/s step after 3 s | Reaches 47.5 cm/s; peak ≤ 55; mean over 13–23 s within ±5% (R0). Mean |yaw rate| < 0.5 °/s |
| C3 | Turn in place, 28.178 °/s step after 3 s | Yaw rate over 13–23 s has the commanded sign, within ±10% (R0) |
| C4 | C2 and C3 at 120 Hz | End X and total yaw differ from 60 Hz by < 5% (R0). The 120 Hz runs must pass C2 and C3 |
| C5 | 10° slope, zero command | Mean downhill speed over 5–10 s < 0.1 cm/s |
| C5b | 10° slope, brake | The same |
| C6 | Climb 5° and 10° at 50 cm/s, from 3 s | Mean uphill speed over 20–30 s ≥ 25 cm/s (R0's report line); tilt < 45° throughout |
| C7 | 600 s of random commands, seed 42, among 10 cm blocks | Completes; speed ≤ 200 cm/s; tilt ≤ 60° (R0). The box never touches the ground |

**Reported without a threshold:**
- **Steeper slopes,** 15° and 20°: climb, hold, and tipping. R0 tipped on both.
- **Steps** of 10, 25, and 50 cm. Contact is only downward, so a step's face is not felt. A failure is expected, and it
  would be a known limit, not a finding.
- **Turn scrub.** For C3: per-wheel lateral slip and traction at the corner wheels, which must scrub sideways when six
  wheels turn in place.
- **Repeatability.** Five deterministic runs of C2 at 60 Hz. The spread of the end pose is reported.
- **Performance.** 60 s of driving in real time at 1280 × 720: frame time percentiles, peak resident memory, and
  minimum free memory.

## Run count

- **Gated: 11 runs.** C1, C1r, C2, C3, C2 and C3 at 120 Hz, C5, C5b, C6 at 5° and 10°, and C7.
- **Judged as 9 tests:** C1, C1r, C2, C3, C4, C5, C5b, C6, and C7. Phase C passes only if all nine pass.
- **Reported only: 12 runs.** Two steeper slopes, three steps, five repeats, one performance run, and the C3 scrub
  records, which come from C3's run.

## Work this would need

- A third rig in `WheelSpikeGameMode` with no locks and six mounts.
- Slope and step terrain, reusing R0's builders.
- A command schedule for random driving.
- Phase C's plan and analyzers in `scripts/wheel_spike.py`.
- About 400 lines, with no change to `WheelModel`'s equations.
- A unit test of the free-body inverse inertia against a hand-computed box tensor, run before any gated run.

## Diagnostics, 2026-11-03: stopped

Not gated. Each batch ran at 60 Hz with a fixed step, on the six-wheel rig as designed above, with the attempt 2 solver
unchanged.

### Stage 1: free fall, landing, and load distribution. No problem found

Batch `cdiag1-20261103`.

| Run | Measured |
| --- | --- |
| `cd_freefall`, dropped from 5 m for 1.4 s | Vertical acceleration −371.0001 cm/s² over 0.1–0.6 s. No wheel in contact, and no force from any wheel |
| Inertia, read in the same run | 1,714,112.6, 2,958,800.2, 4,445,313.0 kg cm². A 200 × 150 × 40 cm box of 853.5 kg gives 1,714,112.5, 2,958,800.0, 4,445,312.5. The inverse rows are diagonal |
| `cd_drop`, 20 cm above ride height | Peak load 3.57 × static; least 0.89 ×. Settled: each wheel 1.000 × `M g / 6`, sum within 1.3e-6 of `M g`, height range 1 µm over 6–8 s. Box never touched the ground |
| `cd_tilt`, 10 cm high with 3° roll and 2° pitch | Peak tilt 3.6°, then level to 1e-5°. Loads 0.065–2.99 × static during landing, then 1.000 ×. No roll or pitch growth |
| `c1` static, sphere sweep | Loads 1.000 × each; sum within 1.2e-8; height range 0 over 10–15 s |
| `c1r` static, ray | The same |

Wheels out of contact never produced a force. Every run completed, with no NaN, no box contact, and no start-in-geometry
trace. Wheel forces summed to `M g` at rest, with net torque below 1 N cm.

**One numerical note.** In `cd_tilt`, 13 steps reached the 200-pass limit without meeting the 1e-7 cm/s stop rule. No
wheel was saturated on those steps. The contacts' end-of-step velocities were at most 1e-6 cm/s, which is the CSV's
resolution. This is slow Gauss-Seidel convergence on a system with more rows than body freedoms, not a wrong force.
Neither the stop rule nor the pass limit was changed.

### Stage 2: friction while sliding. Defect found

Batch `cdiag2-20261103`. A saturated wheel is sliding, so Coulomb friction must act against the contact's sliding
velocity, which is the rim's speed relative to the ground along `f` and the speed along `l`. The table gives the angle
between the force on the body and that opposing direction, over every saturated wheel-step where the sliding speed
exceeds 0.01 cm/s.

| Run | Saturated wheel-steps | Angle: least, median, 90th percentile, most |
| --- | --- | --- |
| `cd_slide_brake`: diagonal push of 2 μ M g for 0.5 s, μ 0.3, braked | 411 | 0.1°, 29.3°, 47.2°, 52.0° |
| `cd_slide_coast`: the same push, coasting | 253 | 9.0°, 47.6°, 57.2°, 72.6° |
| `c3` run as a diagnostic: turn in place at 28.178 °/s | 4,804 | 47.0°, 54.4°, 56.3°, 56.3° |

**This is a defect in the model.** The friction circle scales the force that would stop all sliding in one step. That
demand is not parallel to the sliding velocity. The longitudinal row includes the wheel's spin, and the rows couple
through the body's rotation. So a sliding wheel pushes partly sideways to its slip. This is the limit noted in attempt
2, and these runs show it is large. Phases A and B could not show it: their sliding was in one direction, on bodies
with rotation locked.

**Its effect on the turn.**
- **Yaw rate.** The measured yaw rate over 13–23 s was 1.64 °/s, against 28.178 °/s commanded.
- **Corner wheels.** These are front and rear. Each spins at 2.04 rad/s, a rim speed of 51 cm/s, over ground moving
  at about 3.5 cm/s. Their slip is almost all longitudinal. Coulomb friction would then point almost along `f`.
  Instead the model applies about 15,500 along `f` and 27,600 along `l`, so the corners resist the yaw.
- **Middle wheels.** They stay stuck at their motor's 60 N m limit.
- **A limit cycle.** The yaw rate repeats every five steps: 0, 0.95, 1.45, 1.76, 1.96 °/s, and then exactly 0
  again. This is a non-physical stick-slip cycle, so it counts as an abnormal contact force. Of its steps, 150
  reached the 200-pass limit.

### What was not done

- The phase C criteria were not committed as registered, and no gated run took place.
- The model's equations, the solver's settings, and the draft thresholds are unchanged.

A fix needs the owner's approval. It would also need phases A and B to be rerun, because it changes the equations
they test.

### Possible fix, not applied

- **Coulomb direction while sliding.** When a wheel's demand leaves the friction circle, set its force to `μ Fz`
  against the contact's sliding velocity at the end of the step. That velocity includes the rim's speed after the
  wheel torque. Solve this direction inside the same Gauss-Seidel pass, either with a few fixed-point updates or with
  an exact local solve over the wheel's two rows and its spin.
- **Unit tests before any run:**
  - a sliding force anti-parallel to the slip, at any slip direction;
  - a coasting wheel that slides sideways with almost no longitudinal force;
  - no limit cycle in a turn-in-place test body.
- **Then the gated runs:** phases A and B again with their 15 tests and thresholds, then phase C's diagnostics, and
  only then phase C's registration.

## Diagnostics after the friction fix, 2026-11-03

Not gated. Batch `cdiag3-20261103`, separate from `cdiag1` and `cdiag2`. It used the attempt 3 model at `a105e1a`,
after phases A and B passed attempt 3. Each run is at 60 Hz unless named `_fps120`.

| Item | Before the fix (`cdiag1`, `cdiag2`) | After the fix (`cdiag3`) |
| --- | --- | --- |
| Free fall | −371.0001 cm/s² | The same |
| Landing from 20 cm | Peak 3.57 × static; settles to 1.000 × each | The same |
| Landing tilted 3° and 2° | Peak tilt 3.6°; settles level | The same; peak load 2.91 × static |
| Static, sweep and ray | 1.000 × each wheel | The same |
| Sliding force against its slip: braked, coasting | Median 29.3° and 47.6°; worst 52.0° and 72.6° | Median 0.0°; worst 1e-4° and 3e-4° |
| Turn in place, 28.178 °/s commanded | 1.64 °/s, in a five-step cycle from 0 to 1.96 °/s | **18.980 °/s, constant:** least and most over 13–23 s are equal to 1e-5 °/s |
| Turn, 120 Hz | Not run | 18.980 °/s; total yaw 376.940° against 376.997° at 60 Hz, 0.015% apart |
| Straight, 50 cm/s | Not run | Mean 50.000 cm/s over 13–23 s; peak 55.29 cm/s; no yaw; end X 993.52 cm |
| Straight, 120 Hz | Not run | Peak 55.27 cm/s; end X 993.34 cm, 0.018% apart |
| 10° slope, zero command | Not run | Mean drift 0.000 cm/s over 5–10 s |
| Climb 10° and 20° | Not run | 49.998 and 49.990 cm/s uphill over 20–30 s; tilt at most 11.3° and 21.3°, the slope plus pitch |

Across all 14 runs:
- every run completed, with no NaN, no box contact, and no start-in-geometry trace;
- traction stayed inside the circle to 1e-7, and wheels out of contact gave no force;
- loads stayed between 0.065 × static, in the tilted landing, and 3.57 ×, in the 20 cm drop.

**Resources.** Peak memory 2,202 MB; free memory at least 40%; swap unchanged; no crash.

### The turn, in detail

At 13–23 s:

| Wheel | Load | Force along `f` | Force along `l` | State |
| --- | --- | --- | --- | --- |
| Front and rear, each | 52,775 | ±14,496 | ±28,152 | Sliding, slip (16.6, 32.3) cm/s, force on the circle |
| Middle, each | 52,775 | ±24,000 | ±6,065 to 6,240 | Sticking, motor at its 60 N m limit |

- **Steady state.** The net horizontal force is below 0.05 and the net yaw torque below 5 N cm, which is a steady
  turn.
- **Yaw torque balance.** The wheels' push and the corners' sideways scrub balance, at 1.099e7 each way.
- **The yaw rate is set by the motor's torque limit.** The middle wheels are at their limit while the corners scrub
  at `μ Fz`.
- **Splits between wheels.** The middle wheels' sideways forces cancel each other, and their split between the
  wheels is not unique.

### Solver convergence

Many steps reached the 200-pass limit without meeting the 1e-7 cm/s rule. In 13–23 s of the turn, 974 of 1,381 steps
did so.

**The size of the remainder.**
- The last pass changed contact velocities by at most:
  - 4.9e-6 cm/s in the turn;
  - 2.8e-4 cm/s in the 120 Hz straight run;
  - 3.3e-4 cm/s in the 10° climb.
- On those few steps the sliding angle reached 1.1° and 0.28°, and friction power over `μ Fz` reached 9e-6 cm/s.
- Otherwise angles stayed below 0.01° and friction power below 1e-6 cm/s.

**The cause.** Twelve rows act on six freedoms, and plain Gauss-Seidel converges slowly on such a system.

## Against the draft criteria, before any registration

These diagnostics measured some of the same quantities that the draft criteria judge. If those criteria were
registered unchanged, they would be expected to fail on the following:

| Draft criterion | Diagnostic | Expected |
| --- | --- | --- |
| Every run: the solve converges on every step | 974 steps of the turn, and some steps of most runs, hit 200 passes | Fail |
| C2: peak ≤ 55 cm/s (R0) | Peak 55.29 cm/s. The body pitches back about 1.2° when it starts, which adds to its center's speed | Fail by 0.29 cm/s |
| C3: yaw rate within ±10% of 28.178 °/s (R0) | 18.98 °/s, limited by the 60 N m motor | Fail |
| C4: time step | 0.015% and 0.018% | Pass, but needs C2 and C3 to pass at 120 Hz |
| C1, C5, C6 at 5° and 10° | Matching values above | Pass |

**These are diagnostics, not results.**
- No criterion has been registered or changed.
- No gated run took place.
- Whether to keep these criteria, change them before registration, or change the model is the owner's decision.
