# Wheel model: method D in C++, standalone

The owner approved a C++ research build of method D on 2026-11-04, after the
[Python solver research](solver-research.md). It is a standalone program, with no engine code and no change to
Unreal's solver, criteria, or records. Phase C stays failed, 2 of 9. ADR 0014 stays Proposed.

**The motion in these results** is that of a game-style wheel model. It says nothing about real rovers or regolith.

## Build and inputs

**Code.** `scripts/contact_solver/cpp/`:
- **`wheel_solver.h`, `.cpp`:** the problem, the checks, PGS, and D.
- **`tests.cpp`:** unit tests on synthetic six-wheel states.
- **`bench.cpp`:** the benchmark.
- **`build.sh`:** builds with the system's Apple clang 21, `-std=c++17 -O2`. No library is used beyond the C++
  standard library.

**Memory.**
- Every solver uses fixed-size arrays.
- A counting `operator new` in the benchmark saw **0 heap allocations** in every timed solve, for every method.
- The whole benchmark, with all 1,620 states loaded, peaked at 9.4 MB of resident memory.

**States.** The same 1,620 saved states from `solverresearch-20261104/states`, exported by
`scripts/contact_solver/export_states.py` to plain numbers. The export also holds Python method D's answer for each
state.

**Machine.** Apple M4 Mac (Mac16,10), 16 GB, macOS 27.0.1. One process, one thread.
- **Repeats.** Each state is solved 5 times by each method, and the median is reported.
- **Clock.** `steady_clock`, read around the solve alone.
- **Warm starts.** Warm-started methods carry their own last answer along each window, as in Python.

## Matching the Python prototype and the engine

| Check | Result |
| --- | --- |
| C++ PGS (method A) against the engine's own forces | Natural residual identical to 3.6e-14 on every state |
| C++ D, written as the Python prototype (`D_py`), against Python D | Velocities within 2.5e-9 on every state |
| Steps where `D_py` falls back to PGS | 158, the same count as Python |
| C++ unit tests, `tests` | 37 checks, 0 failures: D alone reaches 1e-12 on four synthetic states with both multiplier kinds; limits, friction work, and energy identity hold; D and a converged PGS give the same velocities to 3e-13 or better; a sliding force opposes its slip |
| Python unit tests, `test_contact_solver.py` (not run by CI) | 7 tests, OK, 7.3 s, on 2026-11-04 |

## Improving D, and what did not work

Each variant below runs without its fallback, so that D's own result shows.

| Variant | States above 1e-8 | Above 1e-6 | Worst residual | Worst velocity error, cm/s |
| --- | --- | --- | --- | --- |
| As Python: Jacobi pseudo-inverse, cut at 1e-10 of the largest eigenvalue | 158 | 1 | 2.0 | 0.37 |
| Cut at 1e-6, 1e-8, or 1e-12 instead; with or without refinement in the kept eigenspace | 158–159 | 1–2 | 2.0 | 0.37 |
| Tikhonov `(S + δI)` with refinement, in place of the cut | 806 | not run alone | 2.0 | 3.7 |
| **Floor `|z|` at 1e-6 cm/s in a sliding term's Hessian, with a residual line search** | **37** | **0** | **4.8e-8** | **2.5e-7** |
| The same floor at 1e-7 or 1e-8 | 37 | 0 | 4.8e-8 | 1.1e-9 |
| The same floor at 1e-5, or at 1e-4 | 124, 171 | 0, 1 | 6.4e-7, 1.2e-2 | 9.3e-7, 1.8e-2 |

**What this shows:**
- **The rank decision was not the cause.** Any cut from 1e-6 to 1e-12 gave the same result.
- **Tikhonov made things worse.** Nearly dependent rows that are not quite consistent got large multipliers. Those
  multipliers left their disks, and the guess of which terms stick then broke.
- **The cause was Newton itself.** It diverged or stalled on sliding terms whose `1/|z|` Hessian is very stiff. The
  floor keeps the step bounded, and the line search on the residual of the conditions keeps it descending.
- **The adopted variant, `D_imp`:** the pseudo-inverse cut at 1e-10, the floor at 1e-6 cm/s, and the line search.

## Methods compared

| Name | What it is | Stop |
| --- | --- | --- |
| A | Gated PGS: forward order, 200 passes | Last change below 1e-7 cm/s |
| B | PGS, alternating order, warm start | The same |
| B_res | B with a residual stop | Natural residual ≤ 1e-8, or 2,000 passes |
| D_py | D as the Python prototype, with its PGS fallback | Target 1e-8; fallback at most 5,000 passes |
| D_imp_alone | Improved D, no fallback | Target 1e-8, or its rounds and flips run out |
| D_imp | Improved D with the fallback | As D_py |
| D_imp_1ms, D_imp_2ms | Improved D with hard budgets: at most 300 or 600 Newton steps, 1 or 2 ms of wall time checked every Newton step and fallback pass, and at most 200 or 600 fallback passes | Target 1e-8, or a budget; then the best answer so far |

## Results on 1,620 states

Velocity error is against the most nearly optimal answer for each state among all methods and Python D.

