# G0 to G2 on the MacBook Air: a work plan

**Status: a plan, 2026-11-07.** Nothing here is installed, built, or measured on the MacBook Air yet. Sizes and
times marked *measured* come from the M4 Mac's [records](macos-checklist.md#unreal-results-on-this-mac), and the
others are estimates to check. The gates are in [release-gates.md](release-gates.md).

**Owner decisions before any step below:** install UE 5.8.4 on the Air, and record it in a new ADR that extends
[ADR 0012](decisions/0012-m4-mac-for-unreal.md) to this machine.

## The machine

| Item | Value | How known |
| --- | --- | --- |
| Model | MacBook Air, Apple M5, 10 cores, 16 GB, no fan | `sysctl`, 2026-11-06 |
| macOS, Xcode | 27.0.1; Xcode 27.2 installed | `sw_vers`, `xcodebuild -version` |
| Free disk | 361 GB of 460 GB | `df`, 2026-11-06 |
| Unreal | Not installed | — |
| Python and C++ checks | Pass at `1db38a0` | [project-status.md](project-status.md) |

ADR 0013 accepted UE 5.8.4 with Xcode 27.2 on macOS 27.0.1 for the M4 Mac only. The same versions on the Air
are expected to behave alike, and that is to be measured, not assumed.

## Capacity

| Use | Size | Basis |
| --- | --- | --- |
| UE 5.8.4, Mac platform only | 43 GB | *Measured* on the M4. The Launcher had shown 15.6 GB |
| Derived data and shader caches | 10–30 GB | Estimate; grows with materials and Landscape |
| `unreal/` with `Intermediate`, `Saved`, `Binaries` | 5–10 GB | Estimate; today `Saved/` holds about 1 GB of experiments |
| Packaged game | About 1 GB now, growing | *Measured* 885 MB for the empty module |
| One HiRISE DTM and its orthoimages | 1–5 GB | Estimate; the STAC listing gives no file sizes |
| Poly Haven and Material Maker sources | 2–5 GB | Estimate, at 2K to 4K textures |
| **Total to plan for** | **About 100 GB**, leaving more than 250 GB free | |

**Memory.** On the M4 Mac, the editor peaked at 5.6–8.3 GB in a 9-million-triangle test scene, and swap grew from
3.9 to 5.4 GB with other applications open (*measured*). With 16 GB on the Air:
- Keep one editor and no packaged game open at once; close browsers during measurements.
- Keep the stop rule of ADR 0013: stop if free memory falls below 10%.
- Set the editor's texture streaming pool and the number of shader compile workers low in `Dev`, recording the values.
- Target: editor at or below 10 GB in the alpha level.

## G0 on the Air: what to measure

Each item is recorded with engine version, machine, profile, and date. The fanless case makes the last two items
the important ones.

