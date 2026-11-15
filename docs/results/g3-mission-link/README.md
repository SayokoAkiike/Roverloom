# G3: mission link between Unreal and the Mission Core, 2026-11-07

**Status: passed and merged. Completion criteria: (1) Unreal raises the arrival and the Mission Core receives it;
(2) the Mission Core's state reaches Unreal's HUD; (3) build, related tests, and an end-to-end run pass. All met.**

## What runs

- Unreal, preset `-RoverDrive=g3-reach`: listens on `127.0.0.1:8100` only, sends `telemetry` (site-frame position in
  metres, forward speed, resets) at 10 Hz, and shows each `mission_state` it receives on the HUD. It does not judge the
  mission.
- Python, `python -m roverloom.unreal_link --scenario g3_reach_target`: an ordinary `MissionSession` whose rover
  position comes from Unreal; the session's own `_update_mission` decides `target_reached`, success, and limits, and the
  link sends `mission_state` back. The session's battery and energy remain the Mission Core's model.
- Framing: the bridge protocol's JSON Lines (`{"type", "body"}`, 1 MiB per line). `telemetry` and `mission_state` are
  new message types for this link, outside bridge protocol version 1.
- Route: the Air's link connects through the night key's tunnel (`-L 18100:127.0.0.1:8100`), the one port that key may
  forward; no new permission, port, or outbound rule.
- Scenario `scenarios/practice/g3_reach_target.json`: one target 8 m ahead, radius 2 m, 120 s, no faults.

## End-to-end run (`g3-1`, Mac mini, `rdnight`, `-RenderOffscreen`)

| Check | Result |
| --- | --- |
| Link | Unreal listened at 12:41:29, the Mission Core connected at 12:41:30 |
| Arrival | Mission Core events: `mission_started` 0.0 s, `target_reached` 18.1 s, `mission_ended` `success` 18.1 s. Expected: 6 s settle, then 0.5 m/s reaches the 2 m radius (x 6 m) at about 18 s |
| HUD | `Mission (Python): g3_reach_target targets 1/1 SUCCESS t 18.1 s`, green (`hud-success.png`); Unreal logged RUNNING then SUCCESS from the Mission Core |
| States | 219 `mission_state` lines; RUNNING until 18.1 s, then SUCCESS |
| Closing | the client's disconnect was dropped cleanly; port 8100 closed after the game |
| Build, tests | build ok; automation 5 of 5; Python: `test_unreal_link.py` 3 tests (success, short of target, loopback only), full pytest 828 passed, 1 skipped |
| GPU | 11.3–11.8 ms, as other drive runs |

## Limits and backlog

- Sockets use non-blocking calls on the game thread; the contract asks for a socket thread (`RealtimeCommandLink`).
- One target, flat ground, scripted driving; a person driving with the keyboard was not part of this run.
- `telemetry` and `mission_state` are not yet in `docs/unreal-contract.md` or the schemas.
- No run log or score for Unreal runs yet (backlog item 1).
