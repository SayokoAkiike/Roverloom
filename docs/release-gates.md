# Release gates

**Status: a plan, written on 2026-11-07.** No gate after G0 has been attempted. Every threshold is a provisional
design target, set before any measurement, and changes only by a dated edit that says why. A gate passes only
on recorded measurements, with the engine version, machine, profile, and commit.

The goal and the quality targets are in [product-quality-vision.md](product-quality-vision.md). The order of
Unreal steps on the Mac is in [mac-unreal-plan.md](mac-unreal-plan.md); where the two differ, this page sets
the gates and that page keeps its procedures.

**Rules for every gate:**
- Register a gate's tests and thresholds in `docs/` and commit them before running the tests.
- A failed gate stays failed in its record. A new attempt is a new record, as with
  [phase C](results/unreal-wheel-model/phase-c-design.md), which stays failed, 2 of 9.
- The Python Mission Core stays the only scorer. Its `MODEL_VERSION` and `SCORING_VERSION` do not change for
  Unreal work.
- Real-time Unreal runs are not used for rankings.
- **Owner** marks a decision that only the owner makes.

## Overview

| Gate | Result | Depends on | Rough size, one person |
| --- | --- | --- | --- |
| [G0](#g0-development-base) | Verified tools on the development machine | — | Partly done |
| [G1](#g1-drive-model-decision) | A drive model chosen for the alpha, within a timebox | G0 | 2 weeks at most |
| [G2](#g2-greybox-playable) | A person drives the rover on test terrain, and the run scores in Python | G1 | 2–3 weeks |
| [G3](#g3-the-site) | The rover drives on a real-terrain site | G2 | 2–3 weeks |
| [G4](#g4-the-mission-loop) | One 15–25 minute mission, with a fault, scored from logs | G3 | 2–3 weeks |
| [G5](#g5-the-look) | The site reads as Mars in `Capture` frames | G3; parallel with G4 | 2–4 weeks |
| [G6](#g6-play-quality-and-stability) | Tutorial, HUD, and 10 clean missions in a row | G4, G5 | 1–2 weeks |
| [G7](#g7-playable-alpha) | A packaged alpha, playtested, with its limits published | G6 | 1–2 weeks |

Sizes are guesses, to plan with, not commitments.

## G0. Development base

| | |
| --- | --- |
| Items | Python and C++ tools verified on the MacBook Air; Unreal on a development machine; empty-project baseline |
| Acceptance | `pytest`, `ruff`, `mypy`, `check_repo.py`, and the contact solver's tests pass; Unreal opens `unreal/`, and C++ compiles |
| Test | The commands in [CLAUDE.md](../CLAUDE.md#commands); `stat unit` and memory in an empty level |
| Done when | Results are recorded in [project-status.md](project-status.md) and [macos-checklist.md](macos-checklist.md) |
| State | **Python and C++ done on the Air on 2026-11-07. Unreal is not installed there** |
| Owner | Install UE 5.8.4 on the Air, or keep Unreal work on the M4 Mac. Either needs a record superseding [ADR 0012](decisions/0012-m4-mac-for-unreal.md) |

## G1. Drive model decision

The game needs a rover that drives plausibly. It does not need the physics research to finish. This gate ends
that research's hold on the game, whatever its outcome.

**Candidates:**

| Name | What it is | State |
| --- | --- | --- |
| P | The six-wheel wheel model with its gated PGS solver, as now | Phase C failed 7 of 9, on convergence, an overshoot, and a motor-limited turn |
| D | The same model with method D, after the [diagnostic mode](results/unreal-wheel-model/unreal-d-diagnostic-design.md) | Not built |
| K | Kinematic: the body follows the terrain under commanded speed and yaw, with rocker-bogie angles solved from wheel heights, and slip from the Mission Core's formula | Not built. Closest to the Mission Core's own model |

**A new phase, G, judges them for play.** Its criteria are registered before any run. Phase C keeps its own.
Starting values to register:

| Test | Threshold |
| --- | --- |
| Straight drive at 0.5 m/s | Speed within 5% after 2 s, no oscillation above 2% |
| Turn in place at the commanded rate | Reaches the rate, or the HUD's limit for it, within 10% |
| Hold on 15°, and climb 10° | Drift below 1 cm/s holding; climbs without stalling |
| Step of 0.25 m, half a wheel diameter | Climbed in at least 4 of 5 tries |
| Time step 60 against 120 Hz | Final position within 5 cm after 10 s of the same commands |
| 25-minute random drive on the alpha's test terrain | No explosion, no penetration below 2 cm, no NaN |
| Cost | At or below 2 ms of game-thread time per step, 99th percentile, on the development machine |

**Method D: adopt, hold, or replace.** Decided from the [diagnostic mode](results/unreal-wheel-model/unreal-d-diagnostic-design.md)'s
shadow runs, if the owner approves building it, and from the
[stall analysis](results/unreal-wheel-model/stall-geometry.md).

| Decision | When |
| --- | --- |
| **Adopt D** for the alpha's rig | All of: natural residual above 1e-8 on at most 1% of shadow steps, and above 1e-6 on none; no `MakeSafe` rejection; D's solve time at most 1 ms at the 99th percentile and 2 ms at worst; and the rig with D passes phase G |
| **Hold D** and keep P | P passes phase G on its own, or D meets every accuracy condition but not its time |
| **Replace D** with P or K | Any of: residual above 1e-6 on any shadow step with no explained cause; stalls on more than 1% of steps; or D's work in Unreal exceeds 5 working days |

**Timebox: 10 working days from the day Unreal is usable for this work.** At the end, the first candidate in
the order D, P, K that passes phase G is the alpha's drive model. If none of D or P passes, K is used. K is always
buildable, because it needs no contact solver. The physics research can replace K later, only through a new gate.

| | |
| --- | --- |
| Acceptance | Phase G recorded for each candidate tried; the choice recorded in an ADR |
| Done when | The ADR names the drive model, the rover mass and inertia it uses, and its known limits |
| Owner | Approves building the diagnostic mode; approves the ADR |

## G2. Greybox playable

| | |
| --- | --- |
| Items | Test map with flat ground, slopes, and steps; the G1 rover; Enhanced Input to `Action`; chase, mast, hazard, and free cameras; watchdog; minimal HUD; logs in the shared formats; `frames.py` ported to one C++ file |
| Depends on | G1 |
| Acceptance | A person drives it for 10 minutes; the watchdog stops it within 2 s of lost input; its logs pass `check_run_contract` and score with `roverloom score`; the C++ frame conversion matches every [golden vector](../schemas/conformance/frame_vectors.json) |
| Test | Unreal automation tests for input, watchdog, and frames; Python contract check on the run directory |
| Done when | Results and a short video are recorded, with machine and engine version |

## G3. The site

| | |
| --- | --- |
| Items | One HiRISE DTM selected with the owner; the [terrain pipeline](unreal-production-plan.md#terrain-data-pipeline); Landscape import; PCG rocks with a fixed seed; collision near wheels matching the rendered surface |
| Depends on | G2. **Owner:** approves the download and any tool such as GDAL |
| Acceptance | Known elevation differences match the source within its stated vertical accuracy; phase G's slope and step tests pass again on the site; `Dev` frame rate meets its target |
| Test | Import check script; phase G rerun as a new batch |
| Done when | The product ID, credit, and generated-detail label are in the game and in [assets-and-sources.md](assets-and-sources.md) |

## G4. The mission loop

| | |
| --- | --- |
| Items | One scenario file: three science targets, inspect and sample, orbiter data windows, battery, a compressed communication delay, one Mars-inspired fault; click-to-drive and short typed plans through the one `Action` path; a provisional HUD score |
| Depends on | G3 |
| Design decision first | Where typed plans run in a packaged game: in C++ from the [skill contract](decisions/0008-skills-are-data-not-code.md), or in Python over the bridge. Record it in an ADR before building |
| Acceptance | The mission takes 15–25 minutes for the developer; its logs score in Python; the HUD's provisional score equals the Python score on 5 runs, or each difference is explained |
| Test | 5 scripted runs and 2 manual runs, each scored from files |
| Done when | Results are recorded; the scenario file is committed, and is a practice scenario, never an evaluation one |

## G5. The look

| | |
| --- | --- |
| Items | Landscape material, three sky presets (clear, normal, dusty), Sun, exposure, dust plumes, tracks, haze, rover dust |
| Depends on | G3; runs in parallel with G4 |
| Acceptance | Three `Capture` frames, at noon, late afternoon, and sunset, judged beside credited rover images by named reviewers, with the [production plan's](unreal-production-plan.md#visual-direction) avoid-list clear; `Play` profile meets its frame-time target |
| Test | Fixed camera shots; frame time and memory per profile over 25 minutes |
| Done when | A graphics report is published, separate from the physics report, with who judged and what was reduced |

## G6. Play quality and stability

| | |
| --- | --- |
| Items | Tutorial for the first mission; complete HUD; help panel; pause; settings for resolution and quality; cause shown for a failed run |
| Depends on | G4, G5 |
| Acceptance | 10 consecutive full missions without a crash, hang, or explosion; every log scores; peak memory at or below 10 GB; `Play` frame-time target met over 25 minutes on the Air |
| Test | Scripted runs with a memory and frame-time recorder |
| Done when | Results are recorded, with the machine's thermal state noted |

## G7. Playable alpha

| | |
| --- | --- |
| Items | Packaged macOS build; credits; known-limits page; license; playtest with at least 5 people outside the project |
| Depends on | G6. **Owner:** license selection, EULA review, and the decision to distribute |
| Acceptance | The build runs on a second Mac; the fun targets in the [vision](product-quality-vision.md#fun) are met or their shortfall is published; no restricted asset in the build; the [security issues](security.md#unresolved) that affect a public build are fixed or stated |
| Test | Build content listing; playtest record with timings and answers |
| Done when | The owner decides to publish, or records why not |

## What the gates do not cover

Rover building in 3D, more sites, online competition, a real language model, held-out evaluation scenarios, and
terramechanics. Each needs its own plan and gates after G7.
