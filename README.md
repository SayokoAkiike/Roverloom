# Roverloom

An open planetary robotics simulation and autonomy competition platform.

> **Status: pre-alpha.** A Python mission core, rover builder, agent SDK, offline leagues, and a
> lightweight 2D Mission Control work today. The high-fidelity Unreal Engine version and online
> competition **do not exist yet**.
>
> The rover, soil, power, sensor, and event models are simple approximations for games and early
> research. They have not been validated against real rovers or terramechanics.

![Replay of a science campaign in the lightweight preview](docs/images/replay-science-campaign.png)

*The lightweight preview. This is not the planned Unreal Engine renderer, and the terrain is
generated rather than real.*

## Quick start

Requires [uv](https://docs.astral.sh/uv/). A browser is needed only for viewing.

```shell
git clone https://github.com/SayokoAkiike/Roverloom.git
cd Roverloom/python
uv run roverloom demo
```

This runs sample missions with four agents, prints a score table, and writes
`runs/demo/report.html`, which you can open in a browser to replay every run.

Drive the rover yourself, or hand over to an agent with `M`:

```shell
uv run roverloom play
```

## Common commands

Run these from `python/`.

| Command | Purpose |
| --- | --- |
| `uv run roverloom demo` | Run all practice scenarios, and write a report |
| `uv run roverloom play --scenario boulder_gap` | Drive manually in a browser |
| `uv run roverloom run --agent replanner --seed 3` | Run one mission, and save its logs |
| `uv run roverloom run --agent examples/my_agent.py:CautiousAgent` | Run your own agent |
| `uv run roverloom compare --agents waypoint,replanner --seeds 1,2,3` | Compare agents |
| `uv run roverloom replay ../runs/demo/demo_traverse/replanner/seed-1 --at 200` | Check a run, and inspect its history |
| `uv run roverloom replay RUN_DIR --html view.html` | Write a replay viewer for one run |
| `uv run roverloom score RUN_DIR` | Recompute the score from logs only |
| `uv run roverloom benchmark` | Measure simulation speed on this machine |
| `uv run roverloom rover` | Compare rover designs and budgets |
| `uv run roverloom rover scout_4w --explain` | Show a design's budgets, and what each part does |
| `uv run roverloom design-study --workers 2` | Change one design choice at a time, and rerun the missions |
| `uv run roverloom study --workers 2` | Compare planners over four tracks, with intervals; about 35 minutes |
| `uv run roverloom run --scenario science_campaign --agent mission-planner --rover hauler_8w` | Run a science mission on a chosen rover |
| `uv run roverloom skills` | Print the skill contract |
| `uv run roverloom league run` | Run all offline leagues, with CSV, JSON, and leaderboards |
| `uv run roverloom competition examples/submission` | Run a local mock submission (not a sandbox) |

## What works today

| Capability | State | Details |
| --- | --- | --- |
| Mission simulation | Works | Fixed-step 2.5D model. See [models](docs/lightweight-models.md) |
| Rover Builder | Works | Classes, volume, power, part rules, and Pareto analysis. See [guide](docs/rover-builder.md) |
| Scientific study | Works | Four tracks, intervals, failure causes. See [benchmark](docs/scientific-benchmark.md) |
| Science missions | Works | Inspect, sample, send in data windows, return to base |
| Events, delay, loss, noise | Works | Eight event types, labeled as Mars-inspired or stress tests; seeded |
| Manual driving and agents | Works | The same command path for both |
| Agents and skills | Works | Reactive, classical, mission and adaptive planners, human approval, seven typed skills |
| CaP-ready interface | Mock only | Validated JSON skill calls. No real model is connected, and no code is executed |
| Offline leagues | Works | Autonomy, Rover Design, Full Mission; pinned benchmark, private seeds |
| Codabench-style evaluator | Local mock only | **Never run on Codabench**, and [not a sandbox](docs/evaluator-safety.md) |
| Logs, replay, scoring | Works | Tamper-evident JSONL; scored from files alone |
| Reproducibility | Tested | Identical logs for identical inputs on the same platform |
| Mission Control | Works locally | [Guide](docs/mission-control.md), tested in a real browser. No frontend framework |
| Agent-to-simulator bridge | Works on the lightweight backend | Loopback JSON Lines, protocol version 1 |
| Unreal contract | Specified and tested without Unreal | [Frames, units, time, safety](docs/unreal-contract.md) |
| Unreal Engine project | **Not started** | [Production plan](docs/unreal-production-plan.md) |
| Unreal MCP | **Not verified** | Engine is not installed |
| Online competition | **Not started** | [Input and output draft](docs/competition-io.md) |

## Add your own

- [Custom Rover Tutorial](docs/tutorials/custom-rover.md)
- [Custom Agent Tutorial](docs/tutorials/custom-agent.md)
- [Custom Mission Tutorial](docs/tutorials/custom-mission.md)
- [Custom Failure Model Tutorial](docs/tutorials/custom-failure-model.md)
- [Benchmark Reproduction Guide](docs/benchmark-reproduction.md)
- [Competition Rules Draft](docs/competition-rules.md)
- [API Compatibility Policy](docs/api-compatibility.md)
- [Scientific Benchmark](docs/scientific-benchmark.md)
- [Model Assumptions](docs/model-assumptions.md)
- [Handoff](docs/HANDOFF.md)
- [Project Status](docs/project-status.md)
- [Evaluator Safety](docs/evaluator-safety.md)
- [macOS Setup and Checklist](docs/macos-checklist.md)
- [Mac Unreal Plan](docs/mac-unreal-plan.md)

## Repository layout

```text
python/      Mission core, agents, preview, and tests
schemas/     Backend-neutral contracts for messages, logs, and configuration
scenarios/   Practice and benchmark missions, terrain definitions
rovers/      Rover parameters and designs
benchmarks/  Pinned benchmark definitions
competition/ Draft Codabench bundle files and public reference data
unreal/      Placeholder for the future Unreal Engine project
docs/        Design, decisions, plans, and guides
scripts/     Repository checks and preview capture
.github/     CI and templates
```

## Development

```shell
git lfs install --local
cd python
uv sync
uv run pytest
uv run ruff check . ../scripts
uv run ruff format --check . ../scripts
uv run mypy
uv run python ../scripts/check_repo.py
```

See [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), and
[security notes](docs/security.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The project is not yet open to public contributions.

## License

No license has been selected yet, so no rights are granted to use, copy, or modify this
code. An open source license is planned before any public release; see
[licensing review](docs/licensing-review.md) and [assets and sources](docs/assets-and-sources.md).

Unreal Engine is a trademark of Epic Games, Inc. Roverloom is not affiliated with or endorsed
by Epic Games, NASA, or USGS.
