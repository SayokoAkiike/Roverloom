# 0014: Chaos rigid bodies and joints for the rover physics spike

Status: Proposed (2026-11-03). R0 failed twice. Not accepted until R0 and R1 pass.

## Context

[`vertical-slice-plan.md`](../vertical-slice-plan.md) lists three candidates for rover physics, and asks for a timeboxed
spike recorded in an ADR. UE 5.8.4 ships Chaos Vehicles and Chaos Modular Vehicle as Experimental plugins, disabled by
default. Rocker-bogie articulation and per-wheel faults are central to Roverloom.

## Decision, proposed

- Build the rover from Chaos rigid bodies and joints, with drive in C++. No vehicle plugin.
- Spawn the test scenes from C++ on the engine's Entry map, so that the spike needs no project assets.
- Treat the spike as an independent experiment. It never feeds the Python Mission Core, which stays the reference for
  science evaluation and competitions. Whether Unreal becomes a backend with its own authority is not decided here.
- Chaos Wheeled Vehicle and Chaos Modular Vehicle were judged on paper and not measured. Measure Modular Vehicle if
  this approach fails within the timebox.

## Evidence

[Results](../results/unreal-physics-spike/README.md). R0 attempt 1 stalled on the ground with a 100 N m limit. A
torque calibration showed the limit is correct on a free wheel, and that most drive torque is lost through sphere contact,
more so at finer steps. Attempt 2, with no effective limit, passed straight driving and failed turning and the time step
test. Slope holding slides for an unidentified reason. The results recommend replacing sphere contact with a C++ wheel
model, or measuring Chaos Modular Vehicle, before R1.

## Consequences

- We own joint setup, drive, and their tuning. Chaos needs bodies to exist before joints, and does not wake sleeping
  bodies for a new drive target. Both cost a failed run each.
- Joint force output was not usable as a load measurement here.
- Results are plausible for game use at best, and never validated.
