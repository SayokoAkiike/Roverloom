# G2 greybox: first build, tests, and manual smoke test

**Status: a manual smoke test passed on 2026-11-07. G2 is not done.** Its acceptance in
[release-gates.md](../../release-gates.md#g2-greybox-playable) also needs 10 minutes of driving by a person, run logs that
pass `check_run_contract` and score in Python, and a recorded video. None of those has been attempted.

The drive model is P, the [WheelSpike wheel model](../unreal-wheel-model/README.md), used as a **provisional** model by the
owner's decision of 2026-11-07. Phase C stays failed. Nothing here tests or changes P's physics, and nothing here is
scored or ranked.

## What was built

| Part | Source |
| --- | --- |
| Six-wheel pawn on the WheelSpike rig, with visual wheels, mast, and panel that have no collision | `unreal/Source/Roverloom/Rover/RoverPawn.{h,cpp}` |
| One command path: keyboard to `Action`, a port of `command.py`'s router with its 2 s watchdog, then phase C's skid steering | `Rover/CommandRouter.{h,cpp}`, `Rover/RoverDrive.{h,cpp}` |
| Enhanced Input actions and keys built in C++, with no input asset | `RoverPawn.cpp` |
| Chase, mast (2.0 m, 45 degrees), front hazard, and free cameras, switched with C | `RoverPawn.cpp` |
| Canvas HUD that always shows the provisional-model label | `Rover/RoverHud.{h,cpp}` |
| Test ground from C++: 200 m flat ground, a 25 cm step, 10 and 15 degree slopes with plateaus, 24 rocks, sun, sky, fog | `Rover/RoverPlaygroundGameMode.{h,cpp}` |
| The site-to-Unreal part of `frames.py` | `Bridge/Frames.h` |

## Machine and versions

Mac mini, Apple M4, 16 GB, macOS 27.0.1, Xcode 27.2, Apple clang 21. UE 5.8.4 (CL 58902052) from the Launcher.
Code at `b0ad00a`. Driven from a MacBook Air over Tailscale screen sharing.

## Results

| Check | Result |
| --- | --- |
| Router, skid steering, and frames compiled natively against Python's outputs, on the Air | 2,000 router cases equal bit for bit, including the clamped flag; 96 wheel targets; 14 golden frame vectors |
| Game target build | Failed once: `ADirectionalLight::GetComponent` is editor-only. Fixed in `cd9aeab`, then succeeded |
| Editor target build, `RoverloomEditor Mac Development` | Succeeded, no warning from project sources |
| Automation `Roverloom.Rover`, `Roverloom.Bridge`, `Roverloom.Module`, with `-nullrhi` | 5 of 5 passed |
| Windowed standalone start, `/Engine/Maps/Entry?game=/Script/Roverloom.RoverPlaygroundGameMode -game` | Started on Metal. Log: 30 blocks, 24 of them rocks, 4 light actors, one rover; gravity -371 cm/s^2 |
| Rover at rest, 3 s after its rig was ready | Body center 0.700 m above ground, tilt 0.00 degrees, 6 of 6 wheels on the ground, no reset |
| Screenshots from the chase, mast, and hazard cameras, taken by the game | Rover, step, slopes, sky, shadows, and HUD label drawn |
| **Manual smoke test by the owner** | **WASD drove forward, stopped, and turned. C switched through all four cameras.** Both worked well, by the owner's report |

Logs and screenshots stay outside Git, under `unreal/Saved/G2Tests/` and `unreal/Saved/G2Play/` on the Mac mini.

## Known problems seen, and what followed

- **No colors, fixed in `65ccaab`.** Ground, rocks, and rover rendered white and gray, and the ground showed a black and
  white speckle. Cause, read through Unreal MCP: in UE 5.8.4 the engine's `Cube` uses `WorldGridMaterial`, and `Sphere`
  and `Cylinder` use `DefaultMaterial`. Neither has a color parameter, so the dynamic instances, made from each mesh's own
  material, ignored the colors, and the 200 m ground showed the world grid. Instances are now made from
  `BasicShapeMaterial`, whose parameters are `Color` and `Roughness`. In the chase camera's screenshot, distant ground
  went from RGB 172, 169, 164 to 200, 166, 130, and the luminance range of a 60-pixel patch from 56–192 to 164–169.
  Screenshots before and after, from the same three cameras, are kept outside Git.
- **Frame rate.** The first run's frame counter gave about 1.5 frames per second for two minutes, while the window was
  probably not in front; the cause is not confirmed. With the window in focus, at `ee5f546`, 1600 × 900, default
  scalability, rover at rest, six 10 s windows gave 60.0 fps, frame time mean 16.67 ms and 95th percentile 16.93–16.98 ms,
  game thread 2.5–3.7 ms, GPU 14.0–14.2 ms, focus 100%. The rate is held by the display's 60 Hz. This meets the
  provisional `Play` target of 30 fps at the 95th percentile on this scene, so no performance change was made. The GPU
  uses 14 of the 16.7 ms a 60 Hz frame allows, on a scene with almost nothing in it. Not measured: driving, 25 minutes,
  the Air, or a packaged build.
- Each screenshot from `-RoverShotDir` costs one long frame, up to 400 ms.
- `-game` with the editor binary logs 15 Python errors from the experimental EditorToolset plugin's start-up script. None
  comes from project code.

## Not shown by this test

Ten minutes of continuous driving, behavior on the slopes and the step, the turn rate reached, any physics property of
P, frame time under load, and run logs. The smoke test is a person's report of a few minutes of driving, not a measurement.
