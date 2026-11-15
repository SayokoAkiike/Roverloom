# Visual roadmap for the Unreal client

**Status: a plan, written on 2026-11-15.** Nothing here has been built, downloaded, or measured. It extends
[visual-technology-review.md](visual-technology-review.md) and [site-and-look-references.md](site-and-look-references.md),
and follows the gates in [release-gates.md](release-gates.md). **This is not legal advice.** License notes summarize
public pages, and some primary pages could not be read from the planning environment; read each primary text
before any download.

## What the screen shows today

All Unreal screenshots in Git are 800 × 450 PNGs of about 300 KB each, under `docs/results/`, taken on a Mac mini
with UE 5.8.4. The rover is built from engine basic shapes on flat test ground, and the HUD text is about 8 px high
at that size. The captures were made at 1600 × 900, but those originals are not in Git. No video exists.

| Image | Shows | Use |
| --- | --- | --- |
| [g4a-manual/human-mission-success.png](results/g4a-manual/human-mission-success.png) | A person drove to the target; the Mission Core judged SUCCESS | README, as the current state |
| [g3-mission-link/hud-success.png](results/g3-mission-link/hud-success.png) | Scripted drive, SUCCESS from the Mission Core | Supporting |
| [v1b-terrain/after.png](results/v1b-terrain/after.png) | Mars palette, sky, and haze | Before-and-after comparisons |
| [game-readiness/](results/game-readiness/README.md) shots | Step and ramp tests | Technical records |

## Rules for every visual step

- Visual meshes are children of the existing physics components, with collision disabled. Wheel radius, track,
  mass, contact, and test lanes do not change. Drive model P stays provisional.
- Python's `MODEL_VERSION` and `SCORING_VERSION`, the bridge, and `schemas/` do not change for visual work.
- Each step records before-and-after images taken under the same conditions, and GPU time, as V1 and V1b did. GPU
  time may grow by at most 0.5 ms per step unless the owner accepts more.
- Look is judged only in the `Capture` profile. See the [Mac plan](mac-unreal-plan.md#quality-without-lowering-the-final-result).
- The rover is an original design, never a replica of a NASA rover, and shows no agency insignia.
- Every asset is entered in [assets-and-sources.md](assets-and-sources.md). Restricted content stays out of Git.
- Large source files, raw terrain data, and video stay outside Git unless the owner decides otherwise.

## Asset and tool candidates

**Asset** means it may enter the game. **Reference** means it is only compared by eye.

| Candidate | Kind | Terms, as found | Unreal | Recommendation |
| --- | --- | --- | --- | --- |
| [Poly Haven](https://polyhaven.com/license) | Asset: rocks, textures, HDRIs | CC0; download by hand, no scraping | Direct import | Adopt |
| [ambientCG](https://ambientcg.com/) | Asset: PBR materials | CC0, as summarized by third parties | Direct import | Adopt, alongside Poly Haven |
| [Material Maker](https://github.com/RodZill4/material-maker) | Tool: procedural materials | MIT; macOS build | PBR export | Adopt for regolith and bedrock layers |
| Megascans on [Fab](https://www.fab.com/) | Asset: scanned rocks and surfaces | Reported free on Fab from November 2026 under the Fab Standard License; Epic's announcement was not read here. Redistribution in a repository is not assumed | Best fit | Only in `Content/Licensed/`, outside Git, with a CC0 substitute for clones |
| [HiRISE DTMs](https://registry.opendata.aws/nasa-usgs-mars-hirise-dtms/) | Asset: measured terrain | CC0 per the registry | Landscape import through GDAL | Adopt, as already planned for G3 |
| [NASA 3D Resources](https://science.nasa.gov/3d-resources/) | Reference: rover models | Free to download; NASA insignia are protected. Page not read here | GLB import | Proportions and mechanisms only, never imported into the game |
| [Blender](https://www.blender.org/) with [blender-mcp](https://github.com/ahujasid/blender-mcp) | Tool: modelling, agent-driven | Blender is GPL, and its output belongs to the author; blender-mcp is listed as MIT, and forks differ | FBX or glTF export | Adopt for the original rover model. Install needs the owner |
| [vork](https://github.com/voyager-so/vork) | Tool: headless 3D and VFX engine for agents | Custom preview license: free, commercial use allowed, modified copies may not be redistributed, later versions may be paid | No Unreal integration; reads glTF, writes PNG and MP4 | Not adopted. Possibly promotional stills later |
| [Gaea](https://quadspinner.com/) | Tool: terrain generation | Free edition is non-commercial, with 1K export | Heightfield export | Not adopted. A paid edition needs the owner |
| [LibreTerrain](https://libreterrain.org/) | Tool: terrain masks and detail | MIT or Apache-2.0; very young | EXR and tiles | Trial only |
| [RoveSoSimulator](https://missourimrdt.github.io/RoveSoSimulator) | Reference: a UE5 rover simulator | Listed as MIT | UE5 | Structure reference only |
| Mars First Logistics, NASA Eyes | Reference: games and visualizers | — | — | Readable failure, data sources on screen. See [product-quality-vision.md](product-quality-vision.md) |

## Steps, in priority order

| Step | Work | Passes when | Rough size |
| --- | --- | --- | --- |
| V2. Rover model | An original six-wheel rocker-bogie in Blender, sized from `rovers/designs/pathfinder_6w`: wheels with grousers, rockers and bogies, mast and camera head, solar panel, dust and wear. Materials from CC0 sources and Material Maker | Collision unchanged; automation tests pass; GPU within limit; same-condition images recorded | 1–2 weeks |
| V3. Terrain | Keep the test ground. Add a HiRISE DTM horizon chosen by the owner, PCG rocks with a fixed seed, CC0 regolith layers, dunes and a crater rim | Test lanes unchanged; terrain source shown on screen | 2–3 weeks |
| V4. Light and cameras | Noon, late afternoon, and sunset with three dust presets; chase camera damping; a mast camera framed like a rover photograph | `Dev` and `Capture` separate; compared with credited references | 1 week |
| V5. HUD and agent view | Readable HUD at 1080p; planned path, targets, hazards, the command queue under delay, fault state, and the reason from `decision` records | Needs bridge v1 in C++ so that a Python agent drives Unreal. Before that, show Python logs in a kinematic replay, labeled where the terrain differs | 2–3 weeks |
| V6. Screenshots and video | Three fixed shots at 1600 × 900 or larger, PNG or WebP under 500 KB each, with the HUD readable; a short video of keyboard and agent driving, stored outside Git | Movie Render Queue or Graph checked on the Mac first; each image records engine, machine, profile, and commit | 1 week |

The existing `-RoverBench` runs already save a 1600 × 900 screenshot. Committing those originals instead of 800 × 450
copies is the quickest way to make the HUD readable in the README.
