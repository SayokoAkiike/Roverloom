# 0018: A lap race with NPCs, ghosts, a local leaderboard and an agent port, apart from scoring

Status: Accepted for the source prototype; Unreal build and playtest pending.

The owner asked for a kart-style race with the garage rover: positions against other players' times, real-time NPC
rivals, and an Advanced mode where autonomous agents, including CaP and LLM agents, drive. Add `race-0.1` rules and the
`race-drive-0.1` kinematic model in `roverloom.race`, beside the rally ([ADR 0017](0017-experimental-rally.md)). Do not
change pinned scenarios, scoring, `MODEL_VERSION` or `SCORING_VERSION`.

- **Python judges, Unreal draws.** Python owns gates, laps, positions, NPC motion and ghosts, and sends them in
  `mission_state`. Unreal renders the course from `course.json`, rival look-alikes without collision, and the HUD.
- **Other players through files.** The leaderboard is a local JSON file. Entries are exported and imported as data,
  checked for shape and size, and never executed. No server or account is added. Entries are not verified.
- **Agents as separate processes.** User agents connect to a loopback TCP port with JSON Lines (`race-agent-1`), so any
  language works and agent code never runs inside the race process. Built-in agents are a pursuit controller and a CaP
  executor whose plans are typed skills checked as data ([ADR 0008](0008-skills-are-data-not-code.md)). No language
  model is called, and none is required.
- **Backends ranked apart.** Headless (deterministic, race model) and Unreal (real time, physics) results, and human and
  agent drivers, are separate leaderboards.

Consequences: race times are game results, not league scores. NPC pace is tuned to the race model, not to people driving
the Unreal rover. Collisions between racers are not modeled. The C++ must be compiled and played on a Mac before the race
is called playable.
