# First 3D mission: reach the beacon

**Status: implementation candidate, not yet built or playtested with Unreal.** Python launcher tests use stand-in processes; they do not verify rendering, input, or the new target marker. The underlying keyboard mission was played on one Mac in [G4a](results/g4a-manual/README.md). A fresh-machine run of this launcher is still required before calling this a verified public demo.

## What you will run

A six-wheel rover on a small, generated 3D practice ground. Drive into the green target 8 m ahead within 120 seconds. The Python Mission Core judges arrival inside a 2 m radius and sends the verdict to the HUD. There are no faults, LLM calls, downloads of art assets, or competition scores. Physics is provisional and unvalidated.

This is the basic-shape training course, not the Gale crater scene shown at the top of the README. It uses assets supplied by your own Unreal installation; no project `.umap`, Poly Haven downloads, NASA terrain, or Git LFS art is needed. This is a source-build developer preview, not a packaged consumer game.

## Prerequisites (macOS)

- Apple Silicon Mac with Unreal Engine **5.8.4** already installed through Epic.
- The Xcode/toolchain required by that engine. See the project's recorded [Mac setup](macos-checklist.md) and [engine setup](decisions/0013-ue-5-8-4-on-macos-27.md).
- [uv](https://docs.astral.sh/uv/) and Git. uv manages Python 3.12 and installs the locked Python dependencies.
- A graphical desktop session. Close other Roverloom game windows; port 8100 must be available.

The launcher does not install Unreal, Xcode, or GPU drivers. Windows and Linux launches have not been implemented. A project open-source license is still pending; see the repository's licensing notice.

## Build and launch

Clone the repository, then run these commands **from the repository root**:

```shell
git clone https://github.com/SayokoAkiike/Roverloom.git
cd Roverloom
uv sync --locked --project python
uv run --project python python scripts/play_3d.py --ue-root "/Users/Shared/Epic Games/UE_5.8" --build --check
uv run --project python python scripts/play_3d.py --ue-root "/Users/Shared/Epic Games/UE_5.8" --build
```

Replace the engine directory if yours differs. `--check` only checks tools and port availability; it does not build, launch, or prove the engine version is correct. The second command builds `RoverloomEditor`, launches the game and connects the Python judge on **127.0.0.1:8100** on the same Mac. No SSH tunnel, night dispatcher, editor MCP, credentials, or paid service is used. Initial C++ compilation and shader preparation can take time.

After a successful build, omit `--build` for subsequent runs. Rebuild whenever C++ changes. Each launch creates a new directory under `runs/first-3d/` and prints its path.

## Play (about 30 seconds, up to 2 minutes)

1. Click inside the game window to give it keyboard focus.
2. Wait for the rig to start and the mission line to show `RUNNING`.
3. Hold **W** to drive forward toward the green wireframe sphere. **S** reverses, **A/D** turn and **C** changes the camera.
4. Release W when the HUD shows `SUCCESS`. The sphere is visual guidance only; Python decides the result.
5. The game closes after the result has remained on the HUD for roughly 8 seconds. A failed or disconnected run must not be recorded as a successful demo.

Press Ctrl+C in the terminal to cancel. The launcher stops only the processes it started. **R** resets the rover pose, not the mission clock; relaunch for a new attempt.

## Results and troubleshooting

Each run directory contains `unreal.log`, `link.log`, `events.jsonl`, `states.jsonl`, and (after a normal link exit) `final_state.json`. These are mission-link records, not ranked benchmark logs. Terminal exit code 0 requires a Python result of `success` with one target reached; a running or failed mission returns 1, launch errors return 2, cancellation returns 130.

- **Engine tool missing:** check `--ue-root`; it must contain `Engine/`. Check the engine version in Epic Launcher separately.
- **Build failed:** the error remains in the terminal. Check Xcode setup and engine version; do not bypass signing/security prompts.
- **Address already in use:** close the earlier Roverloom window or other listener. The launcher refuses to attach to an existing listener.
- **No movement:** click the window and check `Rig starting`, `Input`, and the watchdog on the HUD.
- **Waiting for Mission Core / no final result:** inspect `link.log` and `unreal.log`. Closing the window early, a crashed engine, or a broken connection is not completion.
- **Long first launch:** inspect the logs for shader preparation. The supervisor stops after seven minutes; preserve the logs instead of treating a timeout as success.

## Fresh-machine acceptance (pending)

On a separate Mac or a clean checkout without generated `Content/`, record the commit, macOS, hardware, Xcode and engine versions, exact command, build result, visible target, keyboard movement, Python `SUCCESS` on the HUD, final JSON, and a screenshot/video. Also check timeout, early window close, and Ctrl+C cleanup. Do not publish a “works from a clean clone” claim until these checks are recorded. No such run is claimed by this document.
