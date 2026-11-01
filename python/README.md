# Python mission core

| Module | Purpose |
| --- | --- |
| `roverloom.api` | Typed messages. Agents see only `Action`, `Observation`, `MissionBrief` |
| `roverloom.contract` | Strict JSON loading and schema validation |
| `roverloom.world` | Scenario, terrain, and rover loading and checks |
| `roverloom.sim` | Rover, sensor, fault, and communications models |
| `roverloom.command` | `CommandRouter`: one path for all drivers |
| `roverloom.session` | Advances a mission one step |
| `roverloom.runner` | Complete runs and comparisons |
| `roverloom.runlog` | Writes and strictly reads run directories |
| `roverloom.evaluate` | Scores from log files alone |
| `roverloom.replay` | Kinematic playback |
| `roverloom.agents` | Sample agents, skills, and agent loading |
| `roverloom.bridge` | Loopback protocol for agents in another process |
| `roverloom.preview` | Lightweight browser preview and reports |
| `roverloom.cli` | The `roverloom` command |

The package must run from a checkout, because it reads `schemas/`, `scenarios/`, and `rovers/`
from the repository. Set `ROVERLOOM_HOME` to point elsewhere. It is not yet published as a
standalone package.

See the [repository README](../README.md) to get started.
