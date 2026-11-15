# Wheel model: verifying improved method D

The owner approved this phase on 2026-11-04, after the [standalone C++ build of D](solver-cpp.md). It contains no
Unreal change, criterion change, or new gated run. Phase C stays failed, 2 of 9; ADR 0014 stays Proposed; the motor
limit stays 60 N m.

**What was not checked.** This is a game-style wheel model; nothing here is checked against a real rover or regolith.

**Machine and build.**
- Apple M4 Mac (Mac16,10), 16 GB, macOS 27.0.1.
- Apple clang 21, `-std=c++17 -O2`, one thread.
- Python 3.13.1 for the Python side.

**Tests outside CI, run on 2026-11-04:**
- `test_contact_solver.py`: 7 tests, OK.
- The C++ `tests`: 42 checks, 0 failures, now including five safety checks.

## Why 37 states stall above 1e-8

`scripts/contact_solver/cpp/probe.cpp` takes each state and examines D's answer in two ways:
- **It splits D's natural residual by wheel and by part:**
  - a sticking contact's slip;
  - a sliding contact's direction;
  - a motor's spin error.
- **It examines the constraints D holds:** every sticking contact (2 rows) and holding motor (1 row), at D's answer.
  - For `S = G M⁻¹ Gᵀ` over those rows, it projects their remaining slips onto each eigenvector of `S`.
  - **What a projection means.** A nearly zero eigenvalue means rows that are dependent. If the slips have a nonzero
    projection onto such an eigenvector, no velocity satisfies all those rows: they are inconsistent.

| Measure | The 37 stalled states | 40 converged states, at random |
| --- | --- | --- |
| States with a dependent direction, eigenvalue below 1e-12 of the largest | 37 of 37 | 11 of 40 |
| Slip that a dependent direction leaves, `|v·z|` | 2.8e-8 to 3.2e-6 cm/s | at most 3.7e-11 |
| Slip along the other directions | at most 2.7e-7 | at most 3.1e-10 |
| D's natural residual | 1.0e-8 to 4.8e-8 | at most 6.3e-11 |
| Natural residual after 50,000 alternating PGS passes, started from D | 1.2e-8 to 9.6e-8 | 2.6e-17 to 1.2e-11 |
| Velocity difference, D against that PGS | at most 5.9e-7 cm/s | at most 4.3e-11 |

**The stall is a property of these steps' constraints, not of D.**
- Their sticking and holding rows are dependent and slightly inconsistent, so no answer makes every slip zero.
- No method tested gets below about 1e-8 there: neither D, nor PGS, nor any reference.
- An exact optimum, in exact arithmetic, would need an unbounded internal force along the dependent direction, until
  a contact reached its circle or a motor its limit.

**Two examples.**

| State | Situation | Held rows on 12 freedoms | Dependent directions | Slip they leave | Natural residual |
| --- | --- | --- | --- | --- | --- |
| Turn at 120 Hz, step 288 | The corners slide; the middle wheels stick, at their motor limit | 8 | 1 | 2.2e-6 cm/s | 3.5e-8 |
| C2 at 120 Hz, steps 78 and 79 | All six wheels stick and all six motors hold | 18 | 9 | 1e-8 to 3e-8 cm/s | 1.0e-8 to 1.4e-8 |

In the turn, all of D's residual is the two middle wheels' slip, 1.57e-6 cm/s each. The sliding corners and the
motors are exact to 1e-16.

**What was ruled out:**

| Suspect | Test | Result |
| --- | --- | --- |
| Residual definition and scaling | Per-part breakdown above | The residual is the real slip of the middle wheels |
| Pseudo-inverse rank cut | Cut from 1e-6 to 1e-12; refinement within the kept space | Same 37 states, same values |
| Newton's stop | 200 steps per partition in place of 50; convergence judged on the full step | Same values. Newton converges: its step falls to 2e-15 |
| Friction against motor limits | Per-part breakdown | Every motor part below 1e-16 in the turn; nothing inconsistent between them |
| C++ against Python rounding | Python D and C++ D | Velocities agree to 2.5e-9; residuals differ at the floor only, either way |
| The reference | 50,000 PGS passes from D | No lower than D on any of the 37 |

