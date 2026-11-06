# Product quality vision

**Status: a plan, written on 2026-11-07.** Nothing in this page beyond the inventory has been built or measured.
**Every number below is a provisional design target, not a measurement.** Targets change only by a dated edit
that says why. Gates and their tests are in [release-gates.md](release-gates.md).

## The goal

A Mars rover simulation game that people want to play for its own sake, that a planetary scientist would not
wince at, and that looks like a robot's photograph from Mars. It is released publicly, with its limits stated.

Three qualities are judged separately. Passing one never implies another:

| Quality | Question it answers | Judged by |
| --- | --- | --- |
| Scientific credibility | Is what it shows grounded, and is what is invented labeled? | Sources, labels, plausibility tests |
| Fun | Do players choose to finish a mission, and to play again? | Playtests with people outside the project |
| Visual quality | Does a still frame read as Mars? | Side-by-side comparison with credited rover images |

The [Python Mission Core](architecture.md) stays the authority for scoring and competitions. The game is a
player of the same contract, not a second scorer ([ADR 0002](decisions/0002-backend-neutral-contract.md)).

## Where the project stands

Measured or tested today, in the [README](../README.md) and [project status](project-status.md):

| Exists | Does not exist |
| --- | --- |
| Mission Core: 2.5D kinematic model, faults, delay, loss, science, data windows, scoring from logs | Any playable Unreal level |
| Rover Builder, three standard rovers, Pareto analysis | A rover that drives in Unreal for players |
| Agents, typed skills, leagues, a scientific study, Mission Control in a browser | Terrain from real Mars data |
| Bridge protocol v1 and frame conversions, tested with a Python stand-in | The bridge in C++ |
| An Unreal C++ project with two physics experiments | Materials, sky, rocks, dust, cameras, HUD |
| A wheel model that passed one- and two-wheel tests, and a six-wheel version that **failed 7 of 9** | A packaged game, a license, a public release |
| Method D, a contact solver, researched in Python and standalone C++ | Method D in Unreal. Only a [design](results/unreal-wheel-model/unreal-d-diagnostic-design.md) exists |

