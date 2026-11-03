# Wheel model: contact solver research

A research phase approved by the owner on 2026-11-04, after [phase C failed](phase-c-design.md#failure-record-confirmed-by-the-owner-2026-11-04)
and the [solver diagnostics](solver-diagnostics.md). It compares contact solvers on the same inputs, in Python, outside
the Mission Core. It changes no Unreal solver, no criterion, no threshold, and no earlier record or verdict. Phase C
stays failed, 2 of 9. ADR 0014 stays Proposed.

This is a game-style wheel model. Nothing here is a claim about real rovers or regolith.

## Findings

1. **The last pass's change is not optimality.** The gated rule stops PGS when a pass changes no contact velocity by
   1e-7 cm/s or more. The natural residual measures distance from the optimum. In the turn, the gated PGS was close
   to optimal, with a natural residual of 3e-8 to 1e-7, while never meeting the rule. At C7's block edges it left a natural
   residual up to 1.2e-4.
2. **How contact force splits between wheels is not unique.** Six contacts give twelve force rows on six body
   freedoms.
   - Here, D and the reference agree on velocities to 2.7e-8 cm/s, yet differ at a single wheel by up to 0.27 × μ Fz.
   - In the earlier diagnostics, solves that agreed on net force to 5e-9 differed at one wheel by 0.85 × μ Fz.
3. **Different forces can give the same net wrench and motion.** Net force, net torque, and the end-of-step
   velocities are unique at the optimum: the velocity problem below is strictly convex. Where two solves differ in
   motion, at least one has not converged.
4. **Warm start and alternating order help PGS, but not everywhere.** With a residual stop at 1e-8 and at most 2,000
   passes, the median solve took 10 passes. Yet 2,000 passes were not enough on some states of every window but C2 at
   60 Hz, C5, and C6. The worst natural residual was 3.7e-6.
5. **The slow turn and the solver are separate problems.** Every exact method turns the Python rig at 18.9798 °/s,
   as the Unreal rig did. The 60 N m motor limits it, not the solve.
6. **Long trajectories must be judged apart from one step's accuracy.** C7 is chaotic: a 1e-8 difference becomes
   metres over minutes. This phase judges one step, short trajectories of 3–4 s, and contact events.

## The formulation

**Generalized velocity.** `q` has 12 entries: the body's linear velocity `v` (cm/s), its angular velocity `ω` (rad/s),
and the six wheels' spins. The mass matrix is block diagonal:
- `M_body I₃` for the body's mass;
- the body's world inertia `I`, from Chaos's diagonal inertia and the body's orientation;
- `I_w` for each wheel, 3,750 kg cm².

**One step,** in Chaos's order:
- `q*` is `q` after gravity, normal loads, and known pushes for `dt`.
- The solve adds impulses `dt x` through constraint rows `G`, so that `q' = q* + M⁻¹ Gᵀ dt x`.
- `x` holds each wheel's tangential force `(F_f, F_l)` and its motor or brake torque `τ`.

**The rows,** per wheel `i`, with `r` from the center of mass to the contact:

| Row | Velocity it measures | Bound on its multiplier |
| --- | --- | --- |
| Contact, `f` | `u_f = f·v + (r × f)·ω − R ω_i`, the contact point's slip | `|F| ≤ μ Fz`, a disk with the `l` row |
| Contact, `l` | `u_l = l·v + (r × l)·ω` | The same disk |
| Motor or brake | `s = ω_i − ω*_i` | `|τ| ≤ L`, 600,000 or 2,000,000 kg cm²/s² |

The ground's force acts on the body at the contact, and on the wheel's rim as `−F_f R`. The motor's torque acts on the
wheel. **As in `WheelModel.cpp`, the motor's reaction on the body is not modeled.** That is a simplification of the
current model, and it does not conserve angular momentum. A later [memo](motor-reaction.md) found the error smaller than this suggests: applying ground force
at the contact point already gives the body the motor's reaction at steady spin, so what is missing is the wheels'
spin-up torque. It was kept so that every method solves the same physics as
the gated runs.

**Two equivalent problems.**

| | Dual, over forces `x` | Primal, over velocities `q'` |
| --- | --- | --- |
| Minimize | `½ xᵀ A x + bᵀ x`, with `A = dt G M⁻¹ Gᵀ` and `b = G q* − c` | `½ (q' − q*)ᵀ M (q' − q*) + Σ dt μ Fz |u_i(q')| + Σ dt L |s_i(q')|` |
| Subject to | The disks and torque intervals | Nothing; the limits are inside the objective |
| Unique? | No. `A` is singular, with rank at most 12 for 18 unknowns | Yes. `M` is positive definite, so the objective is strictly convex |
| Hard part | Flat valleys, along force splits with no effect on motion | The norms are not smooth where a contact sticks or a motor holds |

Both have the same optimality conditions:
- **A contact sticks,** with `u = 0` and `|F| ≤ μ Fz`, or slides, with `F = −μ Fz u/|u|`.
- **A motor holds,** with `s = 0` and `|τ| ≤ L`, or saturates, with `τ = −L s/|s|`.

Having fewer unknowns does not make the primal easy. Its difficulty is the nonsmooth terms, and it remains.

**Energy.** For any `x`, exactly:
- **The balance.** `Δ(½ qᵀ M q) = dt (Σ F·u + Σ τ ω') − ½ |q' − q*|²_M`.
- **Friction** does work `F·u`, which must not be positive.
- **The motor** supplies `τ ω'`.
- **The last term** is the scheme's numerical dissipation.

This identity held to within 5.5e-10 kg cm²/s² on every state for every method, against kinetic energy changes of
order 1e6. That checks the formulation's consistency.

## Methods

Every method was judged by the same natural residual: for each wheel, the larger of two values.
- **Force part:** `|F − P_disk(F − ρ u)| / μ Fz`, with `ρ = 1 / max(A_ff, A_ll)`.
- **Torque part:** `|τ − P(τ − ρ_τ s)| / L`.

It is zero only at the optimum.

| | Method | Objective and constraints | Stop | Convergence judged by |
| --- | --- | --- | --- | --- |
| A | PGS, forward order, 200 passes, the gated settings | Dual, by exact 3 × 3 block minimization per wheel | Largest change in a pass, times `dt K`, below 1e-7 cm/s, or 200 passes | Natural residual |
| B | PGS, alternating order, warm start | The same | The same | Natural residual |
| B_res | B with a residual stop | The same | Natural residual ≤ 1e-8, checked every 5 passes, or 2,000 passes | Natural residual |
| C | FISTA | Dual, accelerated projected gradient with restart | Natural residual ≤ 1e-8, or 20,000 iterations | Natural residual |
| D | Generalized-velocity active-set Newton | Primal: smoothed Newton predictor to ε = 1e-5 cm/s, then exact KKT Newton on the guessed active set, with a pseudo-inverse for dependent sticking rows | Natural residual ≤ 1e-8; if missed, flip each ambiguous term, then fall back to B_res from D's forces, at most 5,000 passes | Natural residual |
| E | B with `A + γ diag(A)`, γ = 1e-6, 1e-4, 1e-2 | Regularized dual: unique forces, but a creep `u = −γ diag(A) x` | As B | Natural residual of the unregularized problem |

**Warm starts** project the last step's force onto this step's contact plane, then clamp it to this step's circle. A
wheel that was out of contact on either step starts from zero. Unit tests check both.

## Data

**Saved states.** Batch `solverresearch-20261104/states`: 1,620 consecutive solver inputs, with the engine's own result
for each, from ten windows of the gated scenarios. They come from the Unreal rig with gated solver settings and sleep
off:

| Window | Steps | Scenario |
| --- | --- | --- |
| `c2_60`, `c2_120` | 96, 192 | Start of C2 at 60 and 120 Hz, 2.9–4.5 s |
| `c3_60_onset`, `c3_60_steady`, `c3_120_steady` | 186, 60, 120 | C3: start 2.9–6 s; steady 15–16 s at 60 and 120 Hz |
| `c5_60` | 120 | C5 settling, 0–2 s |
| `c6_60` | 66 | C6 at 10°, start 2.9–4 s |
| `c7_edge1`, `c7_edge2` | 240, 180 | C7 at block edges, 84–88 s and 95–98 s |
| `c7_sample` | 360 | C7, every 100th step over 600 s |

**The Python port of A reproduces the engine.** On all 1,620 states, the engine's dumped forces and the port's gave
the same natural residual, velocities, and net wrench. The two differ only in the last bits of energy rounding.

**Runner checks over the 10 runs:** every exit code was 0, with no crash report and no forced stop. Peak memory was
2,195 MB, free memory never fell below 36%, and swap stayed at 3,303 MB.

**The reference** for each state is whichever of these was nearer optimal: D aimed at 1e-10, or an alternating PGS
started from D's forces, at most 5,000 passes. Its natural residual has median 2.7e-13, p95 2.0e-8, and worst 1.5e-7.
D gave the reference on 1,619 states.

## Results on the 1,620 states

Velocity differences are against the reference, as worst cases. `F` and `T` are net tangential force and torque.

| Method | Natural residual, p99 and worst | `|Δv|`, cm/s | `|Δω|`, °/s | `|ΔF|` | `|ΔT|` | Single-wheel force gap, × μ Fz | Iterations, median / p99 / worst |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Engine | 6.2e-5, 1.2e-4 | 0.035 | 0.028 | 1,810 | 50,700 | 0.84 | 23 / 200 / 200 passes |
| A | 6.2e-5, 1.2e-4 | 0.035 | 0.028 | 1,810 | 50,700 | 0.84 | 23 / 200 / 200 passes |
| B | 6.3e-5, 3.0e-4 | 0.057 | 0.052 | 2,920 | 92,800 | 1.50 | 15 / 200 / 200 passes |
| B_res | 2.2e-7, 3.7e-6 | 8.2e-4 | 7.6e-4 | 42 | 1,370 | 1.50 | 10 / 2,000 / 2,000 passes |
| C | 2.1e-7, 2.7e-7 | 9.1e-6 | 7.9e-6 | 0.47 | 20 | 0.66 | 20,000 iterations, mostly at the limit |
| D | 5.8e-8, 1.5e-7 | 2.7e-8 | 8.4e-9 | 0.0014 | 0.051 | 0.27 | 45 / 157 / 393 Newton steps, plus fallback passes |
| E, γ 1e-6 | 6.3e-5, 3.0e-4 | 0.057 | 0.052 | 2,920 | 92,800 | 1.49 | as B |
| E, γ 1e-4 | 9.9e-5, 3.0e-4 | 0.057 | 0.051 | 2,900 | 92,600 | 1.15 | as B |
| E, γ 1e-2 | 9.5e-3, 9.9e-3 | 0.41 | 0.47 | 21,300 | 1,490,000 | 0.95 | 200 passes |

**Constraints held for every method on every state:**
- Friction circle, at most 4.2e-16 relative.
- Torque limits.

**Friction power over `Σ μ Fz` stayed at or below:**
- 4e-9 cm/s for D;
- 3e-7 for A, B, and C, where they had not converged;
- 5e-5 and 3.6e-4 for E at γ 1e-6 and 1e-4, which had not converged either.

**By window, the worst natural residual of the gated settings (A):**
- **Near 1e-8 or below:** C2 at 60 Hz, C3, and C5.
- **Larger:** 5e-6 to 9e-6 in C6 at 10° and C2 at 120 Hz, and 7e-5 to 1.2e-4 in the three C7 windows.

**The worst velocity errors.** The five worst steps for A lie in `c7_edge1`, steps 69–73. There A's velocity was off
by 0.033–0.035 cm/s and its net force by 1,690–1,810, about 0.6% of the weight. These are block-edge steps.

## Time and memory

Measured in Python 3.13.1, pure Python with no NumPy, one process. The machine is an Apple M4 Mac (Mac16,10), 16 GB,
macOS 27.0.1. Peak memory is Python's own allocations per solve, by `tracemalloc`. **These are prototype times. They
are not a measure of C++ cost, and they are not comparable with the Unreal solve's times.**

| Method | Turn, `c3_60_steady`: median / p95 / p99 / worst ms | C7 edge, `c7_edge1`: median / p95 / p99 / worst ms | Peak memory per solve |
| --- | --- | --- | --- |
| A | 39 / 43 / 45 / 46 | 3.5 / 41 / 43 / 48 | 17 KB |
| B | 39 / 43 / 45 / 45 | 2.3 / 42 / 45 / 50 | 17 KB |
| B_res | 2.3 / 416 / 436 / 438 | 2.5 / 415 / 430 / 440 | 17 KB |
| C | 374 / 795 / 806 / 809 | 735 / 765 / 781 / 782 | 19 KB |
| D | 12 / 1,058 / 1,091 / 1,093 | 12 / 15 / 19 / 683 | 63 KB |
| E, γ 1e-2 | 39 / 45 / 45 / 46 | 38 / 44 / 46 / 50 | 29 KB |

**D's tail is its fallback.**
- **How often:** D missed its 1e-8 target on 158 of 1,620 states and fell back to PGS. That was 53 of 120 in the
  steady turn at 120 Hz, and 87 of 360 in the C7 sample.
- **In the turn:** D's own residual there was 1e-8 to 5e-8, the floor of its pseudo-inverse cut at 1e-10. It was not
  wrong, only just above the target.
- **In the C7 sample:** neither D nor 5,000 PGS passes reached 1e-8 on its worst steps, which stopped near 1.5e-7.

## Short trajectories, 60 and 120 Hz

`scripts/contact_solver/simulate.py` stands in for the Unreal rig. It uses the same box, wheels, suspension, and step
order, with rays to a plane and gravity tilted for slopes. It has no sleep, and it differs from Unreal's sphere sweeps.
Each method drives its own trajectory:
- **Straight:** 50 cm/s, for 3 s.
- **Turn:** 28.178 °/s, for 4 s.
- **Climb:** 10°, for 3 s.
- **Hold:** 10° under a zero command, for 3 s.

Each command starts at 0.5 s. All 64 runs stayed finite.

| Method | Largest position gap to D at the same rate, worst over the four scenarios | 60 against 120 Hz, straight / turn / climb / hold | Turn: end yaw at 60 and 120 Hz | Slide switches, all runs |
| --- | --- | --- | --- | --- |
| A | 8.9e-7 cm | 0.218 / 3e-9 / 0.230 / 0.017 cm | 63.8307°, 63.7728° | 2–8 |
| B, B_res | 5.2e-7 cm | the same as A | the same | 2–12 |
| C | 8.2e-6 cm | the same | the same | 0–4 |
| D | 0 | the same | the same | 0–4 |
| E, γ 1e-6 | 2.4e-4 cm | the same | the same | 0–4 |
| E, γ 1e-4 | 0.016 cm | 0.218 / 6e-5 / 0.227 / 0.017 cm | 63.8209°, 63.7679° | 0–4 |
| E, γ 1e-2 | 1.6 cm | 0.187 / 4e-5 / 0.604 / 0.773 cm | 62.8475°, 63.2812° | 0–4 |

**What the table shows:**
- **The 60 against 120 Hz gap is the time step's own effect.** It is the same, to the digits shown, for every method
  that solves accurately: 0.22 cm going straight and 0.23 cm climbing.
- **In this rig, with symmetric ray contacts, PGS converges much better than on the Unreal states.** A's worst
  residual was 3.3e-6.
- **A and B switch between stick and slide more often than D does.** They do so near the boundary, where an
  unconverged force can sit a little inside or outside the circle.

## Regularization, E

A diagonal `γ diag(A)` makes the forces unique, but it is a compliance, and it costs physics:

| γ | Per step, worst `|Δv|` / `|ΔF|` against the reference | 3 s on a 10° slope under a zero command | Turn after 4 s |
| --- | --- | --- | --- |
| 1e-6 | 0.057 cm/s / 2,920, no better than B in 200 passes | Creeps 2.4e-4 cm | Yaw unchanged |
| 1e-4 | 0.057 / 2,900 | Creeps 0.016 cm | Yaw 0.010° lower |
| 1e-2 | 0.41 / 21,300 | Creeps 1.5 cm | Yaw 0.98° lower at 60 Hz, 0.49° at 120 Hz |

**What it costs:**
- **Holds become slow slides.** The slip is `u = −γ diag(A) x`.
- **Energy and the time step.** At γ 1e-2 the scheme's numerical dissipation changed by −1,940 to +257 per step
  against the reference. The 60 against 120 Hz gap on the hold grew from 0.017 to 0.77 cm.
- **It does not speed up PGS here.** With 200 passes, γ up to 1e-4 left the same worst velocity errors as B.

**Regularization is not recommended.**

## Sleep

The research states were collected with sleep off, and the Python rig has none. The earlier diagnostics measured
sleep itself, on and off; see [Chaos sleep, on and off](solver-diagnostics.md#chaos-sleep-on-and-off). Those runs
showed two effects:
- **Resets while slow.** Up to 132 resets in a C7 run, each removing up to 1.0 cm/s and 2.7 °/s.
- **A small difference on waking.** 1e-5 °/s.

Neither is a solver error, and no number on this page includes either.

## Worst cases

| Case | Where | What fails | Size |
| --- | --- | --- | --- |
| Gated PGS at a block edge | `c7_edge1`, steps 69–73 | 200 passes leave a residual of 6e-5 | Velocity off by 0.035 cm/s, net force by 1,810 |
| Alternating PGS on a random-drive step | `c7_sample` | 2,000 passes, residual 3.7e-6 | Velocity off by 8e-4 cm/s |
| D on a steady turn | `c3_120_steady` | Residual floor 1e-8 to 5e-8, just above the 1e-8 target | The 5,000-pass fallback, about 1 s in Python |
| D at a contact sliding at nearly zero slip | `c7_edge1`, step 124 | Newton's `1/|u|` term is too stiff to converge | Solved by the fallback |
| D and PGS both | `c7_sample`, steps 245–336 | Neither reaches 1e-8 | Residual 1.2e-7 to 1.5e-7; velocity within 6e-10 cm/s of the reference |
| FISTA | Every window | Rarely reaches 1e-8 in 20,000 iterations | Velocity off by up to 9e-6 cm/s |

## Porting D to C++: a design, not built

- **Data.** Fixed-size arrays: `q` (12), `M` blocks, up to 12 contact rows and 6 motor rows. No heap use per step.
- **Predictor.** Smoothed Newton with ε from 10 to 1e-5 cm/s. Each iteration forms a 12 × 12 Hessian and factors it
  by Cholesky. In Python this took 20–40 iterations.
- **KKT Newton.** The same 12 × 12 factorization, then a Schur complement over up to 18 sticking and holding rows,
  solved by a pseudo-inverse. A Jacobi eigen-decomposition of 18 × 18 can be replaced by a rank-revealing
  factorization (LDLᵀ with pivoting, or QR) and should be.
- **Fallback.** The existing PGS, warm-started from D's forces, with a residual stop. It also covers the cases above.
- **Wiring.** Replace `SolveWheels`'s pass loop, behind a flag, with the gated PGS kept as it is. The step order,
  forces through `AddForceAtLocation`, and every record stay the same.
- **Expected cost.** Arithmetic per Newton step is a few thousand multiply-adds, and the predictor and KKT stages
  need 40–160 steps. That suggests well under 1 ms per step in optimized C++. This is an estimate to be measured, not a
  result. The fallback's tail would remain.

## Recommendation, and what it would need

**Recommended for the next phase:**
- D, with alternating PGS and a residual stop as its fallback.
- Convergence judged by the natural residual.

**Why:**
- D was the only method whose velocities matched the reference to 3e-8 cm/s on all 1,620 states.
- Its typical cost in Python is 12 ms, and its tail is the fallback.
- B_res is the cheaper option if a residual near 4e-6 at the worst steps is acceptable.

**What it would need before any C++ work is approved:**
1. **Make D's own residual reach its target.** That means a rank-revealing factorization in place of the cut
   pseudo-inverse, or a polish step, so that the turn does not fall back. This can be done in Python first.
2. **Handle contacts sliding at nearly zero slip** without the fallback. One option is a Newton step on the disk's
   boundary.
3. **Measure the C++ cost,** in the rig itself, with the gated settings kept for comparison.
4. **Decide whether to model the motor's reaction on the body.** That is a physics change, not a solver change.
5. **Register any new criteria before a new gated run.** The candidate is a natural residual bound in place of the
   last-change rule.

**Re-running phase C now is not recommended.** No solver change is approved for Unreal. A re-run with the gated
solver and criteria would fail again on the same rule. The slow turn needs its own decision, on the motor limit or on
the turn criterion, apart from the solver.

## Code

| File | Role |
| --- | --- |
| `scripts/contact_solver/problem.py` | The step as a problem in generalized velocities, from a dumped input, with every check in `evaluate` |
| `scripts/contact_solver/methods.py` | Methods A to E |
| `scripts/contact_solver/compare.py` | Runs every method on saved states, with warm starts carried along each window |
| `scripts/contact_solver/simulate.py` | Short trajectories in a Python stand-in for the rig |
| `scripts/contact_solver/test_contact_solver.py` | Unit tests, run by `python -m unittest discover -s scripts -p "test_contact_solver.py" -t scripts`; CI does not run them |
| `WheelRig.cpp`, `WheelSpikeGameMode.cpp` | `-WheelDumpEvery`, `-WheelDumpFrom`, `-WheelDumpTo`: one JSON line per step, with the engine's result. Diagnostics only; the gated path is unchanged |
