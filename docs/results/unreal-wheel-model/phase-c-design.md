# Wheel model, phase C: six wheels (design draft, not implemented)

**Status.** This is a draft for the owner's review, written after phases A and B passed on attempt 2. Nothing here is
implemented. The criteria below are proposals. They become fixed only after the owner approves them and they are
committed before the first gated run. R1, the rocker-bogie, stays on hold. R0's verdicts are not rejudged.

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
