# Roadmap

Checked items exist and are tested on the lightweight backend, or, where marked, recorded by hand on the Mac. Everything else is a plan.

## Phase 0: Foundation (in progress)

- [x] Private repository, documentation, Git LFS, and CI configuration
- [x] Draft data contracts and contract tests
- [x] Unreal Engine 5.8 and C++ toolchain installed, on the M4 Mac (recorded by hand)
- [x] Unreal MCP verified with a read-only call, on the M4 Mac (recorded by hand)

## Lightweight vertical slice (done)

- [x] Mission core: fixed-step model, faults, delay, loss, noise, mission rules
- [x] Common command path for manual driving and agents
- [x] Logs, kinematic replay, file-based scoring, reproducibility tests
- [x] Sample agents, custom agent loading, skill plans as data
- [x] Lightweight browser preview, separate from the Unreal renderer
- [x] Loopback bridge protocol, on the lightweight backend

## Game systems and competition (done on the lightweight backend)

- [x] Rover Builder with budgets, and three standard rovers
- [x] Science missions, data windows, events labeled by origin
- [x] Agent SDK, seven typed skills, mock CaP agent, human approval
- [x] Pinned benchmark, three leagues, private seeds, local leaderboards
- [x] Local mock of Codabench-style ingestion and scoring
- [x] Mission Control with setup, tasks, approvals, and replay
- [ ] Connect and evaluate a real language model (optional)
- [ ] Real sandbox and an actual Codabench run

## Competition quality and evaluation (done on the lightweight backend)

- [x] Design classes, volume, power, and compatibility rules; Pareto analysis; intervention studies
- [x] Study tracks: standard, stress, out of distribution, misestimated uncertainty
- [x] Confidence intervals, paired comparison, failure causes, recorded decisions
- [x] Adaptive planner with ablations, and hidden-truth separation tests
- [x] Mission Control E2E tests in a real browser
- [x] Local evaluator limits and hostile submission tests, with its bypass documented
- [x] Frames, units, protocol v1, conformance checks, and a stand-in backend for Unreal
- [x] Final measurements recorded in [results/phase3](results/phase3/README.md)
- [ ] Scenarios and seeds held out from planner development
- [ ] Review of related work before any research claim

## Phase 1: Unreal vertical slice

The current order of work on the Mac is in [mac-unreal-plan.md](mac-unreal-plan.md).

Goal: a real Martian site you can drive a six-wheeled rover across. Details are in
[vertical-slice-plan.md](vertical-slice-plan.md) and
[unreal-production-plan.md](unreal-production-plan.md).

- [x] Create the UE 5.8 C++ project in `unreal/`, confirm a clean clone opens (recorded by hand)
- [ ] Measure baseline frame rate on the target machines
- [ ] Rover: physics spike, six wheels, rocker-bogie, plausibility tests. R0 [failed twice](results/unreal-physics-spike/README.md)
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

- [ ] Environment: terrain properties, day and night
- [ ] Rover design in Unreal: configurable chassis and components

## Phase 5: Open release and competition

- [ ] License audit and license selection
- [ ] Public release decision, contribution process
- [ ] Competition design, submission sandboxing, and leaderboard
