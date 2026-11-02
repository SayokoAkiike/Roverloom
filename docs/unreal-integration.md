# Unreal integration

Design only, reviewed 2026-11-02. **Nothing here has been run in Unreal.** The tested contract is in
[unreal-contract.md](unreal-contract.md), which takes precedence over this page. Editor MCP setup and
verification are in [unreal-mcp.md](unreal-mcp.md).

## Two separate paths

| Path | Purpose | Technology | Runs in |
| --- | --- | --- | --- |
| Development | Agents inspect and edit the project | Unreal MCP, Editor Python | Editor only |
| Runtime | Python commands a rover | Roverloom TCP bridge (proposed) | Editor play and packaged builds |

Neither path depends on the other. Simulation behavior never depends on MCP.

## Runtime options

| Option | Strengths | Weaknesses |
| --- | --- | --- |
| Unreal MCP | Already planned for dev | Experimental; toolsets are editor-discovered; serial on game thread; no authentication |
| [Remote Control API](https://dev.epicgames.com/documentation/unreal-engine/remote-control-for-unreal-engine?lang=en-US) | First-party HTTP and WebSocket; no custom server | Beta; off by default in packaged builds; community reports of packaged and path issues; messages not shaped like our schemas |
| Editor Python | Good for content tools | Editor-oriented; not a runtime interface |
| Custom TCP in C++ | Same JSON messages as the lightweight backend; works in packaged builds | We own a small protocol and threading |
| gRPC or ROS 2 | Common in robotics | Extra build dependencies and license review for no current need |

**Proposal (ADR 0005):** A small C++ TCP server on loopback, carrying JSON Lines that
validate against `schemas/`. If a spike shows Remote Control is clearly simpler and
reliable in a packaged build, reconsider before writing more than the first command.

## Bridge protocol

This protocol is implemented and tested in `python/src/roverloom/bridge.py` against the lightweight
backend, where it runs in lockstep. **No Unreal side exists yet.**

- Listens on `127.0.0.1` only. No authentication, so never bind it more widely. A future
  networked competition needs a separate, sandboxed design.
- UTF-8 JSON, one document per line, 1 MiB maximum. Invalid input ends the mission as `agent_error`.
- Each line is `{"type": ..., "body": ...}`:

| Type | Direction | Body |
| --- | --- | --- |
| `start` | Simulator to agent | `{"protocol_version": 1, "seed": n, "brief": MissionBrief}` |
| `observation` | Simulator to agent | [Observation](../schemas/observation.schema.json) |
| `action` | Agent to simulator | [Action](../schemas/action.schema.json) |
| `end` | Simulator to agent | `{}` |

- Lockstep on the lightweight backend. Unreal starts in real time, in which case an action
  applies when it arrives. Deterministic stepping in Unreal is for Phase 3.
- Socket work stays off the game thread. Latest action passes through a thread-safe slot,
  and is read at the start of a physics step.

```text
Python client --TCP--> bridge thread --latest Action--> Rover control input
Keyboard ------------------------------Action---------> (one selected at a time)
                                                         |
                                                   Rover physics
                                                         |
                                 Observation <-----------+---------> Telemetry log
```

## Control rules

1. Keyboard and Python both produce the same `Action`. There is one rover input path.
2. The active source is explicit: `Manual` or `External`. A key toggles it; the HUD shows
   it. External commands in `Manual` mode are ignored and logged.
3. Watchdog: if the active source sends no Action for 2 s, the rover commands zero velocity.
4. Disconnecting never crashes the simulation, and never leaves motors running.
5. Commands are clamped to rover limits, and clamping is logged.

## Boundary conversion

Only `unreal/Source/Roverloom/Bridge/CoordinateConversion` converts between contract SI
right-handed units and Unreal centimeters and left-handed frames. Unit tests cover position,
quaternion, velocity, and yaw-rate sign. Getting yaw sign wrong would otherwise appear only
as a rover turning the wrong way.

## Project layout (planned)

```text
unreal/
  Roverloom.uproject
  Config/                  Text, in Git
  Source/Roverloom/
    Rover/                 Physics, drive, control input
    Bridge/                TCP, messages, coordinate conversion
    Telemetry/             Run manifest, logs, replay
    Cameras/
  Content/
    Maps/ Rover/ Terrain/ Materials/ Effects/ Input/  Original or confirmed assets
    Licensed/              Ignored by Git
```

A single module is enough for now. Split into plugins only when a second project needs it.

## Python side (planned)

`python/src/roverloom/` adds a small `client` (connect, send Action, receive Observation),
and `replay` tools working on log files. The same client will work with the lightweight
simulator. CI tests the client against a fake TCP server, since CI has no Unreal Engine.

## Testing without a GPU in CI

- CI: schema, Python client, log and replay parsing.
- Unreal automation tests run by hand or on a future self-hosted runner, and test results
  are recorded with engine version and machine.
- Epic's terms and storage cost should be checked before caching engine builds in CI.
