# Experimental rover race

A kart-style lap race for the rover you build in the garage. You race NPC rovers in real time, race the ghosts of saved
runs, and put finished runs on a leaderboard. In Advanced mode an autonomous agent drives instead of you: a built-in
controller, a code-as-policy (CaP) planner, or your own program connected over a local socket.

These are game rules, kept apart from the scored mission benchmark ([ADR 0018](decisions/0018-experimental-race.md)).
Speeds, boosts, dust, battery and sand values are invented game settings, not rover or Martian measurements.

**Status, 2026-11-27.** The Python rules, NPCs, ghosts, leaderboard, agents and the lobby page have automated tests.
The Unreal C++ for the race (course markers, rival rovers, race HUD) was written in a cloud session without Unreal and
**has not been compiled or played yet**. The first build on a Mac is the next step.

## Quick start

From the repository root:

```shell
uv run --project python python -m roverloom.race_cli lobby
```

Open `runs/race/lobby.html`. Choose a mode, build the rover, pick the course, press **Save garage.json**, and copy the
start command. It looks like this:

```shell
uv run --project python python scripts/play_3d.py --race --garage ~/Downloads/garage.json --npcs 3 --ue-root "/Users/Shared/Epic Games/UE_5.8" --build
```

`--build` compiles the C++ first; leave it out once it has built. Click the game window once, then drive.

| Key | Action |
| --- | --- |
| W / S | Drive forward and back |
| A / D | Turn |
| SPACE | Boost: 1.5 times speed for 3 seconds, 8 charge units |
| C | Change camera |
| R | Rescue to the start pose, +30 seconds |

## Rules

- A three-second countdown, then the race clock starts. Gates must be passed in order. The last gate is the start and
  finish line. You finish after the set number of laps; the race ends when you finish.
- **Positions** are by laps, then gates, then distance to the next gate. Finished racers rank by time.
- **Boost pads** (teal squares) give one boost, at most three held, once every six seconds per pad.
- **Sand** (darker patch with amber corner posts) slows all-round tires to 55% and sand tires to 95%.
- **Supply pad** (amber, beside the hut) recharges the battery while you are on it.
- **Dust storms** come in the last four seconds of some 20-second slots, chosen by the seed. Everyone slows to 75%.
  The scout sensor warns eight seconds ahead instead of four.
- **Rivals do not collide** with you or each other. They are drawn where Python's race model puts them.

## Modes

| Mode | What it is | Start command option |
| --- | --- | --- |
| Grand Prix | You against up to five NPC rovers | `--npcs 3` |
| Time Attack | You against the ghosts of the best saved runs | `--npcs 0 --ghosts 3` |
| Advanced | An agent drives the rover | `--agent pursuit`, `cap` or `external` |

NPCs: Dune Runner (sand tires), Long Haul (endurance battery), Scout-7 (scout sensor), Regolith and Kestrel. Each
uses the same game rules as you. `--difficulty easy|standard|hard` sets their pace and the dust probability.

NPC pace is set against the race model, not measured against people driving the Unreal rover. If they are too fast or
too slow for you, change the difficulty.

## Courses

| Course | Lap | Default laps | Features |
| --- | --- | --- | --- |
| `crater_loop` | 46 m | 2 | Sand on the east turn, two boost pads, a supply pad |
| `dune_sprint` | 32 m | 3 | A short rectangle with a sand patch and one boost pad |

The rover's top speed is 0.5 m/s, as the drive model's limit, so a lap takes over a minute. The course is drawn on the
generated crater floor by default. `--map gale` uses the Gale level if it exists in `unreal/Content/Licensed/Gale/`;
that level is not in Git, and the course has not been checked for slopes or rocks there.

## Leaderboard and ghosts

Every finished race is saved to `runs/race/leaderboard.json`, with its time, lap times, rover and a path sampled four
times a second. `--ghosts N` adds the N fastest saved runs of the same course, laps and backend as ghosts.

```shell
uv run --project python python -m roverloom.race_cli board
uv run --project python python -m roverloom.race_cli export a570cb11 --out my-run.json
uv run --project python python -m roverloom.race_cli import their-run.json
```

To compare with friends without a server, send the exported file; they import it and race your ghost. Boards are kept
apart by course, laps, backend (`unreal` or `headless`) and driver (human or agent). **Entries are not verified:**
anyone can edit a file. There is no online ranking or anti-cheat.

