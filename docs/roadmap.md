# Roadmap

All items below are plans. Only Phase 0 has work in the repository.

## Phase 0: Foundation (in progress)

- [x] Private repository, documentation, Git LFS, and CI configuration
- [x] Draft data contracts and contract tests
- [ ] Unreal Engine 5.8 and C++ toolchain installed
- [ ] Unreal MCP verified with a read-only call

## Phase 1: Vertical slice

Goal: a real Martian site you can drive a six-wheeled rover across. Details and
completion criteria are in [vertical-slice-plan.md](vertical-slice-plan.md).

- [ ] Python client, log, and replay tools, tested without Unreal
- [ ] Create the UE 5.8 C++ project in `unreal/`, confirm a clean clone opens
- [ ] Measure baseline frame rate on the target machines
- [ ] Rover: physics spike, six wheels, rocker-bogie, plausibility tests
- [ ] Keyboard and Python driving through one input path; camera switching
- [ ] Telemetry logs and kinematic replay
- [ ] Terrain from a public Mars elevation tile, Landscape by default
- [ ] Martian look: regolith, atmosphere, lighting, dust; graphics report

## Phase 2: Shared mission loop

- [ ] Lightweight Python simulator running scenarios
- [ ] Evaluator scoring telemetry logs, same code for both backends
- [ ] Mission logic in Unreal consuming the same scenario files

## Phase 3: Autonomous agents

- [ ] Python agent SDK and a baseline planner
- [ ] Decide and implement the Unreal agent transport
- [ ] Deterministic stepping and reproducibility checks

## Phase 4: Depth

- [ ] Fault injection: wheel failures, power, sensor degradation
- [ ] Environment: dust, terrain properties, day and night
- [ ] Rover design: configurable chassis and components

## Phase 5: Open release and competition

- [ ] License audit and license selection
- [ ] Public release decision, contribution process
- [ ] Competition design, submission sandboxing, and leaderboard
