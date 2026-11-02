# Mac Unreal plan

**Goal:** an Unreal Engine 3D demo in which a six-wheeled rover drives across realistic Martian terrain, operated by a person and by a Python agent.

**Plan. Steps 1 to 3 are measured; the rest has not been built.** See [the results](macos-checklist.md#unreal-results-on-this-mac). Design detail is in [unreal-production-plan.md](unreal-production-plan.md), the contract in
[unreal-contract.md](unreal-contract.md), and compatibility in [macos-checklist.md](macos-checklist.md). This page sets order and gates. If it conflicts with
[vertical-slice-plan.md](vertical-slice-plan.md), this page and the contract win. That plan's machine column predates the Mac.

Finish each step's gate, and record its numbers, before the next. Stop and ask the owner at every line marked **Owner**.

## Quality without lowering the final result

Editor speed and final image quality are separate settings, and should stay separate.

| Profile | Used for | Rule |
| --- | --- | --- |
| `Dev` | Daily editing, on the measured Mac | May use lower scalability, screen percentage, and Lumen settings. Never committed as the project default for captures |
| `Capture` | Screenshots, video, look decisions | Highest settings the machine completes reliably. Can run far below real time |

- Lower `Dev` first. Do not reduce source assets, terrain resolution, material layers, or `Capture` to make the editor faster.
- Judge the look only in `Capture`. Report anything reduced from intent, with the reason, and the measurement.
- Start with software Lumen, which Epic lists as supported on M1+. Nanite and Virtual Shadow Maps are beta on Mac, and hardware ray tracing and MegaLights are experimental. Test each in a spike, and keep a tested fallback.
- With 16 GB, which is Epic's minimum, expect smaller levels open at once, lower streaming pools in `Dev`, and fewer parallel compile jobs. Measure rather than assume. 32 GB is Epic's recommendation.
- The [earlier target](graphics-strategy.md) of 1440p and 60 FPS was for a discrete GPU PC. Measure on M4, and report it. Do not claim it unmeasured.
- **Owner:** if `Capture` cannot reach the intended look, propose a separate machine rather than quietly lowering the target.

## Steps

### 1. Check the Mac

Run [the checklist](macos-checklist.md) sections 1 to 5, then record results there.
**Gate:** specs and free disk reported. Python checks pass, or failures are reported.

### 2. Install tools and Unreal Engine

**Owner:** approve the install, after seeing macOS version, chosen Xcode version, and reported sizes.

1. Xcode, then the Epic Games Launcher, then the newest 5.8 hotfix. Skip optional platforms.
2. Measure an empty project with `stat unit` and `stat gpu`, and record memory.
3. Create a C++ project in `unreal/`, build it, and confirm that a clean clone opens. Run a small Mac packaging test early, because of the reports in the checklist.

Add `Roverloom.uproject`, `Config/`, and `Source/`. Do not commit anything ignored by `.gitignore`.
**Gate:** the editor opens, and C++ compiles. Times, memory, and versions are recorded in [development-environment.md](development-environment.md). Update [ADR 0003](decisions/0003-unreal-engine-5-8.md) in a new record if needed.

### 3. Connect Unreal MCP, read-only

**macOS status is unknown.** Epic's [MCP page](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?lang=en-US) neither lists nor excludes macOS. Its only platform note is a Unix shell setting for the Terminal plugin. Follow [unreal-mcp.md](unreal-mcp.md):

1. Check that the plugin appears on Mac. Look in Edit > Plugins, and check `ModelContextProtocol.uplugin` for platform lists.
2. Enable it, generate `.mcp.json` from the console, and start Claude Code from `unreal/` with the editor running.
3. Run the verification plan on a disposable map. Compare a read-only actor listing with the Outliner, and confirm that `git status` is clean.

Keep the server on loopback. **Gate:** record engine version and exact calls, or record the failure. MCP is not needed for the demo: if it fails, continue with Editor Python and C++, and say so.

### 4. Build the Mars environment

Follow the production plan for look, data, and honesty rules.

1. Terrain: select a HiRISE DTM with the owner, and run the pipeline. **Owner:** approve the download and any tool install, such as GDAL. Raw data stays outside Git, and the script and metadata go in Git. Label generated detail.
2. Decide in a spike whether Landscape with Nanite works on the Mac. Landscape remains the default.
3. Materials, then lighting and sky presets (clear, normal, dusty), then PCG rocks, then dust. Use original or CC0 assets for anything required. Fab content goes only in `Content/Licensed/`, and is not committed.
4. Update [assets-and-sources.md](assets-and-sources.md) with every asset.

**Gate:** `Capture` shots at noon, late afternoon, and sunset beside credited rover references, and the numbers for each profile. Photorealism is a judgment, so state who judged it.

### 5. Place and drive the six-wheeled rover

Build from `rovers/designs/pathfinder_6w` parameters and geometry. It is an original design, not a NASA replica.

Run the physics spike, timeboxed, from the [vertical slice plan](vertical-slice-plan.md), and record the choice in an ADR. Then automate the plausibility tests in that plan: free fall at 3.71 m/s², static load, step response, yaw sign, slope, obstacle, time step, stability.
**Gate:** tests recorded. Results are described as plausible for game use, never validated.

### 6. Manual control and cameras

Enhanced Input maps to `Action`, which is the one input path. Add chase, mast, wheel close-up, and free cameras, plus the source toggle and watchdog. Switching cameras never changes physics.
**Gate:** a real person has driven it. The watchdog stops the rover.

### 7. Connect Python

Port `frames.py` to one C++ boundary file, and test it with [frame_vectors.json](../schemas/conformance/frame_vectors.json). Implement bridge protocol v1 off the game thread, following `RealtimeCommandLink`. Unreal listens, and an unmodified Python agent connects over loopback.
**Gate:** a Python agent drives the same rover. Yaw and Y signs are verified. Killing the client stops the rover without a crash.

### 8. Integrate faults, telemetry, and replay in 3D

- Unreal reads scenario files, and applies faults through the same names. Effects stay visual unless a scenario defines otherwise.
- Write run logs in the shared formats, with a distinct `backend` and `model_version`. Pass `check_run_contract`, and score with `roverloom score`.
- Replay Unreal logs kinematically. To replay Python logs, first solve the shared heightmap issue in [the handoff](HANDOFF.md#known-problems-and-technical-debt). The simple choice is a label saying that the terrain differs.
- Extra wheel fields are optional additions to telemetry, tested on both sides. Keep Python model and scoring versions unchanged, so that existing pins hold.

**Gate:** one mission runs with a fault, is scored from files, and replays. Real-time logs are labeled as not for ranking.

### 9. Screenshots, video, performance

Fixed shots, plus a short video of manual and Python driving. Record frame time, memory, resolution, profile, machine, and engine version. Publish the graphics report and the physics report separately, with their limits.
Offline capture tools on Mac, such as Movie Render Queue, have not been checked. Check them before relying on them.

### 10. Save to GitHub

- Save at the end of every step, not only here. Feature branches are fine. Stage by name, and review the diff.
- Lock `.uasset` and `.umap` files. **Check Git LFS usage regularly** with GitHub's billing page, since Unreal assets can pass the free quota quickly. **Owner:** approve any data pack, or decide what stays outside Git. Large video and raw data stay outside Git.
- Update README, roadmap, [project-status.md](project-status.md), and this handoff. CI has no Unreal, so record Unreal test results with engine version and machine.
- Confirm that the repository stays private.

## Completion criteria

- A fresh clone opens, with substitutes for restricted assets.
- A person and a Python agent drive the same rover through one input path, and the watchdog stops it.
- A run's logs pass the contract check, score in Python, and replay in Unreal.
- Graphics and physics reports exist, with the numbers and limits. Asset sources are complete.
