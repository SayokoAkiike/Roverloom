# Wheel model: where method D's 37 stalls come from

**Research closed on 2026-11-07, by the owner's decision,** after the X2 and single-precision checks below. The next
steps proposed here are recorded, not scheduled.

The owner approved this analysis on 2026-11-07. It uses only saved data: no Unreal run, no long simulation, and
no change to any solver, criterion, or record. Phase C stays failed, 2 of 9; ADR 0014 stays Proposed; the motor
limit stays 60 N m. **This is a game-style wheel model; nothing here is checked against a real rover or regolith.**

## Registered plan

Written and committed on 2026-11-07, **before any of the measures or variants below was computed.** What was
already known is only what the [verification](solver-d-verification.md#why-37-states-stall-above-1e-8) reports:
the 37 states' sticking and holding rows are dependent and slightly inconsistent, 37 of 37 have a dependent direction
against 11 of 40 converged states, and no method tested goes below about 1e-8 there.

### Question

Is the inconsistency a property of the contact geometry that the engine hands the solver (contact points,
normals, and the forward and lateral directions), or of the model's own rows, or of the solver?

### Data

From `unreal/Saved/WheelSpike/`, read only:
- `solvercpp-20261104/data/states.txt`: the 1,620 saved states, one per line, line numbers from 0.
- `solvercpp-20261104/stall37.txt`: the 37 stalled lines. `good40.txt`: the 40 converged lines used before.

New output goes to a new batch, `geomprobe-20261107/`. Nothing existing is written.

### Groups

- **S:** the stalled states. Recomputed here with improved D alone (floor on, no fallback, target 1e-8) on the
  original states. If the recomputed set differs from `stall37.txt`, the difference is reported and the recomputed
  set is used.
- **W:** converged states in the windows where a stall occurs. The matched control.
- **A:** every converged state.

### Measures from the inputs alone, for every state

The body's axes are estimated from the inputs, which hold no orientation: `x` along the mean forward direction of
wheels in contact, `z` along their mean normal, `y = z × x`. Wheel order is taken from the stand-in rig, 0–2 on
one side and 3–5 on the other, front to back, and is checked against the data before use; if it differs, the data's
order is used and reported.

| Name | Measure |
| --- | --- |
| M1 | Normal spread: the largest angle between a contact normal and the mean normal, in degrees |
| M2 | Planarity: the largest distance of a contact point from the plane through their centroid with the mean normal, cm |
| M3 | Frame error: over wheels in contact, the largest of `|f·n|`, `|l·n|`, `|f·l|`, and each vector's length less 1 |
| M4 | Mirror asymmetry: over the pairs (0,3), (1,4), (2,5), the largest difference of `r·x`, `|r·y|`, and `r·z`, cm, with `r` from the center of mass |
| M5 | Middle pair: the angle between the lateral directions of wheels 1 and 4, in degrees, and the difference of their `r·x`, cm |
| M6 | Load imbalance: the largest difference of normal force within a mirror pair, over the mean normal force |

### Measures at improved D's answer

Over the sticking contacts (2 rows each) and holding motors (1 row each), with `S = G M⁻¹ Gᵀ`, as in `probe.cpp`:
the number of held rows; the number of eigenvalues at or below 1e-12 of the largest; the smallest such ratio; the
largest `|v·z|` along those directions; and the wheels whose rows make up more than 10% of the worst such direction.

### Variants

Each variant rewrites the inputs of every state and solves again with improved D alone.

| Name | Change |
| --- | --- |
| V0 | None. The reproduction |
| V1 | Every contact normal replaced by the mean normal |
| V2 | Each wheel's forward and lateral directions made orthonormal against its own normal, keeping the forward direction's heading |
| V3 | Every contact point projected onto the plane through the centroid with the mean normal |
| V4 | V1 and V3, then V2 against the mean normal: one consistent plane |
| V6 | Control: each state's inputs moved by the same size as V4's change, in a random direction, with a fixed seed |

For each variant: how many of S fall to 1e-8 or below (**resolved**); how many of A rise above 1e-8 (**broken**);
and the largest change of the solved velocities against V0, per state.

### How the answer is decided

| Finding | Rule |
| --- | --- |
| **Geometry causes the stall** | V4 resolves at least 30 of 37, breaks at most 1% of A, and V6 resolves at most half as many as V4 |
| **One part of the geometry** | V1, V2, or V3 alone meets the same rule. Otherwise the cause is called combined |
| **Not the geometry** | V4 resolves 10 or fewer. The model's rows or the arithmetic stay as candidates, to be tested next |
| **Inconclusive** | V4 resolves 11 to 29, or V6 resolves more than half as many as V4 |
| **Association only** | For M1–M6, a measure is called associated if S's median exceeds the 90th percentile of W. This never decides cause by itself |
| **A large correction** | If V4 changes any S state's velocities by more than 1e-3 cm/s, the ideal geometry is not a small change, and this is reported beside the finding |

Solver-specific causes are not tested again. The verification already found the same floor with 50,000 PGS passes
and with every pseudo-inverse cut from 1e-6 to 1e-12. If V6 resolves about as many as V4, that points to
conditioning, a knife-edge, rather than geometry.

### What follows from each finding

These do not decide method D's adoption. That needs the shadow runs in
[release gate G1](../../release-gates.md#g1-drive-model-decision).
- **Geometry:** the floor should be expected in engine geometry, sized by the measures above. Next: count, in shadow
  mode, how often it happens, and test whether making the contact frames consistent in the rig removes it.
- **Not the geometry:** next, test the rows themselves: the motor targets, and the spin coupling in the forward row.
- **Inconclusive:** report it, and propose one smaller test. Do not widen the analysis without the owner.

### Tools

- `scripts/contact_solver/geometry.py`: the measures and the variants, in plain Python.
- `scripts/contact_solver/cpp/geom.cpp`: solves each state with improved D and writes the residual and the
  consistency measures, one CSV row per state.

## Results

Run on 2026-11-07, on a MacBook Air (Apple M5, 16 GB, macOS 27.0.1), Apple clang 21 at `-O2`, Python 3.12.16.
Batch `geomprobe-20261107/`, outside Git: the six rewritten state files, one CSV per variant from `geom`,
`summary.json` for the registered part, and `explore.json` for the exploratory part. The whole analysis took a few
seconds.

### Registered part

**Reproduction.** Improved D alone on the original states stalls on the same 37 lines as `stall37.txt`, no more and
no fewer. V0's rewritten file is byte-identical to the original. The assumed wheel order holds in all 1,597 states
with six contacts.

**Groups.** S: 37, in `c3_120_steady` 26, `c3_60_onset` 5, `c3_60_steady` 3, `c2_120` 2, `c7_sample` 1.
W: 881 converged states in those windows. A: 1,583.

**The geometry the engine hands the solver is already nearly ideal:**

| Measure | S, median | W, median | W, 90th percentile | Associated |
| --- | --- | --- | --- | --- |
| M1, normal spread | 0° | 0° | 0° | No |
| M2, planarity | 6.4e-6 cm | 6.4e-6 cm | 8.3 cm | No |
| M3, frame error | 0 | 1.6e-24 | 2.2e-16 | No |
| M4, mirror asymmetry | 9.8e-6 cm | 1.3e-5 cm | 10 cm | No |
| M5, middle pair's lateral angle | 0° | 0° | 0° | No |
| M5, middle pair's offset along x | 6.0e-6 cm | 2.5e-6 cm | 1.9e-4 cm | No |
| M6, load imbalance | 6.4e-8 | 8.2e-7 | 1.29 | No |

Normals are identical across wheels, and the frames are orthonormal to rounding. W's large 90th percentiles come
from its step-edge windows, where wheels really are at different heights.

**Consistency at D's answer.** All 37 of S have a dependent direction, and so do 584 of W's 881. The slip along
it is 1.4e-6 cm/s at the median in S, against 3.7e-10 in W. The worst direction is made of the **middle pair,
wheels 1 and 4, in 36 of 37**; the other is wheels 1 and 2.

**Variants:**

| Variant | S resolved | A broken | Largest velocity change in S |
| --- | --- | --- | --- |
| V1, one normal | 0 of 37 | 0 | 0 |
| V2, orthonormal frames | 0 | 0 | 1.2e-16 cm/s |
| V3, one plane | 2 | 2 (0.13%) | 4.0e-8 cm/s |
| V4, all of these | 2 | 2 (0.13%) | 4.0e-8 cm/s |
| V6, random control | 5 | 30 (1.9%) | 3.1e-7 cm/s |

**Finding under the registered rules: not the geometry tested.** V4 resolves 2 of 37, at or below the threshold
of 10. Normals, planarity, and frames are not the cause.

**One ambiguity in the rules, reported as found.** The "inconclusive" row also names V6 resolving more than half
as many as V4, and V6's 5 is more than half of V4's 2. That clause was written to tell geometry from a knife-edge
when V4 succeeds. Here both resolve few, so the finding above stands. The ambiguity is in how the rules were written,
not in the data.

### Exploratory part, after the registered result

**Not registered. These checks were chosen after seeing the result above, so they are hypotheses, not findings.**

**1. The slip left along the dependent direction is the yaw rate times the middle pair's offset.** The two middle
wheels sit at the body's center along `x`. Their lateral rows, `l·v + (r × l)·ω`, are then identical except for a
yaw term, the yaw rate times the difference of their `r·x`. Along `(1, −1)/√2`, the slip left over should be
`|ω_z Δx| / √2`.
- Over the 37 states, the measured slip over that prediction is 1.0000000 at the median and 1.0000002 at the
  90th percentile. The one exception is the state led by wheels 1 and 2.
- The offset is about 6e-6 cm, and the yaw rate in the turn about 0.33 rad/s. Together they give the 1.4e-6 cm/s
  slip, and through it the natural residual of 1e-8 to 4.8e-8.

**2. Aligning each mirror pair along `x` removes almost all of the stall (variant X1).**
- 35 of 37 fall to a natural residual of 1e-16 at the median, 1.4e-8 at worst. The two left are the C2 states
  where all six wheels stick and all motors hold.
- **It breaks 33 of 1,583 converged states (2.1%),** all in step-edge windows (`c7_edge2` 23, `c7_edge1` 9,
  `c7_sample` 1). There, a pair's offset is real, up to 18.7 cm, and moving it is not a small change. X1 was applied
  to every pair, with no threshold. So X1 alone would fail the registered rule's limit of 1% broken.
- Its velocity change in S is 6.2e-7 cm/s at most.

**3. The contact points look rounded to single precision.**
- 24,913 of 29,091 contact point coordinates (86%) are exactly representable as 32-bit floats. Only 4 of 4,860
  center-of-mass coordinates are.
- At the middle wheels' distance from the origin, about 76 cm, the 32-bit spacing is 7.6e-6 cm. That is the size
  of the offsets above.
- **Candidate, not established:** the rig takes each contact point from `Hit.ImpactPoint` of a line trace or a
  sphere sweep (`WheelRig.cpp`, where `Contact.Point` is set). If that scene query computes in single precision,
  its rounding breaks the mirror symmetry by about one spacing. Whether it does was not checked in the engine.

## What this means for method D

- **The floor is real and harmless in motion.** It moves velocities by at most 6.2e-7 cm/s, which is far below
  anything a player or a plausibility test can see.
- **It will appear in Unreal shadow runs,** whenever two sticking wheels' rows are nearly dependent and the body
  yaws. In the steady turn at 120 Hz, that was 26 of 120 steps.
- **Gate G1 would then fail D on a harmless floor.** Its condition of "residual above 1e-8 on at most 1% of shadow
  steps" was written before this result. Changing it is the owner's decision, made before any shadow run. Two options:
  - **Keep the criterion, and fix the input.** Give the solver double-precision contact points, or snap a pair's
    offset when it is within a few single-precision spacings. Either is a model change, and needs approval.
  - **Change the target.** Accept a residual floor tied to the yaw rate and single-precision spacing. That is a
    criterion change, and needs a dated record.
- **This does not decide adoption.** It removes one unknown: the 37 stalls are not a solver defect, and not a
  sign of bad contact normals or frames.

## Next minimal verification, proposed and not run

1. **Register and run X2**, a confirmatory version of X1: align a pair only when its offset is below 1e-4 cm, a
   threshold fixed now, before running. Pass if at least 30 of 37 are resolved and at most 1% of A broken. This takes
   seconds.
2. **A causal test in the stand-in rig.** Round contact points to 32-bit floats in `traj.cpp`'s turn, at 60 and
   120 Hz, and count stalls. The symmetric rig has none today. If rounding alone makes them appear, the cause is
   shown. This is a short offline run, and needs approval.
3. **Find the rounding in the engine.** The rig's side is known: `Hit.ImpactPoint`. Whether Chaos's scene query
   returns it in single precision can be read in the engine's source or tested in the rig by logging a known
   point. Reading only, or a short diagnostic run with approval.
4. **The two C2 states** stay unexplained. All six wheels stick and hold there, with 9 dependent directions. They
   need their own look, after 1 to 3.

## Follow-up checks, registered on 2026-11-07 before running

The owner approved both checks on 2026-11-07. Their rules are fixed here and committed before either runs.

**Neither is independent.** X2 uses the same 37 states on which the hypothesis was formed, after the exploratory
result was seen. It can show that the hypothesis is consistent with these data, and not that it holds elsewhere. The
rounding check uses the stand-in rig, which is not the engine.

### X2: align only near-mirror pairs

- **Change.** As X1, but a mirror pair is aligned along `x` only when its offset is below **1e-4 cm**. Pairs with a
  real offset, as at a step edge, are left alone.
- **Solve.** Improved D alone, as above. New output in `geomprobe-20261107/`, as `states_X2.txt` and
  `solved_X2.csv`. No existing file is changed.
- **Supports the hypothesis** if at least 30 of 37 are resolved and at most 1% of A, 15 states, are broken.
- **Does not support it** if 10 or fewer are resolved, or more than 1% are broken. Otherwise, inconclusive.

### F32: single-precision contact points in the stand-in rig

- **Change.** An optional flag for `traj.cpp` rounds each contact point to the nearest 32-bit float before the solve,
  and uses the rounded point for the force's lever arm, as the engine rig uses `Contact.Point`. Without the flag,
  `traj` behaves exactly as before.
- **Runs.** All six scenarios at 60 and 120 Hz, with and without the flag, in a new batch `f32-20261107/`.
  Both conditions are run fresh on this machine.
- **Measure.** Steps where improved D alone ends with a natural residual above 1e-8, per scenario and rate; the
  worst residual; and the largest position difference between the two conditions.
- **Rounding is enough to cause the floor** if the turn has no such step without the flag, and has them on at least
  1% of its steps with the flag, at 60 or 120 Hz.
- **Not enough** if the turn has none with the flag at either rate. Otherwise, inconclusive.
- **What it does not show:** that the engine rounds. That is the question in the next section.

## Follow-up results, 2026-11-07

Same machine and build as above. Both checks took seconds. New files only: `states_X2.txt`, `solved_X2.csv`, and an
updated `explore.json` in `geomprobe-20261107/`, with the earlier file kept as `explore-before-x2.json`; and the new
batch `f32-20261107/`.

### X2: supports the hypothesis, on the same data

| Measure | Result | Rule |
| --- | --- | --- |
| S resolved | 35 of 37, natural residual 3.5e-16 at the median | At least 30 |
| A broken | 0 of 1,583 | At most 15 |
| Largest velocity change in S | 6.1e-7 cm/s | Reported |
| Left unresolved | `c2_120` steps 78 and 79, where all six wheels stick and hold | — |

X1's numbers in `explore.json` are unchanged by the rerun. **As registered, X2 is not independent:** it confirms that
the hypothesis fits these 37 states, after it was formed on them.

### F32: rounding is enough to cause the floor, in the stand-in rig

**The flag changes nothing when off.** All 60 runs without it match the M4 Mac's runs of 2026-11-04 in every
column but solve time.

| Scenario, improved D alone | Steps | Stalled without rounding | Stalled with rounding | Worst residual with rounding | Largest position change |
| --- | --- | --- | --- | --- | --- |
| Turn, 60 Hz | 240 | 0 | **14 (5.8%)** | 1.8e-8 | 8.2e-12 cm |
| Turn, 120 Hz | 480 | 0 | **112 (23.3%)** | 3.7e-8 | 2.3e-13 cm |
| Straight, climb, hold, stop, drop, both rates | 180–360 each | 0 | 0 | at most 5.5e-16 | at most 1.1e-7 cm |

**By the registered rule, rounding is enough.** The rate and size match the engine's: 26 of 120 steps, or 22%, in
the steady turn at 120 Hz, with a worst residual of 4.8e-8.

**What the floor costs is time, not accuracy.** In the rounded turn, against improved D alone without rounding:

| Method | Velocity error, worst | Angular velocity error, worst | Steps at budget | Solve time, µs: median / p99 / worst |
| --- | --- | --- | --- | --- |
| D alone, 60 Hz | 1.5e-10 cm/s | 5.7e-7 °/s | 0 | 86 / 661 / 2,691 |
| D with unbounded fallback, 120 Hz | 8.2e-12 cm/s | 3.0e-7 °/s | 0 | 84 / 46,298 / 53,451 |
| D with a 1 ms budget, 120 Hz | 8.2e-12 cm/s | 3.0e-7 °/s | **112, every stalled step** | 83 / 995 / 1,001 |
| A, gated PGS, 120 Hz | 4.7e-7 cm/s | 8.2e-7 °/s | 347 passes at their cap | 1,777 / 1,928 / 1,963 |

- Each stalled step spends D's whole budget looking for a residual it cannot reach.
- In each D run, one step's stick or slide pattern differs from the reference. A's do not. Its cause was not examined.
- Times are from the MacBook Air, and are compared only with each other.

### Where the offset comes from, from the code, read only

**What the code shows** (`unreal/Source/Roverloom/WheelSpike/`):
- `WheelSpikeGameMode.cpp` runs the six-wheel tests, `c3` included, with a sphere sweep, `bSweep = true`.
- The ground is a 200 m by 200 m box with its top at z = 0, from `SpawnBlock`.
- `WheelRig.cpp` computes each wheel's mount from the body's `FTransform` in double precision, sweeps a sphere
  from it with `SweepSingleByChannel`, and sets `Contact.Point = Hit.ImpactPoint`.
- The two middle mounts are mirror images through the body's center. In double precision their offsets along `x`
  would agree to about 1e-14 cm, not 1e-5.
- The normal, forward, and lateral directions are computed in the rig, in double precision, which fits M1 to M3
  being exact.

**What the data show:** 86% of contact point coordinates are exactly 32-bit floats, against 4 of 4,860 for the
center of mass, whose value comes from the body in double precision.

**Not checked, because the engine is not installed on this machine:**
- `FHitResult::ImpactPoint`'s type in UE 5.8. From prior knowledge, not checked here: it is an `FVector_NetQuantize`,
  which stores doubles and quantizes only when sent over a network. If so, the rounding happens before the result is
  stored.
- Whether Chaos's sphere-against-box sweep computes its contact point in single precision. **This is the likely
  path, and it is a guess.**
- Why 14% of point coordinates are not 32-bit values.

**How to settle it, with approval:** read `HitResult.h` and Chaos's sweep code on the M4 Mac where UE 5.8.4 is
installed, read only; or log, in the rig, the sweep's point beside the one computed from the mount, `Up`, distance,
and radius in double precision, for one short run.

## A proposal for gate G1, not adopted

**G1's residual threshold is unchanged.** This section only proposes; the owner decides.

What the data now say: the floor is single-precision geometry, its effect on motion is at most 6.2e-7 cm/s in the
engine's states and 1.5e-10 cm/s in the stand-in, and its real cost is the time spent at the budget.

| Option | What changes | Velocity error | Time | Safety | Change needed |
| --- | --- | --- | --- | --- | --- |
| **1. Condition the input** (recommended) | Before the solve, align a mirror pair's offset when below 1e-4 cm, as X2 does | At most 6.1e-7 cm/s, in S | Stalls removed in 35 of 37 states, so no budget spent there | Unchanged; `MakeSafe` still checks | A model change, so a new `model_version` for the rig, and owner approval |
| 2. Judge D by outcomes | Replace "residual above 1e-8 on at most 1% of steps" with: velocity difference against a reference below 1e-5 cm/s, contact pattern equal, no `MakeSafe` rejection, and the time conditions | Measured directly | Budget hits allowed if time holds | Unchanged | A criterion change, recorded and dated before any shadow run |
| 3. Double-precision contact points | Compute the point from the mount and the sweep distance in double | Expected as option 1 | Expected as option 1 | Unchanged | A model change; the engine's own rounding must first be confirmed |
| 4. Keep everything | Nothing | — | D would fail G1 on about 22% of steps in a steady turn | — | None |

**Recommendation:** option 1, with option 2's outcome measures recorded beside the residual in shadow mode, so that
both are visible when the owner decides. Keep D's 1 ms budget in every case: the unbounded fallback took 46 ms at
the 99th percentile in the rounded turn.

## Unresolved

- Which engine call rounds the contact points, if any does.
- The two C2 states.
- Whether the floor appears at the same rate inside Unreal. No shadow run exists.
- Whether gate G1's residual condition should change. That is the owner's decision.
