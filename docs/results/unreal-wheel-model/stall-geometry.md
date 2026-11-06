# Wheel model: where method D's 37 stalls come from

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

Not yet run.
