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
- **One collision rule, by kind and size, never by place** (`Source/Roverloom/Rover/Collision.h`). In a race, every
  object is a solid body by default: posts, flag poles, cairns, cones, the banner, the hut, and any prop added later.
  Only marks drawn on the ground opt out (pads, sand, finish squares, the stones round a flag). A rock is solid when its
  radius is over 15 cm, wherever it lies and on every stage; smaller stones count as the ground's roughness. The rock
  collision belongs to the mesh asset (a 26-sided hull from `scripts/unreal/build_rock_collision.py`), so it moves and
  scales with every instance.
- **Rovers meet body and wheels.** A rig's box (2.0 x 1.5 m) is narrower than its wheel track (2.3 m), and the model
  wheels are traces, not bodies: in the second Mac run a rival drove alongside the player with its wheels 0.87 m into
  the player's for 15 s. In a race each wheel also has a solid sphere welded to the body (no mass of its own), which
  meets other rovers and obstacles but not the ground; the wheel model still finds the ground by its trace. Race rigs
  have a restitution of 0.35 (a game setting) and their wheel traces see only the ground (object type WorldStatic), so a
  wheel never climbs onto another rover or a post.
- **Ground or obstacle.** The ground and rocks are WorldStatic: wheels stand on them and climb them. Posts, poles,
  cairns and buildings are WorldDynamic: they block bodies and wheels and are not climbed.
- **Rivals see where they go.** Each rival sweeps ahead every frame (a box as wide as its body straight ahead, spheres
  30 degrees to each side, 5 m) and Unreal reports the free distances. Anything solid with a steep face counts, ground it
  can drive up does not. Python steers round it, keeps to the side it chose for 1.5 s, and backs off when nearer than
  0.9 m. No prop or rock position is known to Python.
- **Stuck rivals.** A rival that makes no headway (under 1 m in 6 s while driving, or in 12 s) is reset 2 m ahead of the
  nearest point of its path; Unreal moves it beside that point if the overlap test finds a body there.
- **Wide start and finish.** The banners are 7.2 m between their solid posts, so two rovers abreast pass. In the first
  Mac run (2026-11-27) with 4.25 m banners, rivals starting on the outer grid places hit the start posts and two were
  reset there again and again.
- **Ghosts** stay records drawn without collision.

Not changed: missions, pinned scenarios, scoring and the benchmark `MODEL_VERSION`. Outside a race, props have no
collision, rigs keep restitution 0, and wheels trace as before. The headless race keeps the kinematic rivals and the
`race-0.3` contact rule, so headless and Unreal results stay on separate boards.

Consequences: Unreal race results now depend on physics and frame rate and are not reproducible. The rocks need
`build_rock_collision` once (run by `setup_gale.py`); without it they are not solid and the log says so. Five rigs instead of one
cost more frame time; this is unmeasured on the MacBook Air. Unreal C++ older than this change sends no `opponents`, and
Python then falls back to the kinematic rivals.
