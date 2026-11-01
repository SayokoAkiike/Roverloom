# Vertical slice plan

Status: plan, nothing implemented. Reviewed 2026-11-02. Numbers are design targets to test,
not measured results. Mars values below are widely cited approximations to confirm against
references during implementation.

## Goal

One small Martian site, a standard six-wheeled rover, keyboard and Python driving,
camera switching, and logs that can be replayed.

**Out of scope:** missions beyond reaching a point, fault injection, rover editor,
multiple rovers, networking beyond loopback, learning, terramechanics, packaged releases.

## Site

- About 1 km × 1 km from a [NASA/USGS HiRISE DTM](https://registry.opendata.aws/nasa-usgs-mars-hirise-dtms/),
  listed as CC0. Pick a tile with varied slopes, rocks, and dunes after viewing candidates.
- Terrain system: **Landscape by default.** Mesh Terrain is reported as experimental, so
  try it only in a timed spike if overhangs are needed.
- DTM resolution is far coarser than wheel scale. Add procedural mid and fine displacement,
  plus scattered rock meshes. Keep a label separating "measured" from "generated" detail.
- Raw DTMs and derived source stay out of Git unless small. Commit a script and citation
  that reproduce them.

## Visuals

| Element | Approach |
| --- | --- |
| Regolith | Layered material: macro color from reference, CC0 or original detail textures, slope and rock blending |
| Rocks | Original or CC0 meshes placed by PCG; Fab only in `Content/Licensed/` for private look tests |
| Sky | Custom Sky Atmosphere: weak molecular scattering, strong dust with blue absorption, about 3390 km planet radius, about 11 km scale height |
| Sun | About 590 W/m² at mean distance, smaller apparent disk; butterscotch day and bluish halo near sunset |
| Dust | Height fog for optical depth, Niagara wheel plumes, slow wind-borne dust |
| Tracks | Runtime virtual texture decals; real deformation later |

Sky references: [Pathfinder sunset caption](https://pds-rings.seti.org/press_releases/pages/PIA00xxx/PIA00917.html)
and [Ehlers et al., Applied Optics](https://profiles.wustl.edu/en/publications/blue-moons-and-martian-sunsets/).
Collect rover images with credits for side-by-side comparison, stored outside Git unless
their terms are confirmed.

## Rover

Original design, not a replica of a NASA rover.

- About 1000 kg, 0.5 m wheels, six independently driven wheels, rocker-bogie suspension.
- Drive speed cap is configurable. Real rovers move at centimeters per second; the slice
  defaults to about 0.5 m/s for usability. The HUD and docs state that this is not realistic.
- Defined by data, so future custom rovers require no code: mass and inertia, link geometry,
  wheel positions, wheel radius, and motor limits. Add `schemas/rover.schema.json` with
  the first implementation, and keep visual meshes separate from physical parameters.

### Physics spike (timebox: 3 working days)

| Candidate | Evaluate | Risk |
| --- | --- | --- |
| Chaos Wheeled Vehicle | Quick baseline | Car oriented; six wheels and rocker-bogie unverified |
| [Chaos Modular Vehicle](https://dev.epicgames.com/documentation/unreal-engine/chaos-modular-vehicles) | Configurable vehicle graph | Documentation is thin; status for 5.8 unconfirmed |
| Articulated rigid bodies with custom C++ wheel contact | Rocker and bogie joints, wheel-level torque and slip | Most work; stability needs tuning |

Prior expectation: the third fits best, because suspension articulation and per-wheel
faults are core to Roverloom. Decide from the validation tests below, and record an ADR.

## Controls and cameras

- Keyboard through Enhanced Input: forward/back, turn, stop, source toggle, camera cycle.
- Maps to the `Action` schema: linear velocity and yaw rate. Python uses the same path.
  See [unreal-integration.md](unreal-integration.md).
- Cameras: chase, mast (first-person), wheel close-up, free observer. Switching never
  changes physics, and does not appear in rover state.

## Logging and replay

Each run writes to `runs/<timestamp>/`, ignored by Git:

| File | Contents |
| --- | --- |
| `run.json` | Scenario and hash, git commit, engine version, rover definition hash, seed, settings, machine, scene assets |
| `telemetry.jsonl` | Ground truth at 20 Hz, one schema-valid record per line |
| `actions.jsonl` | Received and applied Actions, source, and clamping |

At about 200–500 bytes per record, one hour is about 14–36 MB.

**Schema change:** Replay needs joint and wheel poses. Add optional per-wheel fields and
suspension angles to Telemetry when implemented, with tests.

**Replay is kinematic.** It plays poses from telemetry with interpolation, and cameras
stay free. It reproduces what happened without requiring physics to be deterministic.
Python validates logs and can plot trajectories without Unreal. Full determinism is a
Phase 3 topic, and replay must not be presented as proof of it.

## Evaluation: two separate reports

Passing one never implies the other.

### Graphics quality (requires B or C hardware)

- Fixed camera shots at noon, late afternoon, and sunset, compared side by side with
  credited rover images. Reviewers rate color, light, scale, and surface detail.
- Performance recorded per profile: FPS, GPU and memory use, resolution, settings, machine.
- Targets: 1440p and 60 FPS on the quality machine; stable interaction on the laptop.

Photorealism is a judgment, not a measurement. Report what was compared and who judged it.

### Physical plausibility (works on any hardware)

Automated where possible, with numbers logged:

| Test | Expected result |
| --- | --- |
| Free fall | Acceleration 3.71 m/s² within tolerance |
| Static load on flat ground | Total normal force equals weight; per-wheel loads match the design |
| Step response | Reaches and holds commanded speed without oscillation |
| Turn | Measured yaw rate matches command; correct sign |
| Slope | Holds or climbs up to a design slope; slip recorded |
| Obstacle | Climbs a step near one wheel diameter with rocker-bogie articulation |
| Time step | Results converge when physics step is halved |
| Stability | One-hour random drive with no explosions or penetration |
| Repeatability | Spread across repeated runs is reported, not assumed zero |

**Limitation to state in all results:** This is a rigid-body approximation with simplified
contact. Without validation against rover data or terramechanics, including Bekker-style soil
models, it is "plausible for game and early autonomy use", not scientifically validated.

## Extension points

Only these are built now, since each has a planned user:

- Rover defined by data: future custom rovers.
- Single Action input path: future agents use what Python uses.
- Scenario, telemetry, and manifest files: future evaluator and lightweight backend.
- Named scalability profiles: varied hardware.

No plugin framework, agent registry, or backend abstraction layer for now.

## Milestones

Durations are rough estimates for one person.

| # | Deliverable | Machine | Estimate |
| --- | --- | --- | --- |
| 0 | Python client, fake server, log and replay tools | Current | 1 week |
| 1 | UE 5.8 installed, baseline measured, MCP verified read-only | Current | 2–3 days |
| 2 | Fresh project in Git, clean clone builds | Current | 2–3 days |
| 3 | Physics spike and ADR | Current | 3 days |
| 4 | Rover driving by keyboard on test terrain; validation suite | Current | 2–3 weeks |
| 5 | Python bridge; logs and replay | Current | 1–2 weeks |
| 6 | Real terrain and cameras | Current, quality machine helps | 1–2 weeks |
| 7 | Lighting, sky, dust, materials; graphics report | Quality machine | 2–4 weeks |

## Completion criteria

- A fresh clone opens without restricted assets, with substitutes if needed.
- Keyboard and Python drive the same rover, and the watchdog stops it.
- Cameras switch. A run's log validates in Python, and replays in Unreal.
- Both evaluation reports are published in `docs/` with honest limits.
- Asset list and licenses are complete.