| # | Measure | Method | Comparable with the M4? |
| --- | --- | --- | --- |
| 1 | Installed size, and free disk before and after | Launcher, `df` | Size, yes |
| 2 | Editor start, first and second | Wall clock | Within method only |
| 3 | `unreal/` C++ build, clean and incremental | `Build.sh` wall time | Within method only |
| 4 | `Roverloom.Module.Loaded` | Automation test | Yes, pass or fail |
| 5 | `git status` clean after an editor session | `git status` | Yes |
| 6 | The M4's five-profile test scene: FPS, frame ms mean and p95, GPU ms, memory peak | `csvprofile`, same scene and viewport | **Method only.** Different hardware |
| 7 | Packaging with `-package`, and running the `.app` | `BuildCookRun` | Pass or fail |
| 8 | Port `*:1985` still open in the packaged build | `lsof -i` | Yes; the [open issue](security.md#unresolved) |
| 9 | **25 minutes in the software-Lumen profile**: frame time p50 and p95 per minute, memory, swap | `csvprofile` over time | No. This measures the Air's thermal behavior |
| 10 | **Thermal state** during item 9 | `pmset -g therm` each minute, which needs no administrator rights | No |
| 11 | Optional: Unreal MCP read-only check | [unreal-mcp.md](unreal-mcp.md) plan | Yes, pass or fail |

**G0 is done** when items 1 to 10 are recorded in [macos-checklist.md](macos-checklist.md), or a failure is recorded
with its cause.

## G1: the drive model

**First, before any run:** write and commit phase G's registered design, from the starting values in
[release-gates.md](release-gates.md#g1-drive-model-decision), in a new `docs/results/drive-model/` directory.

| Task | Where | Test | Size |
| --- | --- | --- | --- |
| Kinematic model K: commanded speed and yaw rate move the body in the plane; six wheel heights from line traces; rocker-bogie angles solved from wheel heights, with the differential linking the two rockers; body pitch and roll from the rockers; speed reduced by the Mission Core's slip formula | `unreal/Source/Roverloom/Rover/KinematicDrive.{h,cpp}` | Automation tests: flat, 10° slope, a 25 cm step, each wheel's height within 0.5 cm of the ground | 3–4 days |
| Model P, the wheel model with gated PGS, behind the same rover | Reuse `WheelSpike/WheelModel` | Phase G batch | 1 day |
| Optional, owner's approval: D's diagnostic mode, and the input conditioning of option 1 in the [stall analysis](results/unreal-wheel-model/stall-geometry.md#a-proposal-for-gate-g1-not-adopted) | [Design](results/unreal-wheel-model/unreal-d-diagnostic-design.md) | Shadow batch, then phase G | 3–5 days |
| Phase G runs for each candidate built | New batches under `unreal/Saved/`, never over old ones | Registered criteria | 1–2 days |
| ADR naming the drive model, mass, inertia, and limits | `docs/decisions/` | Review | 0.5 day |

K's slip uses the Mission Core's documented formula as a game rule, and inherits its [limits](model-assumptions.md).

## G2: greybox playable

**Owner decision, 2026-11-07:** G2 starts without G1. The first drive model is the existing wheel model P, from
`WheelSpike/`, labeled provisional on screen; K replaces it if P misbehaves in play. Work runs on the Mac mini's
existing UE 5.8.4 over Tailscale, so the Air needs no Unreal install for this milestone.

| Task | Where | Test | Size |
| --- | --- | --- | --- |
| Test map spawned from C++, with no new assets: flat ground, 10° and 15° slopes, a 25 cm step | Game mode, as `WheelSpikeGameMode` spawns blocks | Opens from a clean clone | 0.5 day |
| `ARoverPawn` with the G1 drive model, from `pathfinder_6w`'s parameters | `Source/Roverloom/Rover/` | Spawns and drives | 1 day |
| One input path: keyboard to an `Action` with linear speed and yaw rate, then a router, as [command.py](../python/src/roverloom/command.py) does | `Rover/CommandRouter.{h,cpp}` | Same clamping as Python on the same inputs | 1–2 days |
| Enhanced Input actions created in C++, so that no `.uasset` is needed yet | Pawn setup | Keys work | 0.5 day |
| Watchdog: zero velocity after 2 s without an accepted command | Router | Automation test | 0.5 day |
| Cameras: chase on a spring arm, mast at 2.0 m, front hazard camera low and wide, free camera | Pawn | Switching changes no physics value | 1 day |
| HUD drawn by `AHUD` canvas: speed, yaw rate, slope, battery placeholder, input source, watchdog | `Rover/RoverHud.{h,cpp}` | Screenshot | 0.5 day |
| Frames: port `frames.py` to one C++ file | `Bridge/Frames.{h,cpp}` | Automation test over every vector in `schemas/conformance/frame_vectors.json` | 1 day |
| Run logs in the shared formats: `run.json` with hashes, `telemetry.jsonl`, `commands.jsonl`, events, with a distinct `backend` and `model_version` | `Logging/RunLog.{h,cpp}` | `check_run_contract` passes; `roverloom score` runs | 2–3 days |

**G2 is done** when a person has driven for 10 minutes, the watchdog test passes, the frame vectors all match, and a
run's logs pass the contract check and score in Python. Record a short video outside Git.

## Order and critical path

```text
G0 install + measure (1–2 days)
 └─ register phase G ── K (3–4 days) ── phase G runs ── ADR      (G1, at most 10 working days)
      └─ pawn, input, router, watchdog, cameras, HUD (4–5 days, can start with K)
           └─ frames + run logs (3–4 days) ── G2 check
```

K and the pawn can be built together, because the pawn only needs a drive model that moves. The shortest path to a
rover a person drives is G0, then K and the pawn, then cameras: about two weeks of one person's work, as a guess.
