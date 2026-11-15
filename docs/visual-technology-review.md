# Visual technology review for the Mars site

**Status: research only, 2026-11-07.** Nothing here has been installed, imported, or measured. Facts come from the
cited pages and the GitHub or GitLab APIs on 2026-11-07. Quality and effort figures are judgments for planning, not
measurements. **This is not legal advice.** Licenses are summarized from their primary texts, which are linked, and
the owner reads them before any use.

The goal is set in [product-quality-vision.md](product-quality-vision.md), and the gates that use this page are
[G3 and G5](release-gates.md#g3-the-site). The look and data rules come from the
[production plan](unreal-production-plan.md).

## The constraints every choice must keep

| Constraint | Source | What it rules out |
| --- | --- | --- |
| Terrain shape comes from a public DTM, and detail below its resolution is labeled generated | [Production plan](unreal-production-plan.md#terrain-data-pipeline) | Any tool that reshapes landforms above the DTM's resolving scale |
| Collision near the wheels matches the rendered surface | [Production plan](unreal-production-plan.md#terrain-lod) | Render-only displacement large enough to change where a wheel touches |
| Real terrain shape does not validate soil, slip, or physics | [Production plan](unreal-production-plan.md#terrain-data-pipeline) | Calling the site "accurate" for driving |
| Every asset has a source and license; restricted assets stay out of Git | [assets-and-sources.md](assets-and-sources.md) | Fab or other restricted content in the public repository |
| Nothing that imitates NASA's rovers, branding, or imagery as the project's own | [README](../README.md#license), [model assumptions](model-assumptions.md) | A replica rover, or NASA logos |
| Dev and Capture profiles stay separate, and Capture is not lowered quietly | [Mac plan](mac-unreal-plan.md#quality-without-lowering-the-final-result) | Judging the look in the editor's daily profile |
| No paid service or large install without the owner | [CLAUDE.md](../CLAUDE.md#hard-limits) | Adopting any tool below without a decision |

## The candidates

"Mac" means the MacBook Air (Apple M5, 16 GB) unless stated. **No candidate was run on it.** Epic's
[macOS requirements](https://dev.epicgames.com/documentation/unreal-engine/macos-development-requirements-for-unreal-engine)
list Lumen with software ray tracing on Apple silicon M1 and later, Nanite and Virtual Shadow Maps as beta on M2 and
later, and hardware ray tracing and MegaLights as experimental on M2 and later. Whether 5.8 changed these rows was
not confirmed.

### Unreal Engine 5.8 features

| Feature | State, per sources | Mac | Use for the site | Effort |
| --- | --- | --- | --- | --- |
| **PCG** | Production-ready since 5.7; 5.8 adds hand edits on procedural output ([forum preview notes](https://forums.unrealengine.com/t/unreal-engine-5-8-preview/2721597)). A third-party guide says GPU overrides need DirectX 12 ([StraySpark](https://www.strayspark.studio/blog/ue-57-pcg-framework-production-ready-migration-guide)), which would leave the Mac on CPU. Unconfirmed by Epic | CPU path expected; GPU path unverified | **Adopt.** Rock scatter by size class from slope and orthoimage masks, with a fixed seed | 3–5 days |
| **Mesh Terrain** | Experimental; supports overhangs and tunnels beyond 2.5D heightfields ([80.lv](https://80.lv/articles/unreal-engine-5-8-is-out-today-with-big-optimization-improvements-and-mesh-terrain), [PC Gamer](https://pcgamer.com/software/unreal-engine-5-8-launches-with-improved-terrain-and-vegetation-tools-a-lumen-lite-option-for-faster-global-illumination-and-for-the-times-we-now-live-in-an-open-standard-plugin-for-llm-systems/)) | Unverified | **Do not adopt for the alpha.** A HiRISE DTM is 2.5D, so overhangs would be invented, not measured. Landscape stays the default, as ADR 0003 says | — |
| **Lumen Lite** | New medium-quality GI from irradiance fields with probe occlusion, about twice as fast as Lumen per coverage ([Tom Looman](https://tomlooman.com/unreal-engine-5-8-performance-highlights/), [Wccftech](https://wccftech.com/unreal-engine-5-8-lumen-lite-60-fps-switch-2/)) | Unverified; software Lumen is listed for M1+ | **Test first** for the `Play` profile. Mars light is dominated by diffuse sky in haze, which probe GI may suit | 1–2 days to measure |
| **Movie Render Graph** | Described as production-ready in 5.8 ([Digital Production](https://digitalproduction.com/2026/06/18/unreal-engine-5-8-tidies-up/)); path tracer or deferred chosen per render chain ([Epic](https://dev.epicgames.com/documentation/en-us/unreal-engine/transitioning-to-the-movie-render-graph-from-movie-render-queue-in-unreal-engine)) | Deferred expected to work. **The path tracer depends on hardware ray tracing, experimental on Mac**; unverified | **Adopt, deferred path** for the promotional video and Capture frames | 2–3 days |
| **Unreal MCP** | Official, experimental. Measured in this project on the M4 Mac for reads, and for edits only in a disposable project ([results](unreal-mcp.md#measured-results)) | Measured on M4 only | **Keep as an editor helper**: screenshots, test runs, actor checks. Never at runtime, never for look approval ([ADR 0005](decisions/0005-runtime-bridge.md)) | Already set up on M4 |

### Terrain and materials tools

| Tool | Repository, activity, license | Mac | Unreal | Use, and constraints | Effort |
| --- | --- | --- | --- | --- | --- |
| **LibreTerrain** | [gitlab.com/libreterrain/libreterrain](https://gitlab.com/libreterrain/libreterrain), site [libreterrain.org](https://libreterrain.org/). MIT or Apache-2.0; the name and logo belong to EllisonDigital. Releases v2026.1.0 and v2026.2.0 in late September 2026; the GitLab project was created on 2026-10-06 and has 2 stars | `macos-universal.zip` in the release | Exports 32-bit EXR heightfields, 16-bit masks, splat maps, and tiled output for World Partition, with an Unreal import helper ([site](https://libreterrain.org/)) | **Trial only, for masks and sub-DTM detail.** Very young; no record of use found. Its erosion must not reshape the measured macro shape | 2–4 days to trial |
| **Material Maker** | [RodZill4/material-maker](https://github.com/RodZill4/material-maker), MIT, v1.8 on 2026-10-25, about 6,200 stars | `.dmg` in each release | Exports PBR materials for Unreal ([site](https://www.materialmaker.org/)) | **Adopt** for original tileable regolith, gravel, and bedrock layers. Outputs are the project's own | 3–5 days for a material set |
| **Poly Haven** | [polyhaven.com/license](https://polyhaven.com/license): assets are CC0, may be redistributed, no attribution required. Site logos, renders, and text are excluded; scraping is not allowed | Not applicable | Textures and models import directly | **Adopt** for rock meshes, detail textures, and test HDRIs. Download by hand, not by scraping. Record each asset in the register | 1–2 days |
| **ArmorPaint** | [armory3d/armorpaint](https://github.com/armory3d/armorpaint), zlib license for source, pushed 2026-11-05. The prebuilt desktop app costs USD 19 ([download page](https://armorpaint.org/download)) | Apple silicon build listed | Exports texture sets | **Optional**, for painting the rover's dust and wear. The prebuilt app is a purchase, so the owner decides; building from source is free and untested here | 1–3 days |

### Asset generation and capture

| Tool | Repository, activity, license | Mac | Use, and constraints | Verdict |
| --- | --- | --- | --- | --- |
| **PYTHIA** | **Not found.** Neither a web search nor GitHub turned up a 3D tool by that name. A link or the paper's title is needed | — | — | Not assessed |
| **SAM 3D Objects** | [facebookresearch/sam-3d-objects](https://github.com/facebookresearch/sam-3d-objects), the custom **SAM License** of 2025-11-19, not an OSI license; pushed 2026-06-02. Reconstructs shape and texture of an object from one image ([model card](https://huggingface.co/facebook/sam-3d-objects/blob/refs%2Fpr%2F3/README.md)) | Not stated; GPU inference expected | A rock mesh from one photograph. Redistribution must carry the SAM License. Images of real Mars rocks are NASA's, so the result's provenance would need its own record | **Not for the alpha.** License, provenance, and an unverified Mac path |
| **TRELLIS, TRELLIS.2** | [microsoft/TRELLIS](https://github.com/microsoft/TRELLIS), [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), MIT, active in 2026 | Not stated; CUDA expected | Generated rock meshes | **Not for the alpha.** Poly Haven and procedural rocks cover the need with clearer provenance |
| **Hunyuan3D 2** | [Tencent-Hunyuan/Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2), Tencent community license that **does not apply in the EU, the UK, or South Korea** | Not stated | — | **Avoid** for a public project with players everywhere |
| **Modly** | [lightningpixel/modly](https://github.com/lightningpixel/modly), MIT, pushed 2026-11-01. A desktop app that runs image-to-3D models locally, listing Apple silicon macOS | Listed | A front end; each model it runs keeps its own license | Watch only |
| **Gaussian splatting in Unreal** | [XScene-UEPlugin](https://github.com/xverse-engine/XScene-UEPlugin), Apache-2.0, last push 2025-07; [unreal-splat](https://github.com/JI20/unreal-splat), MIT, UE 5.5, Windows binaries only; [YaGS](https://github.com/yandex/yags), Apache-2.0, UE 5.5–5.7, **archived** | No Unreal plugin with macOS or UE 5.8 support was found. [MetalSplatter](https://github.com/scier/MetalSplatter), MIT, renders splats on Apple platforms, but outside Unreal | Splats need many photographs of one scene. No such capture of a Mars site exists for this project, and splats do not give collision | **Do not adopt.** No data, no Mac path, no physics surface |

### Other tools found, 2025–2026

| Tool | Facts | Use |
| --- | --- | --- |
| **GDAL** | [OSGeo/gdal](https://github.com/OSGeo/gdal), MIT-style, pushed 2026-11-06 | **Required** for the DTM pipeline: crop, fill, resample, 16-bit export. Installing it needs the owner, as the [Mac plan](mac-unreal-plan.md#4-build-the-mars-environment) says |
| **Cesium for Unreal, with Cesium Mars** | [CesiumGS/cesium-unreal](https://github.com/CesiumGS/cesium-unreal), Apache-2.0; v2.31.0 on 2026-10-29 supports UE 5.6–5.8 on macOS. [Cesium Mars](https://cesium.com/blog/2025/09/03/lift-off-to-cesium-mars/) streams global Mars at about 200 m, Jezero at 20 m terrain, and Gale at 1 m terrain with 25 cm imagery, through a Cesium ion account | **Optional, for the far horizon only.** It needs an account and streaming, and its content terms for a distributed game were not checked, so the owner decides. The playable site stays a local HiRISE import |
| **Ames Stereo Pipeline** | [NeoGeographyToolkit/StereoPipeline](https://github.com/NeoGeographyToolkit/StereoPipeline), Apache-2.0, a NASA project; daily builds include `arm64-OSX` | **Not needed** while a released HiRISE DTM covers the site. Kept as an option for making a DTM from stereo pairs |
| **USGS ISIS** | [DOI-USGS/ISIS3](https://github.com/DOI-USGS/ISIS3), pushed 2026-10-26 | Not needed for released DTMs |

## The recommended pipeline for a 1 km site

**Measured shape, generated detail, original materials, CC0 assets, one engine.** Each step names what it may
and may not change.

```text
HiRISE DTM + orthoimage (USGS, CC0)          measured
   │ GDAL: crop 1 km, fill nodata, resample to 1009 × 1009 at ~1 m, 16-bit
   ▼
Heightfield + metadata (script and numbers in Git, raw data outside)
   │ optional: LibreTerrain or a script adds band-limited detail below ~2 m only,
   │           and masks (slope, roughness, rock density) from the DTM and orthoimage
   ▼
UE Landscape (collision from the same heightfield)     ── measured shape preserved
   │ PCG: rocks by power-law size class, fixed seed; large rocks have collision
   │ Materials: Material Maker layers + Poly Haven CC0 detail; macro color from the orthoimage, tinted
   │ Sky Atmosphere, Sun, height fog with the production plan's starting values; three dust presets
   ▼
Two outputs from one level
   ├─ Play: real time on the Air
   └─ Capture / promotional video: Movie Render Graph, deferred path
```

**The two outputs:**

| Setting | Play, on the Air | Capture and promotional video |
| --- | --- | --- |
| Goal | 30 FPS at the 95th percentile over 25 minutes, as in the [vision](product-quality-vision.md#performance-measured-on-the-development-macbook-air-apple-m5-16-gb) | The best image the machine completes, at any speed |
| Global illumination | Lumen Lite, if it measures well; else software Lumen at low settings | Software Lumen at high settings |
| Shadows | Shadow maps; Virtual Shadow Maps only if their beta measures well | Virtual Shadow Maps if they work; else high-resolution shadow maps |
| Geometry | Landscape LODs; rock LODs; Nanite only if its beta measures well | Nanite rocks if they work; denser small-rock PCG pass |
| Resolution | TSR at 50–67% of about 1440 × 900 | Full output resolution, temporal sample accumulation in Movie Render Graph |
| Dust and effects | Few Niagara particles, height fog | More particles, slower wind sheets, motion blur |
| Path tracer | No | **Not planned.** It depends on hardware ray tracing, experimental on the Mac. Revisit only with a measurement |

**What stays out:** Mesh Terrain, Gaussian splats, and generated 3D models in the alpha; Fab content in the public
repository; Cesium streaming in the playable area.

**Order of adoption,** each only after the owner approves its install or download:

1. GDAL and one HiRISE DTM, with the pipeline script and its import check.
2. Poly Haven assets and Material Maker layers, logged in the register.
3. PCG rock scatter, then Sky Atmosphere and dust presets.
4. Measure `Play` with Lumen Lite against software Lumen, and VSM and Nanite against their fallbacks, over 25 minutes.
5. Movie Render Graph for three Capture frames, for gate G5's review.
6. Only then, a timed trial of LibreTerrain for masks and sub-DTM detail, compared with a plain script.

## How this fits the scientific constraints

| Constraint | How the pipeline keeps it |
| --- | --- |
| Shape is measured | Only GDAL resampling touches the DTM's shape. Any added detail is band-limited below about 2 m, logged, and labeled generated |
| Collision matches render | Landscape collision uses the same heightfield. Render-only detail stays below a size to set at import and test in phase G's step test |
| No physics claim from terrain | The site's info panel says the shape is measured and the driving model is a game model |
| Asset provenance | Every Poly Haven asset, Material Maker graph, and generated mask is recorded in [assets-and-sources.md](assets-and-sources.md) |
| No NASA imitation | Rover and HUD are original. NASA and USGS data are credited as sources, never as endorsement |
| Mission Core unaffected | Nothing here changes the Python model, scoring, or any registered criterion |

## Open questions for the owner

- Approve installing GDAL, and downloading one HiRISE DTM, after choosing the site.
- Decide whether ArmorPaint's USD 19 app is worth buying, or whether to build it from source.
- Decide whether a Cesium ion account is acceptable for a horizon backdrop.
- Provide a link for "PYTHIA", if it is a specific project.
