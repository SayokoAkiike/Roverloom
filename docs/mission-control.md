# Mission Control

`uv run roverloom play` opens a local 2D display. It is a development tool, not the planned Unreal
renderer. What carries over to Unreal is its information design and contracts:

| Contract | Purpose |
| --- | --- |
| [mission_control_state](../schemas/mission_control_state.schema.json) | What a live display needs |
| [telemetry](../schemas/telemetry.schema.json), [event](../schemas/event.schema.json), [decision](../schemas/decision.schema.json) | What a replay needs |
| [world payload](../python/src/roverloom/preview/report.py) | Sites for display, without hidden values |

## Display

Objectives, rover state, command link, data windows, latency, battery, terrain, position, path, faults,
events, agent decisions, score, and replay.

## Controls

| Control | Endpoint |
| --- | --- |
| Drive with `WASD` or arrows | `POST /api/command` |
| Switch driver | `POST /api/mode` |
| Start with a scenario, rover, agent, speed | `POST /api/configure` |
| Stop, restart | `POST /api/stop`, `POST /api/reset` |
| Inspect, collect, transmit, end | `POST /api/task` |
| Approve or decline (`human-approval`) | `POST /api/approve` |
| Open replay of the finished run | `GET /replay` |
| Replay speed | Local to the page |

State: `GET /api/state` (its `control` key), `GET /api/world`, `GET /api/options`.

The server is loopback-only, checks Host and Origin, and accepts only choices it published. Another
program on the same machine can still control it, as there is no authentication.

## Verified, and not

`scripts/capture_preview.py` runs real key events and clicks in a headless browser, and the API has
integration tests. Testing by a person at a real keyboard, phones, and accessibility are not checked.
