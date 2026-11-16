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
| [vork](https://github.com/voyager-so/vork) | Tool: headless 3D and VFX engine for agents | Custom preview license: free, commercial use allowed, modified copies may not be redistributed, later versions may be paid | No Unreal integration; reads glTF, writes PNG and MP4 | Adopted for concept renders only, by the owner on 2026-11-15. See [ADR 0015](decisions/0015-vork-for-concept-renders.md) and the [guide](vork-concept-renders.md) |
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

**V2 progress, 2026-11-15:** the mesh generator and its checks are done; see [V2 results](results/v2-rover-model/README.md).
The pawn change is merged but has never been compiled. Import into Unreal and same-condition screenshots wait for
Unreal Engine, which is not installed on the Mac mini as of 2026-11-15. Concept renders with vork exist; see
[results](results/concept-renders/README.md). They are not game screenshots.

**V3 progress, 2026-11-16:** the owner chose Gale. A 1 km heightfield from HiRISE DTM
`DTEEC_063319_1745_052242_1745_A01` is made and checked against its source; see [terrain results](results/terrain-gale/README.md).
Import, regolith materials, and rocks wait for Unreal Engine.

The existing `-RoverBench` runs already save a 1600 × 900 screenshot. Committing those originals instead of 800 × 450
copies is the quickest way to make the HUD readable in the README.

## Next work, 2026-11-16

Ordered by what can start now. Nothing below is done unless marked.

| # | Work | Needs | State |
| --- | --- | --- | --- |
| 1 | Mission Control restyle, same behavior | Nothing | Done, PR #12 |
| 2 | Concept render of the V2 rover on the Gale heightfield | vork, the [terrain results](results/terrain-gale/README.md) | Done; see [concept results](results/concept-renders/README.md#gale-site) |
| 3 | Build the merged V2 pawn (PR #9) and import the rover meshes; same-camera screenshots | UE 5.8.4 on the Mac mini | **Done 2026-11-16:** compiled, imported, shown in the game; same-camera shots and drive comparison in [the V2 results](results/v2-rover-model/README.md#first-unreal-run-2026-11-16). GPU time not measured |
| 4 | Rover materials | UE | **Done 2026-11-16:** PBR materials with dust that settles by surface direction and height; procedural, no third-party asset ([results](results/rover-pbr/README.md)). The V2 mesh itself is simple |
| 5 | Gale Landscape from `gale_site.r16`, Z scale 17.562%, checked against `site.json`; CC0 regolith in two scales; rocks with a fixed seed, off the test lanes, no collision | UE; CC0 textures from ambientCG or Poly Haven | **Done 2026-11-16, except a check of more points against the DTM:** [Gale results](results/gale-landscape/README.md). Four layers at two scales, 691 rocks, a 5.6 km horizon; the rover starts on a calm patch 38 m from the center |
| 6 | Lighting presets from the command line, fixed exposure, `Dev` and `Capture` apart; chase-camera damping | UE | **Done 2026-11-16 except chase-camera damping:** `-RoverLight` noon, afternoon, sunset; `-RoverProfile` dev (software Lumen, 34 fps with rocks) and capture (11 to 16 fps, stills only). Values by eye |
| 7 | HUD readable at 1080p with the PROVISIONAL label | UE | **Done 2026-11-16:** the HUD scales with the viewport height; the label is unchanged ([results](results/rover-pbr/README.md#hud-at-1080p)) |
| 8 | Three fixed shots, Movie Render Queue checked on the Mac, a 30 s video outside Git; README top image from the game | Steps 3–7 | **Mostly done 2026-11-16:** Movie Render Queue works on the Mac (three 1920 x 1080 stills, a 30 s video kept outside Git), in [the effects results](results/gale-effects/README.md). The video's camera does not follow the rover. A README image is proposed there, not applied |
| 9 | G2 acceptance: a 10-minute drive and scored run logs from Unreal | UE | Waiting |
| 10 | Bridge v1 in C++, so that a Python agent drives the Unreal rover | UE; the owner gave the go-ahead 2026-11-16 | **Compiled and run once, 2026-11-16:** one `unreal_link --agent reactive` run reached the G3 target ([results](results/unreal-link-g3/README.md)). One run, not a verified path |
| 11 | The Gale site as a terrain in the lightweight backend, so both backends share a `terrain_id` | Owner decided 2026-11-16; [ADR 0016](decisions/0016-gale-terrain-in-lightweight-backend.md) | Schema and loader done, with synthetic-data tests. The terrain document and a scenario need `gale_site.r16` from the Mac mini |

