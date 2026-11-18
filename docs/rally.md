# Experimental rover rally and garage

This source prototype adds game rules alongside the scientific simulator. It is not a ranked physics benchmark. Python rules and the local TCP link have automated tests; the changed Unreal C++ still needs a UE 5.8.4 build and a Mac playtest. No packaged game is supplied.

## Prepare a rover

From the repository root, write an offline garage page:

```shell
uv run --project python python -m roverloom.rally --ui
```

Open `runs/garage.html`, choose tires, battery, sensor and paint, then download `garage.json`. The page shows a schematic, not an Unreal render. Alternatively:

```shell
uv run --project python python -m roverloom.rally --tires sand --battery endurance --sensor scout --paint cyan --out runs/garage.json
```

Six wheels and the chassis geometry remain fixed. Sand tires improve sandy-zone speed at the cost of cruise speed. An endurance battery increases capacity but reduces cruise speed. The scout sensor gives an earlier dust warning but consumes more idle charge. These are invented game modifiers, not measured hardware properties. Only paint changes the Unreal assembly's appearance; component selection does not yet replace its meshes.

## Launch on macOS

Install the existing project's [Unreal prerequisites](first-3d-mission.md), then run from the repository root (adjust the engine path):

```shell
uv run --project python python scripts/play_3d.py --rally --garage runs/garage.json --difficulty standard --seed 1 --ue-root "/Users/Shared/Epic Games/UE_5.8" --build
```

Add `--check` to check tools and the loopback port without launching or building. Close other rover sessions before launching. Click the game window; W/S drives, A/D turns, C changes camera, SPACE requests a boost, R rescues the rover to its starting pose. Rescue adds 60 seconds to the result; it is not a route shortcut without a cost.

## One course, four ordered stages

1. Pass either the sandy shortcut at site `(5, -3)` or the longer firm route at `(5, 7)`.
2. Stop near the supply gate `(14, 0)` for two seconds to replenish charge and one boost.
3. Stop at the sample gate `(22, 0)` for one second.
4. Return to the start `(0, 0)`.

Active targets have green wire outlines. Gates have a two-metre arrival radius. There is a 240-second limit. Boost lasts three seconds, costs eight charge units, and has two initial uses. Dust reduces speed for the final four seconds of selected 20-second intervals: easy disables it, standard uses probability 0.2, hard 0.4. The seed and interval determine events independently of player actions. These probabilities are game settings, not Martian statistics.

The generated level uses engine primitives, a sandy patch, supply structures, gate pillars and distant rocks. It does not require the untracked Gale map or third-party asset downloads. The rover adds panel and hub details. This is a visual starting point, not the photorealistic target in the concept renders.

## Replay a ghost

The launcher prints a new run directory under `runs/first-3d/`. It contains `unreal.log`, `link.log`, `states.jsonl`, `final_state.json`, and `ghost.json`. Use its actual path:

```shell
uv run --project python python scripts/play_3d.py --rally --garage runs/garage.json --difficulty standard --seed 1 --ghost runs/first-3d/run-REPLACE/ghost.json --ue-root "/Users/Shared/Epic Games/UE_5.8"
```

A cyan wire box replays the previous position without collisions. Difficulty, seed and ruleset must match; a different garage is allowed for comparison. The trajectory ends when its recording ends. This is a local time-trial ghost, not a live opponent or anti-cheat system. Success requires all four stages and an explicit Python verdict; a lost connection cannot count as a finish. Commands stop after two seconds without a rally response.

Custom autonomous agents already run in the Python mission platform. Autonomous control of this new Unreal rally, live CaP/LLM execution, online multiplayer, free-form vehicle geometry and ranked submissions remain future work.
