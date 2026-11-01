# Adding an agent

An agent is any class with two methods:

```python
from roverloom.api import Action, MissionBrief, Observation

class MyAgent:
    def reset(self, brief: MissionBrief, seed: int) -> None:
        """Called once. Use only this seed for randomness."""

    def act(self, observation: Observation) -> Action:
        """Called for each observation that arrives. Returns the next command."""
```

A commented template is at [python/examples/my_agent.py](../python/examples/my_agent.py). Run it
from `python/`:

```shell
uv run roverloom run --scenario demo_traverse --agent examples/my_agent.py:CautiousAgent
uv run roverloom compare --agents reactive,examples/my_agent.py:CautiousAgent --seeds 1,2,3
```

To add one to the built-in list, register it in `BUILTIN_AGENTS` in
`python/src/roverloom/agents/__init__.py`, and add a test.

## What your agent can use

| Message | Contents |
| --- | --- |
| `MissionBrief` | Mission ID, start pose, targets, limits, control period, rover size and speed limits, sensor range, map extent |
| `Observation` | Capture time, estimated pose, battery fraction, wheel-odometry speed, targets reached, range scan |

## Rules of the world

- Observations can be noisy and old. `time_s` is when the data was captured.
- Observations can be lost. Your agent is called only when one arrives.
- A range of `None` means no return, which is also what a failed sensor produces.
- The rover stops if it gets no command for 2 seconds.
- If `act` raises or returns anything but an `Action`, the mission ends as `agent_error`.
- Agents are never told about rocks, soil, faults, or noise settings. They must infer them.

## Information boundaries, and their limit

The simulator gives agents only frozen copies of these messages, and tests check that future
faults do not affect observations before they begin. However, an agent in the same Python process
could still inspect the interpreter, or read scenario files. **This boundary prevents accidents,
not cheating.** A fair competition needs agents isolated in a sandbox, as described in
[competition-io.md](competition-io.md). Treat agent files as untrusted code: loading one runs it
with your permissions.

## Skills and code-as-policy agents

`roverloom.agents.skills` defines how a future high-level planner can drive the rover:

- A **skill** has `step(observation)`, returning an `Action` and a status.
- A **plan** is JSON validated by [skill_plan.schema.json](../schemas/skill_plan.schema.json), which
  names skills from a fixed list with typed parameters.

```shell
uv run roverloom run --agent skill-plan --plan my_plan.json
```

```json
{
  "schema_version": 0,
  "steps": [
    { "skill": "wait", "duration_s": 5 },
    { "skill": "go_to", "x_m": 40, "y_m": 10 },
    { "skill": "go_to_next_target" }
  ]
}
```

**No LLM is connected, and plans are never executed as code.** Adding a skill is a reviewed
code change. Running generated Python, as true code-as-policy systems do, requires a real sandbox
and a separate security design first. Do not add `eval`, `exec`, or similar to the agent path.

Plans are open-loop today: they have no branches or error handling, and a future planner would
need to replan between them.
