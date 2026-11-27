# 0019: Physical rivals and solid props in the Unreal race

Status: Accepted for the source; Unreal build and playtest pending.

[ADR 0018](0018-experimental-race.md) had Python move the rivals and Unreal draw them without collision. `race-0.2` and
`race-0.3` then kept rovers apart by moving rivals in Python. The owner found that rivals still drove through course
props and asked for real collisions between every solid object instead of a positional rule.

Decision, `race-0.4` / `race-drive-0.4`, Unreal backend only:

- **Unreal's physics places the rivals; Python drives and judges them.** Each NPC rival is the player's six-wheel rig
  (853.5 kg box, model-P wheels) under its look-alike meshes. Python sends each rival a command (speed and turn rate) in
  `mission_state`; Unreal reports each rival's pose and forward speed in its telemetry (`opponents`). Gates, laps,
  positions, charge, boosts and dust still come from Python, on the reported poses. Python no longer moves rivals or
  separates rovers when those poses arrive.
- **Solid props.** In a race, posts, flag poles, cairns, cones, the finish banner and the supply hut block every rover.
  Marks on the ground (pads, sand, the stones round a flag, the finish squares) do not. Rocks of 30 cm radius or more within
  40 m of the course get an invisible collision sphere, because the Poly Haven meshes are imported without collision.
- **Rovers meet body to body.** Race rigs have a restitution of 0.35 (a game setting) and their wheels stand on static
  objects only, so a wheel never climbs onto another rover.
- **Stuck rivals.** A rival that is commanded forward but makes no headway for 6 s is reset beside its path by Python.
  Rivals aim 1.6 m beside a flag's pole, inside the 2.5 m arrival radius.
- **Ghosts** stay records drawn without collision.

Not changed: missions, pinned scenarios, scoring and the benchmark `MODEL_VERSION`. Outside a race, props have no
collision, rigs keep restitution 0, and wheels trace as before. The headless race keeps the kinematic rivals and the
`race-0.3` contact rule, so headless and Unreal results stay on separate boards.

Consequences: Unreal race results now depend on physics and frame rate and are not reproducible. Five rigs instead of one
cost more frame time; this is unmeasured on the MacBook Air. Unreal C++ older than this change sends no `opponents`, and
Python then falls back to the kinematic rivals.