| Method | Natural residual, p99 / worst | States above 1e-8 | Worst velocity error, cm/s | Iterations, median / p99 / worst | Fallbacks | Time per solve, µs: median / p95 / p99 / worst |
| --- | --- | --- | --- | --- | --- | --- |
| A | 6.2e-5 / 1.2e-4 | 406 | 0.035 | 23 / 200 / 200 passes | | 191 / 2,133 / 2,832 / 3,028 |
| B | 6.3e-5 / 2.9e-4 | 357 | 0.057 | 15 / 200 / 200 | | 156 / 2,142 / 2,823 / 3,107 |
| B_res | 2.2e-7 / 3.7e-6 | 324 | 8.2e-4 | 10 / 2,000 / 2,000 | | 124 / 21,614 / 23,134 / 29,276 |
| D_py | 5.8e-8 / 1.5e-7 | 157 | 3.9e-6 | 45 / 246 / 601 Newton steps | 158 | 108 / 55,014 / 57,378 / 75,490 |
| D_imp_alone | 1.8e-8 / 4.8e-8 | 37 | 2.5e-7 | 45 / 158 / 335 | 0 | 109 / 464 / 807 / 1,940 |
| D_imp | 1.8e-8 / 4.8e-8 | 37 | 2.5e-7 | 45 / 158 / 335 | 37 | 108 / 461 / 54,918 / 58,313 |
| D_imp_1ms | 1.8e-8 / 1.4e-7 | 40 | 3.7e-6 | 45 / 158 / 175 | 40 | 102 / 450 / 1,006 / 1,028 |
| D_imp_2ms | 1.8e-8 / 4.8e-8 | 38 | 4.1e-7 | 45 / 158 / 181 | 38 | 102 / 450 / 2,006 / 2,031 |

The last two rows come from a separate run of A, D_imp, and the two budgeted variants, after the budget was made a
hard check. In that run A's figures were within 4% of those above.

**Limits held everywhere.**
- The friction circle was never exceeded beyond 4.2e-16 (relative), and torque limits never at all.
- Friction power was at most 1.9e-2 kg cm²/s³, about 1e-7 cm/s over `Σ μ Fz`, from A and B where they had not
  converged.
- The energy identity held to 8.7e-10 kg cm²/s².

**The fallback's cost.** It was 58 to 76 ms at worst, for up to 5,000 passes. With budgets, it was capped at 245 µs
(1 ms run) and 1,256 µs (2 ms run).

**Time by window, median and worst, µs:**

| Window | A | D_imp_alone |
| --- | --- | --- |
| C2 start, 60 and 120 Hz | 1.0 and 0.9; 822 and 743 | 143 and 141; 198 and 286 |
| C3, all three | 2,126; 2,324 to 2,922 | 105 to 107; 798 to 994 |
| C5 settling | 6.5; 461 | 189; 352 |
| C6 start | 247; 744 | 138; 348 |
| C7 windows | 126 to 1,798; 2,125 to 3,028 | 98 to 109; 202 to 1,940 |

**What the timings show:**
- **A is near free when its first passes meet the stop rule.** In the turn, it spends all 200 passes on every step,
  about 2.1 ms.
- **D_imp_alone costs about 100–190 µs** in every window.
- **The unbounded fallback costs 55 ms or more.** That is beyond any frame budget.

**The Unreal solve, for scale.** The [solver diagnostics](solver-diagnostics.md) timed the solve inside Unreal, built
on `TArray` and `FVector`, at 1.6 ms median in the turn and 2.2 ms in C7 with the gated settings. It is a different
build from the standalone A above, so the two are not compared directly.

## The fallback states

**The states of D as in Python:**
- It fell back on 158 states, and 157 of them ended above 1e-8.
- **Where the 157 were:** 87 in the C7 sample, 53 in the steady turn at 120 Hz, 15 in the turn's other windows, and
  2 in C2 at 120 Hz.
- **The improved Newton step removed 120 of them,** including 86 of the C7 sample's 87.
- **So those 120 were Newton failing to converge** on stiff sliding terms. They were not a matter of rank or
  tolerance.

**The 37 that remain for the improved D:**
- 26 in the steady turn at 120 Hz, 8 in the turn's other windows, 2 in C2 at 120 Hz, and 1 in the C7 sample.
- **Not small slips.** None has a sliding contact slower than 1e-3 cm/s; the median slowest is 36 cm/s.
- **Not near a switch.** No sticking contact is above 0.99 of its circle, and no motor sits between 0.99 and 1 of
  its limit.
- **The turn's geometry.** They are the turn in place: four corner wheels scrubbing on their circles, the middle
  wheels sticking at the motor's limit, and twelve rows on six body freedoms.
- **The size.** D's residual stalls at 1e-8 to 4.8e-8 there. The velocities are still within 2.5e-7 cm/s of the
  reference.

**What is not established is why it stalls there.** One candidate is rounding in the Schur complement of the middle
wheels' dependent lateral rows. This was not proven.

## Bounding the worst time

D's work can be capped at four points, all present in `DOptions`:
- Newton steps across all stages: `MaxNewtonTotal`.
- Active-set rounds: `MaxRounds`.
- Fallback passes: `FallbackPasses`.
- Wall time: `MaxSeconds`, checked at every Newton step and every fallback pass.

When a cap is reached, the best answer so far is returned, and `BudgetHit` says so.

**How well it held:**
- **The cap's overshoot.** It is at most one Newton step or one pass. At 1 ms the worst solve took 1.028 ms, and at
  2 ms it took 2.031 ms.
- **The accuracy cost at 1 ms.** 40 states end above 1e-8 instead of 37. The worst residual is 1.4e-7, and the worst
  velocity error is 3.7e-6 cm/s. That is still four orders of magnitude better than A's 0.035 cm/s.

**A design for Unreal, not built:**
- Run D under a per-step wall budget, with the gated PGS as the last resort.
- Record `BudgetHit` and the natural residual every step, so a run shows every step where accuracy was traded for
  time.

## Unresolved

- **The turn's stall.** The 37 steady-turn states stall between 1e-8 and 4.8e-8. Their cause is not proven.
- **Untested inside Unreal.** Its 60 Hz frame, threads, and other work may change the times above.
- **No trajectories.** D has not driven a trajectory in C++. Its step-by-step stability over time was only shown in
  Python.
- **The target is a choice.** 1e-8 has not been registered as a criterion, and changing it needs the owner.
