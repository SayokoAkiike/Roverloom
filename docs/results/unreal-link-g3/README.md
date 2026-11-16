# G3 mission link with the `reactive` agent, one run

**One run, one machine, real time.** Measured 2026-11-16 on the Mac mini (Apple M4, 16 GB, macOS 27.0.1), UE 5.8.4
(CL 58902052), at `e291392` (the C++ was compiled on the same day, see below). This is not a benchmark and not a
reproducible result. Unreal's physics are its own and the run is not scored. See [`unreal_link.py`](../../../python/src/roverloom/unreal_link.py).

## What was run

| Step | Exact call |
| --- | --- |
| Build | `Build.sh RoverloomEditor Mac Development -project=unreal/Roverloom.uproject`: `Result: Succeeded`, 34.2 s, 20 actions, no warnings or errors. `RoverPawn.cpp` (PR #16's `action` input, and PR #9's V2 pawn) compiled for the first time |
| Rover | `UnrealEditor unreal/Roverloom.uproject "/Engine/Maps/Entry?game=/Script/Roverloom.RoverPlaygroundGameMode" -game -windowed -ResX=1280 -ResY=720 -RoverDrive=play-g3 -log`. The editor with the MCP server was also open |
| Agent | `uv run python -m roverloom.unreal_link --scenario g3_reach_target --agent reactive --port 8100 --out <dir> --wait 30` |

`--out` is required by the client, and the port is fixed at 8100 in `RoverPawn.cpp`. With `play-g3` the rover has no drive
script ("0 phases"), so it moves only on `action` lines from Python.

## Measured

| Quantity | Value | Source |
| --- | --- | --- |
| Client exit code | 0 | shell |
| Outcome | `success`, 1 of 1 targets | `final_state.json` |
| Mission time at success | 34.4 s (first state line at 13.4 s, so 21.0 s after the link's first state) | `states.jsonl`, 244 lines |
| Wall time, link connected to success shown on Unreal's HUD text | 21.05 s (07:19:13.810 to 07:19:34.861 UTC) | Unreal log |
| Unreal's own record of the verdict | `targets 1/1   SUCCESS   t 34.4 s` | Unreal log |
| Rover at rest before the link | site (0.000, -0.000, 0.700) m, tilt 0.00 deg, wheels on ground 6/6 | Unreal log |
| Target | (8, 0, 0) m, radius 2 m, from [`g3_reach_target.json`](../../../scenarios/practice/g3_reach_target.json) | scenario |
| Frame rate while linked, window not in focus | 95.2, 92.8, 91.2 fps (10 s windows; p95 11.5 to 11.6 ms) | Unreal log |

The Python session replaces only the rover's position with Unreal's. Success therefore means that Unreal reported a position
within 2 m of (8, 0), starting from (0, 0), with no motion from any drive script. That is the basis for saying the agent moved the rover.

## Not measured, and open

- **No Unreal-side position or speed log** between "settled" and the end. Distance and speed are not reported. The only
  evidence of motion is the mission verdict, which depends on Unreal's telemetry.
- **No screenshot or video** of the run. Nobody watched the window.
- **No count of `action` lines** sent or received, and no comparison of commanded and achieved velocity.
- **One run.** No repeat, no spread. Real-time runs do not reproduce.
- The mission clock was already at 13.4 s on the first state line. The reason was not investigated.
- Unreal logged `client dropped (connection error)` 5 s after the success, when the client exited after its linger. It is the
  message for any end of connection and was not examined further.
- The editor logs 15 Python errors from the experimental EditorToolset start-up script (`unreal.AgentSkill`, `unreal.PythonTestRunner`
  missing), as already noted in the [G2 results](../g2-greybox/README.md). They did not stop the link.
- The run used the C++ test ground from the greybox mode, not a Mars terrain.

## What this shows

On this one run, a Python agent drove the Unreal rover over the bridge `action` path, and the Mission Core judged the target reached.
It does not show that the path is reliable, that control is accurate, or that the agent suits Unreal's physics.
