# Wheel model: a diagnostic mode for method D in Unreal, a design

**Status.** A design only, written on 2026-11-04 after the [verification of improved D](solver-d-verification.md).
- **Nothing is built.**
- **The gated solver stays the default** and is not changed.
- **The owner's approval is needed** before any of this is added to `unreal/`.
- **Unaffected:** phase C's verdict, its criteria, the 60 N m motor limit, and ADR 0014.

## Aim

Run improved D inside the rig as a diagnostic, behind a command-line flag, to measure three things in the engine's
own contact geometry and timing:
- **its time per step,** under a budget;
- **its residual and stalls;**
- **its difference from the gated solver,** step by step.

Gated runs keep the gated solver, with no change to any record.

## Flags

| Flag | Effect | Default |
| --- | --- | --- |
| `-WheelSolver=pgs\|d\|shadow` | `pgs` applies the gated solver; `d` applies D; `shadow` applies the gated solver and also solves with D for comparison only | `pgs` |
| `-WheelDBudgetUs=<n>` | D's wall-time budget per step | 1000 |
| `-WheelDReject=<r>` | Natural residual above which `MakeSafe` rejects D's answer | 1e-3 |

With no flag, the rig must behave exactly as now. That is checked cell by cell against the phase C records, as was
done for the solver diagnostics.

## Where it runs in the step

- **No change to timing.** The rig solves in the game mode's pre-physics tick. It reads the body state from the last
  step, solves, and applies forces with `AddForceAtLocation` for the coming step. D would run at the same point, with
  the same inputs that `SolveWheels` gets, and its forces would be applied the same way. Fixed step only, with no
  substeps, as now.
- **The generalized velocities are built from what the rig already has:** `FBodyState`, the contacts, the commands,
  and the spins.
- **D returns the same per-wheel results** as `SolveWheels`: forces, torques, spins, and slips. Records keep their
  columns.

## Memory

D uses fixed-size arrays only. In the standalone build it made zero heap allocations per solve. In Unreal it would sit
in the `WheelSpike` module as plain C++, with no `TArray` in the solve. The rig's own per-step arrays would stay as
they are.

## Time

**Budget and stop rule.**
- **The budget** is `-WheelDBudgetUs` per step, with the predictive stop from the standalone build: a unit is not
  begun if it might end past the budget, less a 5 µs reserve.
- **Every step records:**
  - the wall time of the D solve;
  - whether the budget was reached;
  - the Newton steps, rounds, and fallback passes.
- **The measurements decide.** Preemption is outside the solver's control, so whether D fits a 60 Hz frame is judged
  from those records, not assumed.

## Fallback and switching back

Within one step, in order:
1. **D.** If its natural residual meets the target, use it.
2. **D's fallback.** Alternating PGS from D's answer, within what remains of the budget.
3. **`MakeSafe`** checks the result:
   - for non-finite values;
   - for a force or torque beyond its limit;
   - for a natural residual above `-WheelDReject`;
   - for implausible speeds.
4. **If rejected, the gated PGS solve of the same step.** It is always feasible, and its answer is applied.

**Run-wide.** After any rejection, or any step over twice the budget, the run continues with D. The step is counted
and logged. Switching back is per step, so no state is carried between solvers except the wheels' spins, which both
update the same way.

## Logs and records

**New CSV columns, written only with the flag:**

| Column | Meaning |
| --- | --- |
| `d_us` | The D solve's wall time |
| `d_natural` | Its natural residual |
| `d_budget_hit` | Whether it reached its budget |
| `d_fallback_passes` | Passes spent in its fallback |
| `d_rejected` | Whether `MakeSafe` rejected it |
| `d_contact_states` | Each wheel's stick, slide, or no contact, and each motor's hold or saturation |
| `pgs_natural`, `dv_d_pgs` | In shadow mode: the gated solve's residual, and the velocity difference between the two |

**Run summary.** The run's JSON summary gains counts of budget hits, rejections, and stalls above 1e-8, with time
quantiles. `numerics` in `scripts/wheel_spike.py` would report them, as it reports sleep today.

## A first diagnostic plan, if approved

- **Shadow mode** on C2, C3, C5, C6 at 10°, and C7, at 60 and 120 Hz, with sleep off as in the research runs. This
  measures time and agreement without changing any trajectory.
- **Then `d` mode** on the same runs, as diagnostics. Their records go to a new batch, never over a gated one.
- **No gated run, and no new criteria,** until the owner decides on both.

## Risks

- **Stalls in engine geometry.** The constraint inconsistency behind the 37-state floor may be common. D would then
  meet its budget often, at a residual near 1e-8.
- **Time.** The physics thread's time may differ from the standalone build's.
- **Logging.** Shadow mode doubles the solve work and adds logging; its times are not D's alone.
