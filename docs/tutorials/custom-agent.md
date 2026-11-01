# Custom Agent Tutorial

An agent is any class with two methods:

```python
from roverloom.api import Action, MissionBrief, Observation

class MyAgent:
    def reset(self, brief: MissionBrief, seed: int) -> None:
        """Called once. Use only this seed for randomness."""

    def act(self, observation: Observation) -> Action:
        """Called for each observation that arrives. Returns the next command."""
```

A commented template is [python/examples/my_agent.py](../../python/examples/my_agent.py). From `python/`:

```shell
uv run roverloom run --scenario demo_traverse --agent examples/my_agent.py:CautiousAgent
uv run roverloom league run --league autonomy --add-agent examples/my_agent.py:CautiousAgent
```

## What your agent can use

| Message | Contents |
| --- | --- |
| `MissionBrief` | Targets, science sites with prior values, base, data windows, limits, rover capabilities, map extent |
| `Observation` | Capture time, estimated pose, battery, odometry speed, range scan, generated power, science status |
| `Action` | Velocity, yaw rate, and an optional `TaskRequest` |

Rules of the world:

- Observations can be noisy, old, or lost. `time_s` is when the data was captured.
- A range of `None` means no return, including from a failed or dust-blinded sensor.
- The rover stops without a command for 2 seconds, and holds still while a task runs.
- If `act` raises or returns anything else, the mission ends as `agent_error`.
- Agents never receive rocks, soil, true science values before inspection, faults, or noise settings.

**Limit:** in the same process, this boundary prevents accidents, not cheating. Loading an agent file
runs it with your permissions. See [security notes](../security.md).

## Choose a style

| Style | How | Example |
| --- | --- | --- |
| Classical planner | Use `Navigator` | `agents/planner.py` |
| Reactive | Implement `act` | `ReactiveAgent` in `agents/basic.py` |
| Mission-level planner | `SkillPlanner` returning `SkillCall`s | `MissionPlanner` in `agents/sdk.py` |
| Code-as-policy (CaP) | `LanguageModel`, through `CapPlanner` | `MockCapAgent` |
| Human in the loop | `HumanApprovalAgent(approver)`, or the GUI | `human-approval` |

## Use skills

Print the whole contract, with inputs, outputs, preconditions, failure reasons, timeouts, and resources:

```shell
uv run roverloom skills
```

| Skill | Purpose | Typical failures |
| --- | --- | --- |
| `observe` | Hold, and report a summary | `timeout` |
| `navigate_to` | Drive, replanning around obstacles | `outside_map`, `timeout` |
| `inspect_target` | Measure a site's true value | `out_of_range`, `already_done` |
| `collect_sample` | Collect from an inspected site | `no_sample_tool`, `needs_inspection` |
| `transmit_data` | Send stored data in a window | `no_data`, `window_closed`, `link_lost` |
| `return_to_base` | Drive to base | `no_base`, `timeout` |
| `safe_stop` | Stop, and optionally end the mission | `timeout` |

```python
from roverloom.agents.sdk import SkillAgent, SkillCall, SkillStatus

class VisitFirstSite:
    def __init__(self, brief):
        site = brief.science_targets[0]
        self.calls = [
            SkillCall("navigate_to", {"x_m": site.x_m, "y_m": site.y_m, "radius_m": 2.5}),
            SkillCall("inspect_target", {"target_id": site.id}),
            SkillCall("transmit_data", {"wait": True}),
            SkillCall("safe_stop", {"end_mission": True}),
        ]

    def next_call(self, context):
        # context.history holds results, including failure reasons, to replan from.
        return self.calls.pop(0) if self.calls else None

class Agent(SkillAgent):
    def make_planner(self, brief, seed):
        return VisitFirstSite(brief)
```

## Connect a language model (optional)

No key or network is needed by default. `cap-mock` uses a deterministic rule-based stand-in, so its
scores equal `mission-planner` and **say nothing about how a real model would perform**.

To connect a real one, implement `LanguageModel.complete(prompt) -> str`, and pass it to `CapPlanner`.
No real model connection is included or tested. Keep keys in environment variables, never in Git.

`CapPlanner` accepts only one JSON object naming an allowed skill. Generated code is rejected without
being evaluated, and three invalid replies stop the rover. **Never add `eval`, `exec`, or similar.**
Running generated code would first need a real sandbox and a separate security design.

## Report your reasoning

Add `drain_decisions() -> list[str]` to appear in Mission Control and `decisions.jsonl`.
These are an agent's own claims, and scoring ignores them.
