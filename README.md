# Roverloom

Developed and maintained by [QUODVIS Inc.](https://quodvis.co).

A simulation and benchmarking platform for autonomous rover agents. Compare agents on the same missions, terrain, communication delays, and faults, with scoring and replay from run logs.

![Six-wheeled Roverloom rover on Gale crater terrain in Unreal Engine](docs/images/game/hero.jpg)

*Unreal Engine 5.8.4 screenshot. Terrain: NASA/JPL/University of Arizona; materials: Poly Haven (CC0). The level and textures are outside Git. [Capture details](docs/results/gale-effects/README.md).*

**Pre-alpha.** The Python simulator supports custom agents and rovers, manual driving, offline leagues, scoring, and replay. The Unreal client is experimental; the quick start below runs the Python simulator. LLM integration and online competitions: **Not started**. Physics models are simplified and have not been validated.

## Quick start

Requires [uv](https://docs.astral.sh/uv/); Python 3.12 or later is managed by uv. Unreal Engine is not required.

```shell
git clone https://github.com/SayokoAkiike/Roverloom.git
cd Roverloom/python
uv run roverloom demo
```

Open `runs/demo/report.html` in the repository root to view results and replay runs.

To drive in a browser, run:

```shell
uv run roverloom play
```

For the experimental source-build 3D tutorial, see [First 3D mission](docs/first-3d-mission.md) (macOS; fresh-machine playtest pending).

## Experimental rally and garage

The [rally guide](docs/rally.md) covers route choices, supply and sampling stops, limited boosts, seeded dust events, local ghosts, and a saved four-slot garage. Source implementation only: Unreal build and playtest are pending.

## Development priorities

Planned work, beyond the current pre-alpha:

- **Visuals:** improve the rover and Martian environment with vork and other 3D tools, bringing suitable assets and lighting into the playable Unreal client.
- **Agent competition:** build a game mode for custom autonomous agents, including code-as-policy (CaP) through the typed skill interface.
- **Gameplay:** add difficulty presets with configurable random faults and environmental events, using shared seeds for fair agent comparisons.

## Build your own

- [Agent](docs/tutorials/custom-agent.md)
- [Rover](docs/tutorials/custom-rover.md)
- [Mission](docs/tutorials/custom-mission.md)
- [Failure model](docs/tutorials/custom-failure-model.md)

See the [Mission Control guide](docs/mission-control.md), [benchmark guide](docs/benchmark-reproduction.md), and [project status](docs/project-status.md) for more.

## Concept renders

Rendered offline with [vork](https://github.com/voyager-so/vork); these are concept images, not gameplay screenshots. [Render details and credits](docs/results/concept-renders/README.md).

![Vork concept render: Roverloom rover in a Mars-inspired landscape](docs/images/concept/hero.jpg)

| | |
| --- | --- |
| ![Vork concept render: side view](docs/images/concept/side.jpg) | ![Vork concept render: rover at sunset](docs/images/concept/sunset.jpg) |

![Vork concept render: rover on HiRISE-derived Gale crater terrain](docs/images/concept/gale.jpg)

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

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [architecture](docs/architecture.md). External contributions are not yet accepted while licensing is being finalized.

## Governance and license

QUODVIS leads the roadmap, reviews proposed changes, and maintains official releases. We are preparing Roverloom for a company-led open-source release; external contributions will open after the project license and contribution terms are published. Third-party software and assets remain subject to their respective licenses.

A project license has not been selected; this repository is not yet an open-source release. See the [licensing review](docs/licensing-review.md) and [asset credits](docs/assets-and-sources.md).

Roverloom is not affiliated with or endorsed by Epic Games, NASA, or USGS.
