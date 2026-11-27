# Experimental rover race

A kart-style lap race for the rover you build in the garage. You race NPC rovers in real time, race the ghosts of saved
runs, and put finished runs on a leaderboard. In Advanced mode an autonomous agent drives instead of you: a built-in
controller, a code-as-policy (CaP) planner, or your own program connected over a local socket.

These are game rules, kept apart from the scored mission benchmark ([ADR 0018](decisions/0018-experimental-race.md)).
Speeds, boosts, dust, battery and sand values are invented game settings, not rover or Martian measurements.

**Status, 2026-11-27.** The Python rules, NPCs, ghosts, leaderboard, agents and the lobby page have automated tests.
The first race version built and ran on a MacBook Air, on the generated ground, with NPCs and the HUD on screen. The Gale
courses, flags, cairns, rock corridor and `setup_gale.py` were added afterwards in a cloud session and **have not been
compiled or played yet**.

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
| Q / E, or 1 2 3 | Speed level: 35%, 70% or 100% of the top speed for W and S (starts at 100%) |
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
- **Rivals do not pass through you or each other.** Rovers touch as rectangles the size of the drawn models: yours
  from the sample arm 1.14 m ahead to the solar deck 1.75 m behind, 2.55 m wide; a rival 2.5 m long and 2.3 m wide.
  A rival overtakes a slower rover on the side with more room; when two touch, the rival is pushed clear, and if you
  drove into it you slow to 60% for 0.8 s ("Bump!"). A rover parked on a gate cannot block it: touching it counts as
  passing. Ghosts still pass through.
  This is race logic in Python, not Unreal physics: your rover's physics body does not touch the rivals' models.

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

| Course | Length | Laps | Ground | Features |
| --- | --- | --- | --- | --- |
| `gale_links` | 289 m loop | 1 | Gale | Six pin flags round an outcrop knoll, a 7 m climb, two boost pads, a supply pad at flag 3 |
| `gale_sprint` | 122 m, point to point | 1 | Gale | The first three flags of Gale Links; finish at flag 3. For short runs and demo videos |
| `noctis_spur` | 333 m, point to point | 1 | Noctis Labyrinthus | Round a layered spur on a trough floor, a trough wall to the east; climbs 8 m |
| `noctis_sprint` | 157 m, point to point | 1 | Noctis Labyrinthus | The first two flags of Noctis Spur |
| `amazonis_rim` | 351 m, point to point | 1 | Amazonis Planitia | Smooth dusty plains past a channel to the rim of a deep pit |
| `amazonis_sprint` | 160 m, point to point | 1 | Amazonis Planitia | The last two flags of Amazonis Rim |
| `crater_loop` | 46 m | 2 | Generated | Sand on the east turn, two boost pads, a supply pad |
| `dune_sprint` | 32 m | 3 | Generated | A short rectangle with a sand patch and one boost pad |

The Gale courses are on the real terrain of the Gale level (a HiRISE DTM, [results](results/terrain-gale/README.md)).
Each was routed on the heightfield so that the 4 m-baseline slope stays under 10 degrees with 3 m of clearance either side
(the steepest point on the path is 10.0 degrees). Flags are golf-style pins with a ring of pale stones the size of the
arrival radius (2.5 m); small cairns every 9 m show the way between them, and the HUD shows the flag number, its distance
and an arrow. Rocks are kept out of a 3.2 m corridor along the path and added beside it, so the ground along the whole
course is as detailed as at the start. Rivals follow the routed path; they do not slow on slopes as the Unreal rover does.

The rover's top speed is 0.5 m/s, as the drive model's limit: Gale Links takes about nine minutes and Gale Sprint about
four in the race model. Long courses use 70% of the battery drain of the short ones, so that they can be finished.

The Noctis Labyrinthus and Amazonis Planitia stages, their sources and what is measured, are described in
[stages.md](stages.md). Build them with `setup_gale.py --site all`.

### The Gale level on a new Mac

The Gale level, its rocks and ground textures are not in Git. Build them once (about an hour, and a few GB of downloads):

```shell
brew install gdal
```

```shell
uv run --project python python scripts/setup_gale.py --ue-root "/Users/Shared/Epic Games/UE_5.8"
```

It runs the existing steps in order and skips any whose output exists: HiRISE site and horizon, MOLA far field, Poly Haven
assets, then the Unreal Editor scripts `import_polyhaven`, `build_gale_material`, `build_rock_materials`,
`build_effect_materials` and `build_gale_level`, and, if Blender is installed, the V2 rover and its materials. The first
game start afterwards compiles the ground shaders, which takes minutes. **This script has not been run on a Mac yet.**

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
uv run --project python python scripts/play_3d.py --race --course gale_sprint --demo --npcs 4 --record 300 --ue-root "/Users/Shared/Epic Games/UE_5.8"
```

`--profile capture` uses the higher render settings; it ran at 15.6 fps on the Gale level on the M4 Mac mini, so use
`dev` (the default) for driving.

## Contact check

If rivals look as if they drive through your rover, one command records a run and checks it:

```shell
uv run --project python python scripts/play_3d.py --race --course noctis_sprint --diagnose --ue-root "/Users/Shared/Epic Games/UE_5.8" --build
```

The pursuit agent drives at 35% so that four `hard` rivals overtake from behind. The screen is recorded for 150 s
(`race.mov`), Unreal saves a screenshot whenever a rival is drawn within 3.2 m (`contact-*.png`), and the race stops
unranked after 80 s. The report compares the positions Python judged (`states.jsonl`) with where Unreal drew the
player's body and each rival (`RaceDraw` lines in `unreal.log`), both with the rover rectangles, and lists the closest
moments. Check an earlier run again with `uv run --project python python -m roverloom.race_cli diagnose [RUN_DIR]`.
The report also counts rover resets in `unreal.log` and how far the player moved. On 2026-11-27 it found the cause of
rivals driving through the player on Noctis Sprint: the course lies 10 to 15 m below the site origin, and the rover's
fall check reset it every frame below z = -10 m, so it never left the start and Python saw it far from the rivals. The
check is now 20 m below the start. The `RaceDraw` lines and screenshots need the C++ built after 2026-11-27.

## On a MacBook Air (Apple M5)

Nothing in Unreal has been run on the MacBook Air yet. What is known:

- UE 5.8.4 with Xcode ran on the M4 Mac mini ([ADR 0013](decisions/0013-ue-5-8-4-on-macos-27.md)). The same steps should
  apply to an M5 Mac, but this is unmeasured.
- On the Mac mini, the Gale level ran at 34 fps with the `dev` profile at 1280 x 720
  ([results](results/gale-landscape/README.md)). The generated race ground has far fewer objects. A MacBook Air has no
  fan and slows down under long load, so expect lower and falling frame rates. Start at `--res 1280x720`.
- Installing Unreal and Xcode needs a few tens of gigabytes of disk. Build the Gale level with `setup_gale.py` (above);
  without it, use the generated ground.
- On 2026-11-27 the race built and ran on a MacBook Air (Apple M5, 16 GB, Xcode 27.2, UE 5.8 from the Launcher) on the
  generated ground, with NPCs and the race HUD shown. No frame time was measured.

## What this is not

- Not a benchmark: real-time Unreal runs are not reproducible, and the drive model is provisional.
- Not a model of rover racing on Mars. Rivals are kinematic; contact between rovers is a game rule, not physics.
- Not an online game: the leaderboard is a local file, and the agent port is loopback only.