**Where the inconsistency comes from is not established.** One candidate is the engine's contact geometry, with its
sweep points and normals. In the symmetric Python stand-in rig no step stalls.

### What a residual means in motion

Over all methods and states of the 1,620-state benchmark, grouped by natural residual, against the reference:

| Natural residual | Steps | Velocity error, median / worst (cm/s) | Angular velocity error, worst (°/s) |
| --- | --- | --- | --- |
| 1e-11 to 1e-10 | 1,097 | 4e-11 / 8.5e-8 | 6.9e-8 |
| 1e-10 to 1e-9 | 2,861 | 8.7e-10 / 4.8e-6 | 4.0e-6 |
| 1e-9 to 1e-8 | 3,462 | 4.9e-9 / 4.5e-6 | 4.1e-6 |
| 1e-8 to 1e-7 | 1,373 | 1.8e-7 / 3.8e-5 | 3.0e-5 |
| 1e-7 to 1e-6 | 100 | 2.9e-6 / 4.6e-4 | 4.3e-4 |
| 1e-6 to 1e-5 | 82 | 2.0e-3 / 9.8e-3 | 7.9e-3 |
| 1e-5 to 1e-4 | 83 | 1.8e-2 / 3.7e-2 | 3.5e-2 |

**What the table shows:**
- **Motion.** Below 1e-8, velocity errors stay below about 5e-6 cm/s. From 1e-6 they reach 1e-2 cm/s.
- **Energy.** The identity `ΔKE = dt (friction power + motor power) − dissipation` holds for any answer, to 8.7e-10.
  The residual does not show up there.
- **Contact states.** Each wheel's stick, slide, or no contact, and each motor's hold or saturation, were compared with
  D plus fallback on every state:

  | Method | States with a different pattern |
  | --- | --- |
  | A | 318 of 1,620 |
  | B_res | 231 of 1,620 |
  | D alone | 0 of 1,620 |
  | D with a 1 ms budget | 2, both at its budget |

## C++ short trajectories

`scripts/contact_solver/cpp/traj.cpp` mirrors `simulate.py` step for step: the same rig, rays to a plane, command
schedule, and step order. It has six scenarios:
- straight;
- turn;
- a 10° climb and a 10° hold;
- `stop`: driving, then braking on μ 0.2 from 1.5 s, where contacts switch between stick and slide;
- `drop`: a release 20 cm above ride height, where contacts are lost and found again.

Each runs at 60 and 120 Hz. Every step's state, contact states, net wrench, energy, residual, and solve time are
written.

**Python against C++.**
- **Setup.** The same initial state, inputs, step, and contact handling.
- **Over all 24 runs of A against A, and of Python D against C++ D written as Python:**
  - position within 2.8e-14 cm;
  - quaternion within 3.3e-16;
  - velocity within 8.9e-14 cm/s;
  - angular velocity within 2e-16 rad/s;
  - wheel spin within 5.6e-15 rad/s.

**Reproducibility.** Running all 60 C++ runs again matched every cell but the timing, 0 cells different.

**Methods against improved D with its fallback, over all six scenarios and both rates:**

| Method | Position | Velocity, cm/s | Angular velocity, °/s | Net force / torque | Steps whose contact pattern differs | Contact switches, total | Natural residual, worst | Time per step, µs: worst median / worst p99 / worst |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A (gated PGS) | 8.9e-7 cm | 1.4e-5 | 4.1e-5 | 1.5 / 290 | 188 | 106 | 3.3e-6 | 76 / 482 / 2,306 |
| D alone | identical | identical | identical | identical | 0 | 84 | 6.8e-16 | 174 / 328 / 347 |
| D, 1 ms budget | identical | identical | identical | identical | 0 | 84 | 6.8e-16 | 174 / 344 / 373 |

