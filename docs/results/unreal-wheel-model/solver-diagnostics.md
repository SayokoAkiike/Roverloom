# Wheel model: contact solver diagnostics

Not gated. This page studies the contact solver after [phase C failed](phase-c-design.md#results-2026-11-03-phase-c-failed-2-of-9-tests-passed).
It changes no criterion, threshold, record, or verdict. Each run used the six-wheel rig and scenarios of phase C at commit
`5b76e91`, with solver settings changed only through diagnostic flags. With no flag set, these runs match the gated
records cell for cell, over every shared column of C2, C3, C5, C6 at 10°, and C7.

## What was added

| Item | Role |
| --- | --- |
| `FSolverOptions` in `WheelModel.h` | Pass limit, stop tolerance, and wheel order: forward, reverse, alternating, or shuffled. The defaults are the gated settings |
| Warm start | Each wheel starts from its last tangential force, projected onto the current contact plane and clamped to the current friction circle. A wheel without contact on either step starts from zero |
| Optimality checks | Every step records a natural residual, `|F − P(F − ρ u)| / μ Fz`, with one scale `ρ` for both directions. It also records the largest slip at a sticking wheel and the largest spin error where a torque is inside its limit. None of these depend on the stop rule |
| Shadow solve | Optionally re-solves each step with 20,000 reverse-order passes and compares the forces. The shadow's forces are never applied |
| Sleep control | `-WheelSleep=0` sets this experiment's own physical material to sleep thresholds of 0. No engine or project setting is changed |
| Step dump | `-WheelDumpAt=<s>` writes one step's solver input as JSON |
| `scripts/wheel_solver_lab.py` | Re-solves a dumped step offline: a port of the PGS that tracks the objective each pass, and the same step as one convex problem solved by FISTA |
| `Roverloom.WheelSpike.Solver` | Unit tests. A warm start is clamped, and ignored out of contact. Different orders give the same net force and torque on the same state |

**The convex problem.** Each wheel in contact has unknowns `x = (F_f, F_l, τ)`. The end-of-step contact slip
`u = (v_f − ω' R, v_l)` and spin error `s = ω' − ω*` are linear in `x`: `w = A x + b`, with `A` symmetric positive
semidefinite. Minimizing `½ xᵀ A x + bᵀ x` subject to `|F| ≤ μ Fz` and `|τ| ≤ limit` gives these conditions:
- **Each contact** either sticks with `u = 0`, or slides with its force opposing `u`.
- **Each motor or brake** either holds its target with `s = 0`, or sits at its limit.

The PGS of attempt 3 solves exactly this problem, one wheel at a time.

## Runs

Batch `solverdiag-20261103`, 61 runs.
- **Exit codes and crashes:** every exit code was 0, with no new crash report and no forced stop.
- **Memory:** peak resident memory was 2,182 MB, and free memory never fell below 39%.
- **Swap:** unchanged at 3,335 MB.

| Condition | Flags | Scenarios |
| --- | --- | --- |
| `A_sleep_on` | Gated settings, shadow on | C2, C3, C5, C6 at 10°, C2 and C3 at 120 Hz; C7 without shadow |
| `A` | The same, sleep off | The same |
| `B2000`, `B20000` | 2,000 or 20,000 passes, sleep off | The same; C7 for `B2000` only |
| `C_warm` | Warm start, sleep off | The same, with C7 |
| `D_reverse`, `D_alternate`, `D_shuffle` | Wheel order, sleep off | The same; C7 for `D_alternate` only |
| `CB_warm_alt_2000` | Warm start, alternating order, 2,000 passes, sleep off | The same, with C7 |

Four steps were also dumped and re-solved offline, under `dumps/`:
- the turn at 19.47 s;
- the 10° climb at 3.57 s;
- C7 at 85.0 s and at 96.53 s, where the gated run's last pass changed most.

## Results by condition

`us` is wall time per solve, measured around the primary solve only. "Short runs" means the six runs other than C7, which
total 10,686 steps with a contact.

| Condition | Steps not converged, short runs | Largest natural residual, short runs | C3 solve, median and p99 | C7 solve, median, p99, worst | C7 steps not converged | C7 natural residual, worst and p99 |
| --- | --- | --- | --- | --- | --- | --- |
| `A_sleep_on` | 3,028 | 2.5e-4 | 1,626 and 1,679 µs | 1.9, 4.0, 6.5 ms | 18,267 of 36,001 | 9.3e-3 and 2.7e-4 |
| `A` | 2,960 | 2.5e-4 | 1,626 and 1,696 µs | 2.2, 4.0, 6.2 ms | 19,539 | 8.0e-3 and 3.0e-4 |
| `B2000` | 2,963 | 5.7e-7 | 14.8 and 16.0 ms | 2.1, 21.0, 43.5 ms | 16,476 | 2.1e-4 and 4.5e-7 |
| `B20000` | 2,950 | 7.6e-7 | 143 and 157 ms | not run | | |
| `C_warm` | 2,948 | 7.6e-7 | 2.2 and 3.5 ms | 0.39, 4.1, 6.7 ms | 16,242 | 7.2e-3 and 1.1e-5 |
| `D_reverse` | 2,969 | 1.4e-4 | 2.2 and 3.5 ms | not run | | |
| `D_alternate` | 1,541 | 6.2e-5 | 0.28 and 4.2 ms | 0.58, 4.3, 7.0 ms | 13,899 | 2.8e-2 and 1.6e-3 |
| `D_shuffle` | 2,958 | 6.5e-5 | 2.4 and 3.5 ms | not run | | |
| `CB_warm_alt_2000` | 1,707 | 7.0e-7 | 0.09 and 17.7 ms | 0.39, 21.1, 43.3 ms | 14,136 | 2.0e-3 and 4.7e-7 |

**No condition met the gated stop rule on every step.** The rule is a last-pass change below 1e-7 cm/s, and no
condition reached it on every step, even at 20,000 passes. In the turn, the last change stayed near 4e-6 cm/s under
every condition.

**What each change did:**
- **More passes** removed the large transients. In the 10° climb and the 120 Hz straight run, the largest residual
  fell from 2.5e-4 to below 1e-6. The cost rose about tenfold for each tenfold rise in passes.
- **Warm start** did the same at 200 passes, and cut C7's median solve from 2.2 ms to 0.39 ms.
- **Alternating order** halved the steps not converged in the short runs, and cut the turn's median solve to 0.28 ms.
  In C7 it did worse in the worst cases.
- **Combined, at 2,000 passes:** C7's p99 natural residual reached 4.7e-7. Its p99 solve took 21 ms, over a 60 Hz
  frame's 16.7 ms.

**Body motion barely changed across conditions.**

| Measure | Spread across all conditions |
| --- | --- |
| Turn's yaw rate | 18.9798 °/s in every condition, to 1e-5 |
| Final positions in C2, C3, C5, C6 | Within 0.0003 cm of each other |
| 60 against 120 Hz | C2's end X 1.78e-4 apart in every condition; C3's yaw rate 1.6e-6 to 1.9e-6 apart |
| Shadow against primary: largest single-wheel force difference | Up to 1.6 × μ Fz |
| Shadow against primary: net tangential force, worst | 29, about 1e-4 of the weight, in C2 at 120 Hz |
| Shadow against primary: net torque, worst | 2,150 |
| Shadow against primary, in the turn | 0.06 force and 3.9 torque |

**Separating non-unique forces from non-unique motion.**
- **Forces are not unique.** Twelve force rows act on six body freedoms, so many sets of wheel forces give the same
  body motion. Solvers that agree on motion disagreed on single wheels by up to 27,000, which is 0.85 × μ Fz.
- **Motion is unique at the optimum.** The convex problem fixes the end-of-step velocities and the net wrench. Where
  solves differed in net force, they had not reached the optimum. That is non-convergence, not non-uniqueness.

**C7 is chaotic over 600 s, so its final pose cannot be compared between conditions.**
- Positions under every condition stayed within 0.1 cm of each other until 86 s.
- At 85–86 s a wheel crossed a block edge. There the gated settings left last-pass changes near 0.01 cm/s for many
  steps, and that run began to drift.
- The better-converged conditions (`B2000`, `C_warm`, `CB_warm_alt_2000`) stayed within 0.1 cm of each other until
  124–171 s, then drifted too.
- Final positions ended up metres apart. In every condition tilt stayed at 4.0° or less and speed at 55.3 cm/s or
  less, and no box contact or NaN occurred.

## The four dumped steps, re-solved offline

Natural residuals are relative to `μ Fz`. FISTA, run for 100,000 iterations, gave the reference.

| Step | 200 passes, each order: is the optimality gap closed? | 20,000 passes | Work to reach 1e-8: forward, reverse, alternating PGS; FISTA |
| --- | --- | --- | --- |
| Turn, 19.47 s | Forward and reverse: no (gap 0.13 in objective; residual 5.4e-8). Alternating: yes, in 9 passes | Forward and reverse still not | never, never, 9; 14,874 |
| Climb, 3.57 s | No order (residual 2e-6 to 5e-6; net force off by 1.9–3.0, torque by 490–1,020) | All orders | 679, 599, 784; 760 |
| C7, 85.0 s | Forward: no (net force off by 215, torque by 7,141). Reverse and alternating: yes | All orders | 209, 55, 171; 650 |
| C7, 96.53 s | No order (net force off by 2 to 266, torque by 600 to 16,800) | All orders | 242, 255, 380; 800 |

**The PGS's objective never rose in any pass, so it never cycled.** It is a descent method that crawls:
- **The turn's forward stall** lies in a nearly flat valley of the objective, along directions that trade forces
  between wheels. Over 20,000 passes the gap shrank only from 0.130 to 0.123, against an objective of 5.4e6. Wheel
  forces stayed up to 26,700 from the reference, while net force stayed within 0.06 and net torque within 4.1.
- **Other steps are ill-conditioned rather than flat.** They need 200 to 800 passes in any order.
- **The 1e-7 cm/s stop rule mixes the two cases.** The flat valley has a small natural residual but a last change
  that never vanishes. The ill-conditioned steps have a real residual.

## Chaos sleep, on and off

**What it did, with sleep on, per run:**

| Run | Events | When | Largest speed and spin lost |
| --- | --- | --- | --- |
| C5 and C6 at 10° | 12 each | 0.40–1.32 s, while settling | 0.57 cm/s and 0.47 °/s; up to 0.69 cm/s just before |
| C7 | 132 | In clusters from 243 s to 598 s, during slow phases of the random driving | 1.0 cm/s and 2.7 °/s |
| C2 and C3 | None | | |

Each event is recorded in `sleep_events.json` with:
- its time;
- the body's speed and spin just before it;
- the speed and spin that the step's forces predicted;
- the net force less the weight.

Each event is a step where the forces predicted motion, but Chaos set every velocity to exactly zero. This is Chaos,
not the solver, and these steps are left out of the solver's checks.

**With sleep off:**
- **No events.** The sleep threshold is set on this experiment's own material, and with it at zero none occurred.
- **Short runs.** Results matched sleep on within 0.0003 cm in final position. Solver statistics were the same within
  run-to-run noise.
- **C7.** It diverged from sleep on after 107 s.
- **The first difference was not a reset.** It appeared at 3.07 s, 1e-5 °/s in pitch rate, when driving began. With
  sleep on, the body had been asleep at rest and was woken by the first force, which changes its first steps
  slightly. Chaos's sleep therefore affects a run in two ways: velocity resets while slow, and a small difference on
  waking.

## Unresolved

- **The stop rule.** No setting tested met the gated stop rule on every step. The rule judges the last pass's change,
  not optimality.
- **The cost of converging.** Driving the natural residual below 1e-6 on every step took up to 2,000 passes. At the
  worst C7 steps that is 21 to 43 ms per solve.
- **The turn's flat valley.** Only alternating order converged on it. The other orders crawl even at 20,000 passes.
- **Block edges in C7.** Even 2,000 passes left a residual up to 2e-3 there.
- **Long runs are chaotic.** A long run's final pose is sensitive to any change, so it cannot judge a solver.

## Options, not yet chosen

Each would change the model or the solver, and needs the owner's approval before it is built or gated.

1. **Judge convergence by the natural residual,** not the last change. This would be a new criterion for any new gated
   run. Phase C's verdict stays as it is.
2. **Alternating order with a warm start,** and a residual target with a pass cap. This is the cheapest gain measured.
   It is not enough on its own at block edges.
3. **A solver in body space.** The motion is unique while the forces are not, so a method over the body's velocities
   and the wheel spins would avoid the flat valleys. That means 12 unknowns, through a Newton or interior-point
   method. It should be tried first in `wheel_solver_lab.py` on many dumped steps.
4. **A small contact compliance** that makes the force split unique. It changes the physics slightly, so its size and
   effect would have to be measured.
5. **Sleep off for the rig in physics runs,** through the experiment's own material, as tested here.
