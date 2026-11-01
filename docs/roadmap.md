# Roadmap

Checked items exist and are tested on the lightweight backend. Everything else is a plan.

## Phase 0: Foundation (in progress)

- [x] Private repository, documentation, Git LFS, and CI configuration
- [x] Draft data contracts and contract tests
- [ ] Unreal Engine 5.8 and C++ toolchain installed
- [ ] Unreal MCP verified with a read-only call

## Lightweight vertical slice (done)

- [x] Mission core: fixed-step model, faults, delay, loss, noise, mission rules
- [x] Common command path for manual driving and agents
- [x] Logs, kinematic replay, file-based scoring, reproducibility tests
- [x] Sample agents, custom agent loading, skill plans as data
- [x] Lightweight browser preview, separate from the Unreal renderer
- [x] Loopback bridge protocol, on the lightweight backend

## Phase 1: Unreal vertical slice

Goal: a real Martian site you can drive a six-wheeled rover across. Details are in
[vertical-slice-plan.md](vertical-slice-plan.md) and
[unreal-production-plan.md](unreal-production-plan.md).

- [ ] Create the UE 5.8 C++ project in `unreal/`, confirm a clean clone opens
- [ ] Measure baseline frame rate on the target machines
- [ ] Rover: physics spike, six wheels, rocker-bogie, plausibility tests
- [ ] Keyboard and Python driving through one input path; camera switching
- [ ] Telemetry logs and kinematic replay
- [ ] Terrain from a public Mars elevation tile, Landscape by default
- [ ] Martian look: regolith, atmosphere, lighting, dust; graphics report

## Phase 2: Shared mission loop

- [ ] Evaluator scoring Unreal logs, proving the same code works for both backends
- [ ] Mission logic in Unreal consuming the same scenario files

## Phase 3: Autonomous agents

- [ ] Unreal agent transport, using the bridge protocol
- [ ] Deterministic stepping in Unreal, and reproducibility checks
- [ ] Sandboxed planner interface, before any code-as-policy agent

## Phase 4: Depth

- [ ] More faults: power and sensor degradation
- [ ] Environment: dust, terrain properties, day and night
- [ ] Rover design: configurable chassis and components

## Phase 5: Open release and competition

- [ ] License audit and license selection
- [ ] Public release decision, contribution process
- [ ] Competition design, submission sandboxing, and leaderboard