## Advanced mode: agents

An agent sees the same information as the HUD and nothing more: a brief with the course, laps, garage and limits, and
an observation every 0.1 seconds with its position, heading, speed, lap, the next three gates, position in the race,
charge, boosts, sand and dust flags, and the rivals' positions. It never sees the seed, future dust or NPC plans.

Built-in agents:

- `pursuit`: steers at the next gate and boosts on long straights. A baseline to beat.
- `cap`: code-as-policy. A plan is a list of typed race skills with bounded arguments, checked as data
  (`follow_checkpoints`, `boost_on_straights`, `detour_sand`, `visit_supply`), and run by a fixed executor. A new plan
  is requested after every lap; an invalid plan is refused and the last valid one is kept. The plan source is a
  rule-based stand-in for a language model: **no language model is called**.

Race an agent without Unreal, on the race model (deterministic for one seed):

```shell
uv run --project python python -m roverloom.race_cli headless --agent cap --npcs 3
```

### Connect your own agent

Your agent is a separate program, in any language. The race listens on `127.0.0.1:8101` (loopback only) and speaks
JSON Lines, protocol `race-agent-1`:

```text
race  -> agent  {"type": "race_brief", "body": {...}}
agent -> race   {"type": "hello", "body": {"name": "My Agent"}}
race  -> agent  {"type": "race_observation", "body": {"tick": 12, "position_m": [x, y], "yaw_rad": 0.1, ...}}
agent -> race   {"type": "race_action", "body": {"tick": 12, "linear_velocity_mps": 0.5, "yaw_rate_radps": 0.1, "boost": false}}
```

Start the race with `--agent external`, then the agent. The example uses only the standard library:

```shell
uv run --project python python -m roverloom.race_agent_example --name "My Agent"
```

Copy [`race_agent_example.py`](../python/src/roverloom/race_agent_example.py) to start your own. Speeds are clamped to the
rover's limits. In real time, an agent that does not answer for a second is stopped; in `headless` mode the race waits
up to a second for each answer. Unreal results are real time and are not reproducible; use `headless` to compare agents.

An LLM agent fits the same loop: ask the model for a plan or parameters once per lap, check the answer as data, and keep
a plain controller in the loop. Do not run model output as code ([ADR 0008](decisions/0008-skills-are-data-not-code.md)).
This port is for your own agents on your own Mac. Never run an agent from someone you do not trust
([evaluator safety](evaluator-safety.md)).

## Recording a demo video

`--demo` lets the pursuit agent drive, so the race plays itself. `--record SECONDS` records the screen with macOS
`screencapture` into the run directory as `race.mov`; the terminal app needs Screen Recording permission in System
Settings. Neither has been tried on a Mac yet. Without `--record`, Cmd+Shift+5 records the screen.

```shell
uv run --project python python scripts/play_3d.py --race --demo --npcs 4 --laps 1 --light afternoon --res 1920x1080 --record 150 --ue-root "/Users/Shared/Epic Games/UE_5.8"
```

`--profile capture` uses the higher render settings; it ran at 15.6 fps on the Gale level on the M4 Mac mini, so use
`dev` (the default) for driving.

## On a MacBook Air (Apple M5)

Nothing in Unreal has been run on the MacBook Air yet. What is known:

- UE 5.8.4 with Xcode ran on the M4 Mac mini ([ADR 0013](decisions/0013-ue-5-8-4-on-macos-27.md)). The same steps should
  apply to an M5 Mac, but this is unmeasured.
- On the Mac mini, the Gale level ran at 34 fps with the `dev` profile at 1280 x 720
  ([results](results/gale-landscape/README.md)). The generated race ground has far fewer objects. A MacBook Air has no
  fan and slows down under long load, so expect lower and falling frame rates. Start at `--res 1280x720`.
- Installing Unreal and Xcode needs a few tens of gigabytes of disk. The Gale level and Poly Haven rocks are on the Mac
  mini only; without them, use the generated ground.

## What this is not

- Not a benchmark: real-time Unreal runs are not reproducible, and the drive model is provisional.
- Not a model of rover racing on Mars. Rivals are kinematic and pass through each other.
- Not an online game: the leaderboard is a local file, and the agent port is loopback only.