The imbalance is the main risk. The competition platform is far ahead of the game. Physics work has gone through
R0 twice, three wheel-model attempts, phase C, and solver research, past its
[3-day timebox](vertical-slice-plan.md#physics-spike-timebox-3-working-days), and no drive model has yet passed a
six-wheel gate. [release-gates.md](release-gates.md#g1-drive-model-decision) bounds it.

## What the references show, and what Roverloom takes from them

**Observed** lists only what the cited source states. **Taken** is a proposal for Roverloom. No reference is
copied: Roverloom's rover, site, missions, art, and names are its own, and it is not affiliated with or endorsed by
NASA, JPL, or any studio.

### NASA's Eyes on the Solar System, and Experience Curiosity

Observed:
- Eyes visualizes the trajectory data that mission navigation uses, and NASA notes that location, motion, and
  appearance come from predicted and reconstructed mission data
  ([JPL](https://www.jpl.nasa.gov/news/follow-nasas-perseverance-rover-in-real-time-on-its-way-to-mars/)).
- An update on 2026-08-04 added full Mars terrain that desktop users can land on and explore
  ([NASA Eyes release notes](https://science.nasa.gov/blogs/eyes/2026/09/03/nasas-eyes-software-august-release-notes/)).
- Experience Curiosity, a browser tool, offered Free Drive by clicking a spot on the terrain, Rover Replay of
  reenacted events, and operating rover components, on a 3D scene built from Curiosity and MRO data
  ([NASA](https://eyes.nasa.gov/curiosity/), [Khronos](https://www.khronos.org/news/permalink/blend4web-nasa-and-the-curiosity-rover)).

Taken:
- **Say where every piece of data comes from, on screen.** Terrain shape "from HiRISE DTM `<product>`", fine detail
  "generated", events "Mars-inspired" or "stress test", speed "faster than real rovers".
- **Click-to-drive as well as direct driving.** A target on the terrain becomes a typed `drive_to` skill call, so
  players use the same plans that agents do.
- **Replay as a first-class mode.** Mission Core logs already replay kinematically. The game replays its own runs.

### JPL's rover simulation (ROAMS, on DARTS)

Observed: ROAMS is a physics-based tool for designing, testing, and operating planetary rovers, built on the DARTS
dynamics engine, with terrain from elevation maps and 3D rocks
([JPL Robotics](https://robotics.jpl.nasa.gov/what-we-do/research-tasks/roams-rover-modeling-and-simulation),
[DARTS Lab](https://dartslab.jpl.nasa.gov/References/pdf/isairas03-roams.pdf)). A JPL task page states that
kilometer-scale HiRISE terrain exceeded ROAMS's data-size limits at the time it was written
([JPL Robotics](https://robotics.jpl.nasa.gov/what-we-do/research-tasks/large-scale-terrain-support-in-roams/)).
A 2026 preprint describes DARTS combining rigid contact with Bekker–Wong terramechanics ([arXiv 2606.06790](https://arxiv.org/pdf/2606.06790)).

Taken:
- **The gap is honest and permanent.** Roverloom has no terramechanics, and its rover is a game model. The game
  says "plausible for play", never "validated", as [model-assumptions.md](model-assumptions.md) requires.
- **Plausibility tests are part of the product.** Free fall, static load, slope hold, and step climb run as
  automated tests, and their results are published with the game.

### Juno: New Origins

Observed: a 3D space sandbox, formerly SimpleRockets 2, with part-based craft building, designer rocket engines,
advertised realistic rocket physics and orbital mechanics, planet creation, and Vizzy, a visual programming language
for automating craft ([Steam](https://store.steampowered.com/app/870200),
[Space.com](https://space.com/juno-new-origins-game-launch-rockets-build-planets)). Space.com notes that the physics
can make the learning curve steep.

Taken:
- **Automation as play.** Roverloom's typed skills are its counterpart to Vizzy, and they are data, not code
  ([ADR 0008](decisions/0008-skills-are-data-not-code.md)). A player writes a short plan, sends it across the
  communication delay, and watches it run.
- **Depth on request.** The first mission teaches one idea at a time. Rover design and agents stay in later modes.

### Mars First Logistics

Observed: a physics-based game by Shape Shop, 1.0 on 2025-09-26, in which players build rovers from over 50 parts
and deliver awkward cargo across procedurally generated Mars terrain, solo or in co-op
([Steam](https://store.steampowered.com/app/1532200), [Space.com](https://www.space.com/entertainment/space-games/mars-is-the-ultimate-sandbox-in-mars-first-logistics-a-physics-based-delivery-game-where-you-build-your-own-rovers)).
The Steam page showed "Very Positive" English reviews when checked.

Taken:
- **A physical problem is the fun.** The player reads the slope, the rock, and the battery, and chooses a route.
- **Readable failure.** When the rover slips or stalls, the HUD shows why, from the wheel model's own numbers.
- **Not taken:** a stylized look, and free-form part building in the alpha. Roverloom aims at a photographic look,
  and its Rover Builder is parameter-based ([ADR 0007](decisions/0007-rover-designs-compile-to-parameters.md)).

## Quality targets

Targets are provisional. Each names how it will be measured, so that it can be passed or failed.

### Scientific credibility

| Target | Measure |
| --- | --- |
| Terrain shape from one public HiRISE DTM, with its product ID and CC0 credit in the game | Import check: known elevation differences match the source within the DTM's stated vertical accuracy |
| Detail below the DTM's resolution is labeled generated | Present in the credits and the site info panel |
| Gravity 3.71 m/s², and the rover's free fall matches within 1% | Automated test |
| Sky, Sun, and dust parameters cite sources, as in the [production plan](unreal-production-plan.md#lighting-and-atmosphere) | Review of the parameter table |
| Every compressed or invented value is said to be so: drive speed, time scale, communication delay, event rates | Text review of HUD, tutorial, and credits |
| No claim of validation, novelty, or NASA endorsement | `test_docs.py`-style checks on shipped text, and review |

### Fun

| Target | Measure |
| --- | --- |
| A first-time player finishes the alpha mission in 15–25 minutes | Playtest timing, median of at least 5 people outside the project |
| At least 4 of 5 playtesters finish without help after the tutorial | Playtest record |
| Each run poses at least three real choices: route, which target to inspect, when to send data | Mission design review, and logged decisions per run |
| A failed run explains its cause | Playtester can name the cause; logged cause matches |
| At least half of playtesters ask for, or start, a second run | Playtest record |

### Visual quality

| Target | Measure |
| --- | --- |
| Three `Capture` frames, at noon, late afternoon, and sunset, read as Mars beside credited rover images | Side by side, judged by named reviewers; their names and verdicts are recorded |
| No oversaturated red, Earth-blue day sky, strong bloom, or visible tiling from the mast camera | Reviewer checklist from the [production plan](unreal-production-plan.md#visual-direction) |
| Dust plumes, tracks, and haze present in play | Checklist on `Dev` and `Capture` |

### UI

| Target | Measure |
| --- | --- |
| The HUD shows speed, battery, slope, wheel slip, communication delay, and the next data window | Checklist |
| Every control is reachable from keyboard and from mouse, and is listed in an in-game help panel | Checklist |
| Text readable at 1440 × 900 on a 13-inch screen | Screenshot review |

### Stability

| Target | Measure |
| --- | --- |
| 10 consecutive full missions without a crash, hang, or rover explosion | Scripted run log |
| The watchdog stops the rover within 2 s of losing commands | Automated test, as in the Mission Core |
| Logs from every run pass `check_run_contract` and score with `roverloom score` | Automated |

### Performance, measured on the development MacBook Air (Apple M5, 16 GB)

Graphics quality and performance are separate targets, as in the [Mac plan](mac-unreal-plan.md#quality-without-lowering-the-final-result).
The Air has no fan, so every performance target is measured over a full 25-minute session, not a short burst.

| Profile | Target |
| --- | --- |
| `Play` (packaged game) | 30 FPS or better at the 95th percentile of frame time, over 25 minutes; internal resolution at least 1280 × 800, upscaled |
| `Dev` (editor) | 20 FPS or better in the alpha level, so that tuning stays practical |
| `Capture` | No real-time target. The highest settings that complete reliably |
| Memory | Peak resident memory of the game at or below 10 GB, so that 16 GB leaves room for the system |
| Wheel physics | At or below 2 ms of game-thread time per 60 Hz step, at the 99th percentile |

If `Capture` cannot reach the look on the Air, the owner decides on another machine. The target is not lowered
quietly.

### Public release quality

| Target | Measure |
| --- | --- |
| A license is selected, and the EULA terms for distributing Unreal builds are read by the owner | `LICENSE` file; owner's record |
| Every asset has a source and license in [assets-and-sources.md](assets-and-sources.md) | Review |
| No restricted asset, secret, or personal data in the repository or build | `check_repo.py`, and a build content listing |
| The open [security issues](security.md#unresolved) that affect a public build are fixed or stated | Review |
| A known-limits page ships with the build | Present |

## The playable alpha

One site, one rover, one mission. Everything else waits.

| Part | Scope |
| --- | --- |
| Site | About 1 km × 1 km from one HiRISE DTM, chosen with the owner. Landscape, generated fine detail, PCG rocks |
| Rover | `pathfinder_6w`, an original six-wheel design, with rocker-bogie articulation shown |
| Mission | 15–25 minutes: reach three science targets, choose which to inspect or sample, send data in orbiter windows, return to a safe zone, with battery and one Mars-inspired fault |
| Control | Direct driving, and click-to-drive, through the one `Action` path. Short typed plans sent across a compressed delay |
| Cameras | Chase, mast, hazard, and free |
| Scoring | Unreal writes Mission Core logs. Python scores them. The HUD shows a provisional score, labeled as such |
| Out of scope | Rover building in 3D, multiple sites, online play, real language models, terramechanics |

The [mission core](lightweight-models.md) already has the rules for targets, data windows, faults, and scoring. The
alpha reimplements their effects in Unreal from the same scenario file, as the [contract](unreal-contract.md)
requires, and gets a new `model_version`.

## Conflicts with earlier plans, and how they are settled

| Earlier statement | Where | Now |
| --- | --- | --- |
| Repository is private | [roadmap.md](roadmap.md), [mac-unreal-plan.md](mac-unreal-plan.md) step 10 | Public since 2026-11-06. The roadmap is updated; the Mac plan keeps its record, superseded here |
| The vertical slice excludes missions and faults | [vertical-slice-plan.md](vertical-slice-plan.md#goal) | The alpha includes one mission and one fault. The slice remains its first part (gates G2–G3) |
| Physics spike timeboxed to 3 days | [vertical-slice-plan.md](vertical-slice-plan.md#physics-spike-timebox-3-working-days) | Overrun. [G1](release-gates.md#g1-drive-model-decision) sets a new, explicit timebox and a fallback |
| Rover mass 1000 kg | [production plan](unreal-production-plan.md#standard-rover) | The wheel model's rig uses 853.5 kg. G1 must state which mass the alpha uses, and why |
| 1440p and 60 FPS | [vertical-slice-plan.md](vertical-slice-plan.md#graphics-quality-requires-b-or-c-hardware) | Was for a discrete-GPU PC. The Air targets are above, and are unmeasured |
| Unreal on the M4 Mac | [ADR 0012](decisions/0012-m4-mac-for-unreal.md) | Development now also runs on a MacBook Air, where Unreal is not installed. Installing it is the owner's decision, and needs a new ADR |
| Deterministic stepping in Phase 3 | [roadmap.md](roadmap.md#phase-3-autonomous-agents) | Not needed for the alpha. Real-time Unreal runs stay unranked |

Phase C's verdict, 2 of 9, its criteria, and ADR 0014's status are unchanged by this page.
