# Wheel model: the motor's reaction on the body, a design memo

Not implemented. The owner asked on 2026-11-04 for a memo on this issue, which the solver research found: the motor
torque acts on the wheel, and no reaction acts on the body. No Unreal code, model, criterion, or record changed.

## What the model does now

Wheel `i` has spin `ω_i` and inertia `I_w`, axle direction `a_i` (the body's lateral axis), and contact point `c_i`
with ground force `F_i` in the contact plane. `WheelModel.cpp` does three things:

| On | Applied |
| --- | --- |
| The wheel | `I_w dω_i/dt = τ_i − F_f R` |
| The body | `F_i` at `c_i`, so the torque about the center of mass is `(c_i − x) × F_i` |
| The body, from the motor | Nothing |

## What a motor between body and wheel does

The wheel turns on a bearing at its hub, `h_i = c_i + R n_i`. The motor, fixed to the body, turns it.

| On | Physically |
| --- | --- |
| The wheel | `I_w dω_i/dt = τ_i + ((c_i − h_i) × F_i)·a_i`, the motor torque and the ground's couple about the hub |
| The body | `F_i` at the hub, `(h_i − x) × F_i`, and `−τ_i a_i` from the motor |

**Rewriting the body's torque** with `c_i = h_i − R n_i`:
- `(c_i − x) × F_i = (h_i − x) × F_i − R n_i × F_i`.
- **The model's body torque less the physical one** is `−R n_i × F_i + τ_i a_i`.
- For a force along the wheel's forward direction, `−R n_i × F_i` about the axle is `−F_f R`.
- **So the difference** about the axle is `τ_i − F_f R`, which is `I_w dω_i/dt`.

**The model's error on the body** is therefore the wheel's own spin-up torque, `Σ I_w (dω_i/dt) a_i`:
- **At steady spin it vanishes,** with `τ_i = F_f R`. There, applying the force at the contact point gives the body
  exactly the couple that the motor's reaction would.
- **It is not zero while a wheel speeds up or slows down.**

**Angular momentum.**
- Of the body and wheels together, it should change only by the external torque `Σ (c_i − x) × F_i`.
- In the model it changes by that plus `Σ I_w (dω_i/dt) a_i`, so it is not conserved while wheels spin up.
- **A correction.** The solver research said the motor's reaction is missing entirely. That overstated the error: most
  of the reaction already reaches the body through the contact-point force.

## Its size, from the 1,620 saved states

Computed from each state's engine result as `Σ I_w (Δω_i / dt) a_i`, and from the body acceleration it would add as
`I⁻¹` times that. Nothing was re-simulated.

| Window | Error torque, kg cm²/s²: median, worst | Body angular acceleration it would add, °/s²: median, worst |
| --- | --- | --- |
| C2 start, 60 and 120 Hz | 0, 4.1e5 | 0, 8.0 |
| C3 turn, all windows | below 0.5 | 0, 0 |
| C5 settling on 10° | below 0.003 | 0, 0 |
| C6 start on 10° | 3.9e4, 3.7e5 | 0.75, 7.2 |
| C7 windows | 35 to 1,411; 1.4e4 to 1.2e5 | up to 2.4 |

**Where it appears.**
- **When driving starts.** The wheels spin up from rest at the motor's limit, in C2 and C6.
- **Not in the turn.** Left and right wheels spin up in opposite directions about the same axle, so the error cancels.
- **Not in holds.** The spins barely change.

A naive count of `Σ τ_i a_i`, which ignores the contact-point couple, gives up to 70 °/s². It is not the error.

**Possible link to C2's failure, not tested.** The error is largest exactly when C2 starts. That is also when C2's
body pitches by 0.72° and its center's speed peaks at 55.29 cm/s. Whether the error changes that peak is unknown.

## A correction, if approved

In the generalized-velocity form of the [solver research](solver-research.md), the motor row of wheel `i` would
become `(0, −a_i, e_i)` in place of `(0, 0, e_i)`. Then:
- **The motor's impulse** turns the wheel and turns the body back about the axle.
- **The wheel's spin is measured relative to the body,** as a motor drives it.
- **The wheel's kinetic energy** then also depends on the body's rotation, so `M` gains off-diagonal terms between
  `ω` and the wheel spins.
- **In `WheelModel.cpp`,** this adds `−τ_i a_i` to the body's torque each step, and includes the body's yaw rate
  about each axle in the motor's target.

## Proposed experiments, before and after

None was run.

1. **Python, without Unreal.**
   - Add the motor row's body term to `scripts/contact_solver`.
   - Drive the stand-in rig on C2, C3, C6, and a hold, with and without the term, at 60 and 120 Hz.
   - Record pitch, the peak of the body center's forward speed, the yaw rate, and the total angular momentum of body
     and wheels.
   - Expect the total to change only by the external torque, to rounding, once the term is in.
2. **Conservation test.** With no ground contact, spin the wheels up with the motors. Today the body does not move.
   With the term, the body counter-rotates, and the total angular momentum stays at its start value.
3. **Unreal, only if the owner approves a model change.**
   - Repeat C2 and C6 as diagnostics.
   - Record the same quantities, then decide whether a new attempt of any phase is warranted.
   - Phase C's recorded verdict would not change.

## What this does not change

- The 60 N m motor limit and all of phase C's criteria and records.
- **The turn's shortfall.** It is set by the motor's limit and friction, and the error is zero in the turn.
- Anything in the Python Mission Core.

## Experiment, 2026-11-04: before and after, in the Python stand-in rig

The owner approved a numerical experiment on 2026-11-04, outside Unreal. `scripts/contact_solver/reaction.py` drives
the [Python stand-in rig](solver-research.md#short-trajectories-60-and-120-hz) with two models, both solved by method
D:
- **current:** as `WheelModel.cpp`.
- **coupled:** each wheel's spin is taken relative to the body, and its kinetic energy is `½ I_w (σ_i + a_i·ω)²`.
  - The mass matrix then couples the body's rotation to each spin about its axle.
  - The motor's reaction on the body follows from that coupling, with no added term.
  - Contact slip is unchanged, because it already uses the relative spin.

**What is measured.** Angular momentum of body and wheels about the center of mass, `L = I ω + Σ I_w (σ_i + a_i·ω) a_i`,
is checked each step against the ground's torque times `dt`. The **balance** is the largest difference.

| Scenario | Model | Largest pitch | Largest pitch rate | Peak forward speed of the center | Angular momentum balance, largest per step |
| --- | --- | --- | --- | --- | --- |
| Start, 50 cm/s from 0.5 s | current | 1.1898° | 6.105 °/s | 55.263 cm/s | 6.9e3 |
| | coupled | 1.2017° | 6.308 °/s | 55.314 cm/s | 1.5e-10 |
| Stop, brake from 1.5 s | current | 1.4732° | 8.558 °/s | 55.263 cm/s | 4.3e4 |
| | coupled | 1.4892° | 8.594 °/s | 55.314 cm/s | 2.4e-10 |
| Climb 10° from 0.5 s | current | 1.3341° | 3.351 °/s | 53.331 cm/s | 6.3e3 |
| | coupled | 1.3403° | 3.563 °/s | 53.355 cm/s | 1.2e-10 |
| Turn in place | current | 0 | 0 | 0 | 3.3e-10 |
| | coupled | 0 | 0 | 0 | 3.3e-10 |
| No ground, wheels spun up | current | 0 | 0 | 0 | 4.5e4 |
| | coupled | 0.6054° | 0.865 °/s | 0 | 3.6e-12 |

Figures are at 60 Hz. At 120 Hz they agree to within 0.01°, 0.2 °/s, and 0.02 cm/s, and the balances are of the same
orders.

**What it shows:**
- **The coupled model conserves angular momentum to rounding.** The current one does not while wheels spin up or slow
  down, as the analysis above predicted.
- **The turn yaws at 18.9798 °/s in both models.** It is unchanged and needs no correction.
- **Pitch at the start changes by about 0.01°, and the center's peak speed rises by 0.05 cm/s.** The missing reaction
  does not explain C2's 55.29 cm/s peak, and correcting it would raise that peak slightly.
- **Without ground, only the coupled body counter-rotates,** by 0.6° in 0.7 s, as a free body must.

No Unreal model was changed. Adding the coupling to `WheelModel.cpp` would be a model change and needs the owner's
approval.