**What the trajectories show:**
- **No D run reached its budget.** In this symmetric stand-in rig, no step stalls.
- **A switches contact state more often than D.** Extra switches appear in C2 at 120 Hz, C6, the hold, and `stop` at
  120 Hz.
- **60 against 120 Hz is a time-step effect.** The gap is the same for every method: straight 0.218 cm and 0.042°,
  turn 0.065°, climb 0.230 cm, hold 0.017 cm, `stop` 0.225 cm, `drop` 0.438 cm.

**Energy.**
- **The identity held every step,** to 6.5e-10.
- **Mechanical energy less motor work** rose on some steps, by at most 0.083 Mg·cm, at the starts. It rose by the same
  amount for every method, so it comes from the explicit spring and damper, not from the solve.

## Time budgets and safe failure

**Why the 1 ms budget overran by 28 µs.**
- **The check.** The deadline was checked only before a Newton step or a fallback pass began.
- **One unit of work.** A Newton step takes 2.2 µs at the median and 19.7 µs at worst. A PGS pass takes 10.8–11.9 µs.
- **The overrun.** A unit begun just before the deadline ran past it, by 4–34 µs.

**The fix, now in `DOptions`.**
- Each solve keeps the duration of its slowest Newton step and of its slowest PGS pass so far.
- It does not begin a unit that would end past `deadline − FinalReserve`, where `FinalReserve` is 5 µs.
- `BudgetHit` is set whenever a unit was refused.

**Measured over 1,620 states and 7 repeats:**

| Budget | Medians over budget | Worst median | Single repeats over | Worst single repeat | States that reached the budget | Their worst residual / velocity error |
| --- | --- | --- | --- | --- | --- | --- |
| 1 ms | 2 | 1,006.5 µs | 7 | 1,013 µs | 39 | 1.4e-7 / 3.7e-6 cm/s |
| 2 ms | 0 | 1,993.2 µs | 3 | 2,064 µs | 36 | 4.8e-8 / 1.4e-15 cm/s |

**What can be guaranteed.**
- **Bounded:** the solver's own work. It ends within the budget plus one unit and the final evaluation: about 15 µs
  on this machine.
- **Not bounded:** preemption. macOS is not a real-time system, and the operating system can stop the thread at any
  time. An earlier run saw one repeat reach 2.67 ms against 1 ms. The same holds in Unreal's physics thread. A budget
  is therefore a target, and each step should record the time it actually took.

**Safe failure.**
- **What `MakeSafe` does.** It checks an answer before use, in order:
  - non-finite values;
  - forces beyond their circle or torques beyond their limits, by more than 1e-9;
  - a natural residual above a reject level;
  - an end-of-step speed above 1e5 cm/s, or a spin above 1e3 rad/s.
- **What it falls back to:** the answer projected onto the limits; then the previous step's answer, projected; then
  zero tangential force and torque.
- **Unit tests** cover a NaN, a force at 50 times its circle, an unconverged answer, and a missing previous answer.
- **On the 1,620 states, at a reject level of 1e-3,** no answer of A, D alone, or either budgeted D was flagged.

## Unresolved

- **Where the inconsistent constraints come from.** That is the cause of the 37-state floor, and it is not yet found.
  A later [analysis](stall-geometry.md) ruled out normals, planarity, and frames. An exploratory check there points
  to single-precision offsets of the middle wheels' contact points, not yet confirmed.
- **No trajectory in engine geometry.** D has driven only the symmetric stand-in rig, with no stall. A trajectory
  through the engine's own contact geometry has not been run.
- **Real-time cost.** Preemption makes any time budget a target, not a bound.
- **The target.** 1e-8 is still a working target, not a registered criterion.
