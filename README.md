# Roverloom

An open planetary robotics simulation and autonomy competition platform.

> **Status: pre-alpha, foundation only.** This repository currently contains
> project documentation, draft data contracts, and repository tooling. There is
> no playable simulation, Unreal Engine project, rover, agent SDK, or online
> competition yet.

## Vision

Roverloom aims to bring together Mars rover design, manual driving, autonomous
AI agents, exploration missions, and fault and environment simulation, using
Unreal Engine for high-fidelity 3D and a separate Python stack for research and
evaluation.

## What exists today

| Area | State |
| --- | --- |
| `schemas/` | Draft v0 JSON Schemas for actions, observations, telemetry, missions, and scenarios |
| `scenarios/` | One example scenario used to test the schemas |
| `python/` | Contract tests only; no agent SDK, planner, or evaluator yet |
| `scripts/` | Repository hygiene check |
| `unreal/` | Placeholder; no Unreal project yet |
| `docs/` | Architecture, roadmap, decisions, environment and licensing notes |

## What is planned

See [docs/roadmap.md](docs/roadmap.md). The next milestone is a vertical slice:
high-quality Martian terrain, a six-wheeled rover, and manual driving.

## Repository layout

```text
unreal/      Unreal Engine project: terrain, physics, rendering (planned)
python/      Agent SDK, planners, evaluation (planned; contract tests today)
schemas/     Backend-neutral action, observation, mission, telemetry contracts
scenarios/   Mission and fault definitions
docs/        Design documents, decisions, development guides
scripts/     Development and verification automation
.github/     CI and issue and pull request templates
```

## Development

Requires Git, Git LFS, and [uv](https://docs.astral.sh/uv/).

```shell
git lfs install --local
cd python
uv sync
uv run pytest
uv run ruff check .
uv run python ../scripts/check_repo.py
```

Unreal Engine setup is described in
[docs/development-environment.md](docs/development-environment.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The project is not yet open to public
contributions.

## License

No license has been selected yet, so no rights are granted to use, copy, or
modify this code. An open source license is planned before any public release;
see [docs/licensing-notes.md](docs/licensing-notes.md).

Unreal Engine is a trademark of Epic Games, Inc. Roverloom is not affiliated
with or endorsed by Epic Games.
