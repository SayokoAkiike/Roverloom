# Development environment

**This page describes the Windows laptop used until 2026-11-02.** Unreal work moves to an Apple M4 Mac, surveyed in
[the checklist](macos-checklist.md#results-on-this-mac) and [ADR 0012](decisions/0012-m4-mac-for-unreal.md).

Surveyed 2026-11-02 on the primary development machine. Graphics recommendations
below are starting points from Epic's published requirements. **They have not been
measured**, because Unreal Engine is not installed yet.

## Machine versus Epic's UE 5.8 recommendation

| Item | This machine | Epic recommended | Assessment |
| --- | --- | --- | --- |
| Model | HP OmniBook 7 Aero 13 | n/a | Thin laptop; expect thermal limits |
| OS | Windows 11 Home 10.0.26200 | Windows 11 | OK |
| CPU | Ryzen AI 5 340, 6C/12T | Quad-core, 2.5 GHz+ | OK; C++ builds will be slow |
| GPU | Radeon 840M (integrated) | DirectX 12 card | Far below high-fidelity needs |
| VRAM | 2 GB reported, shared with system | 8 GB or more | Below recommendation |
| RAM | 13.8 GB usable | 32 GB | Below recommendation |
| Disk | 120.5 GB free on C: (476 GB NVMe) | Not specified | Tight with engine and VS |

## Verdict

This machine can be used for C++, Blueprint logic, physics, tooling, and small test
levels at reduced settings. It is **not suitable for developing or judging high
visual quality**. High-quality terrain authoring needs a machine with a discrete GPU
with at least 8 GB VRAM and ideally 32 GB RAM. Options are a desktop PC or an
eGPU if the laptop's ports support one, which has not been checked.

## Tool status

| Tool | Status |
| --- | --- |
| Git / Git LFS | 2.55.0 / 3.7.1 installed |
| GitHub CLI | 2.103.3 installed for this setup |
| Python / uv | 3.13.14 / 0.12.17 installed |
| Claude Code | 2.1.316 installed |
| Node.js | 24.19.0 installed |
| Unreal Engine, Epic Launcher | Not found |
| Visual Studio, Rider | Not found |

## Required installation (manual, not yet done)

1. **Epic Games Launcher and UE 5.8**, to run the engine and Unreal MCP. Install
   only Windows target and skip optional platforms and debug symbols to save space.
2. **Visual Studio 2026 Community**, Epic's listed compiler for general UE 5.8
   development. Use the "Game development with C++" workload with the Unreal Engine
   options and the Windows SDK. Check Epic's Visual Studio setup page at install
   time, and confirm that Community license terms fit your situation.
3. **Disk space.** Check the Launcher's and Visual Studio installer's reported sizes
   before starting. Together with shaders and caches, they may consume most of the
   free 120 GB, so consider freeing space or using a fast external SSD first.

## Starting graphics settings for this machine

Measure with `stat unit` and `stat gpu` and adjust.

| Setting | Editor start value | Reason |
| --- | --- | --- |
| Engine Scalability | Low, Medium if stable | Limited GPU and shared memory |
| Screen percentage | 50–67% with TSR | Cost scales with pixels |
| Global illumination | Lumen Lite, or off in test levels | Epic targets it at lower-end PCs; test on this GPU |
| Hardware ray tracing | Off | Not realistic on this GPU |
| Shadows | Regular or low-quality | Virtual Shadow Maps are costly here |
| Nanite | Test on terrain spike | Verify driver support and cost |
| Texture streaming pool | 1 GB or less | Memory is shared |
| Compile jobs | Limit to about 4 | Avoid running out of memory |

Keep the project outside OneDrive and other synced folders. Plug in AC
power when measuring. Do not enable high-quality presets as defaults in
`unreal/Config` based on this machine; keep separate scalability profiles once a
capable machine is available.

## Sources

- [Epic: UE 5.8 hardware and software specifications](https://dev.epicgames.com/documentation/unreal-engine/hardware-and-software-specifications-for-unreal-engine?lang=en-US)
- [Epic: Unreal Engine 5.8 released](https://forums.unrealengine.com/t/unreal-engine-5-8-released/2729274)
