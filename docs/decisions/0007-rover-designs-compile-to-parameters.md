# 0007: Rover designs compile to parameters

Status: Accepted (2026-11-02)

## Context

Participants need to design rovers with real trade-offs, while the simulator already consumes flat
parameters, and legacy files must keep working.

## Decision

Designs (`rover_design`) describe parts, and a builder compiles them to the existing `rover` parameters
plus optional fields. Budgets and plausibility checks live in the builder. Designs carry provenance.
Wheel faults map onto existing wheels, and random faults draw from a fixed wheel list.

## Alternatives

Simulating each part directly would add fidelity that the lightweight model cannot justify, and
hand-tuning parameters would allow free performance without cost.

## Consequences

The rules are game rules, and are versioned. Unreal can compile the same design differently, under
its own model version. Rule changes invalidate benchmarks.
