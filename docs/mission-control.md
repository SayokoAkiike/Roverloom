# Mission Control

`uv run roverloom play` opens a local 2D display. It is a development tool, not the planned Unreal
renderer. What carries over to Unreal is its information design and contracts:

| Contract | Purpose |
| --- | --- |
| [mission_control_state](../schemas/mission_control_state.schema.json) | What a live display needs |
| [telemetry](../schemas/telemetry.schema.json), [event](../schemas/event.schema.json), [decision](../schemas/decision.schema.json) | What a replay needs |
| [world payload](../python/src/roverloom/preview/report.py) | Sites for display, without hidden values |

## Display

A status bar shows what matters at a glance: mission state, time, battery, command link, data window,
driver, and science sent. Active faults get a banner, and failures of the page or simulation get
another. Panels hold objectives, rover state, events, agent decisions, and the score.

The event and decision lists keep the reader's scroll position, and follow new rows only when already
at the end. Controls that cannot work are disabled, such as Stop after a mission has ended.

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

## Input rules

- Keys are ignored while a list has focus, and choosing an option gives the keyboard back.
- `Ctrl`, `Alt`, and `Cmd` combinations stay with the browser, so `Ctrl+R` does not restart the mission.
- Losing window focus releases all keys. A closed tab stops the rover within 0.6 s.
- Nothing can follow the end of a mission. Switching driver afterward does nothing, and the log stays valid.

## Verified, and not

[test_mission_control_e2e.py](../python/tests/e2e/test_mission_control_e2e.py) drives Edge or Chrome through
Playwright, whose keyboard and mouse events reach the page as trusted input. Evidence from the latest
saved run is in [`docs/e2e/`](e2e/e2e-log.jsonl), including screenshots.

| Tested in a real browser | |
| --- | --- |
| Keyboard | Forward, left turn, arrows, Space, release, and focus rules |
| Handover | By key and by button, with the rover at rest afterward |
| Buttons | Start with a chosen setup, Restart, Stop, double click, 50 repeated presses |
| Faults | Banner, link status, wheel, recovery, and event log |
| Replay | Play, speed, scrubbing both ways |
| Errors | Server lost and regained, a refused request, a failed simulation |
| Window sizes | 320 to 1920 wide, resizing while running, and no sideways scrolling |

Not tested: a person at a real keyboard, Safari, real phones, touch input, and accessibility tools. Touch
input has no driving controls.
