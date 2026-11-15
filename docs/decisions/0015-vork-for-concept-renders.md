# 0015: vork for concept renders, kept apart from game screenshots

Status: Accepted by the owner (2026-11-15). No image has been rendered yet.

## Context

The README's only Unreal image is an 800 × 450 greybox frame. The V2 rover model exists as meshes, but it is not yet
in Unreal, and this cloud session cannot upload Git LFS images. The [visual roadmap](../visual-roadmap.md) had listed
[vork](https://github.com/voyager-so/vork) as "not adopted": it has no Unreal integration, and its license is a
preview license. The owner chose to use it for promotional images of the V2 rover.

Facts checked on 2026-11-15, at vork commit `5de38c2` and release 0.5.1. This is not legal advice; read the
[license](https://github.com/voyager-so/vork/blob/main/LICENSE):

- The license is the "vork Preview License". vork is source-available, "not open source", and "free to use during
  the research preview, including for commercial work". Modified copies may not be distributed. Later versions may
  have other terms, including paid ones.
- "We claim no rights in the scenes, code or media you create with vork."
- Rendering needs Apple silicon with Metal, macOS 26 for the bundled toolchain, or an NVIDIA GPU with Vulkan ray
  queries. `vork check` validates a scene without a GPU.

## Decision

Use vork as a local tool on the Mac for **concept renders** of the rover. It is not a dependency.

- `scripts/vork/rover_concept.py` writes the scenes from the V2 glTF. Every other element is made from vork's own
  shapes and programs: ground, rocks, mesas, sky, and dust. No third-party assets.
- vork itself is never committed or vendored.
- Every concept image is labeled **"Concept render (vork), not a game screenshot"** wherever it appears. It is never
  placed where a reader would take it for the running game. The README's game section keeps real Unreal frames only.
- Images are committed from the Mac, through Git LFS, with the vork version, profile, and commit recorded.

## Consequences

- The README can show the rover's look before the Unreal import (V2 on the Mac) is done.
- Concept renders show a model and an invented scene. They say nothing about physics, terrain data, or game performance.
- If vork's terms change, or it stops being free, the renders already made stay ours. The scene generator stops being
  usable, and Blender's Cycles path (`scripts/blender/build_rover.py --render`) remains as a fallback.
