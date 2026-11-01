# Roverloom

An open planetary robotics simulation and autonomy competition platform.

> **Status: pre-alpha.** The Python mission core, sample agents, and a lightweight 2D
> browser preview work today. The high-fidelity Unreal Engine version and online
> competition **do not exist yet**.
>
> The rover, soil, power, and sensor models are simple approximations for games and early
> research. They have not been validated against real rovers or terramechanics.

![Replay of an autonomous mission in the lightweight preview](docs/images/replay-demo-traverse.png)

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

## What works today

| Capability | State | Details |
| --- | --- | --- |
| Mission simulation | Works | Fixed-step 2.5D model. See [models](docs/lightweight-models.md) |
| Faults, delay, loss, noise | Works | Wheel failure, comm blackout, sensor dropout; seeded |
| Manual driving and agents | Works | The same command path for both |
| Sample agents | Works | Stop, waypoint, reactive, grid replanner, skill plan |
| Logs, replay, scoring | Works | Tamper-evident JSONL; scored from files alone |
| Reproducibility | Tested | Identical logs for identical inputs on the same platform |
| Lightweight browser preview | Works | Local only, no frontend framework |
| Agent-to-simulator bridge | Works on the lightweight backend | Loopback JSON Lines |
| Skill plans for future code-as-policy agents | Interface only | Plans are data; no LLM is connected |
| Unreal Engine project | **Not started** | [Production plan](docs/unreal-production-plan.md) |
| Unreal MCP | **Not verified** | Engine is not installed |
| Online competition | **Not started** | [Input and output draft](docs/competition-io.md) |

## Add your own

- [Agents](docs/adding-agents.md)
- [Scenarios and fault models](docs/adding-scenarios.md)
- [Rover specifications](docs/adding-rovers.md)

## Repository layout

```text
python/      Mission core, agents, preview, and tests
schemas/     Backend-neutral contracts for messages, logs, and configuration
scenarios/   Practice missions, terrain definitions
rovers/      Rover specifications
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
