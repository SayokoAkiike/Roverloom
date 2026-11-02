# Unreal Engine 5.8 production plan

**Plan only.** `unreal/` is only a skeleton, so nothing here has been built or measured, including
all budgets. Reviewed 2026-11-02. See also [vertical slice plan](vertical-slice-plan.md),
[graphics strategy](graphics-strategy.md), and [integration](unreal-integration.md).

The lightweight preview in `python/` is a separate tool. It is never a substitute for this renderer,
and it shares contracts, not visuals.

## Visual direction

**Goal:** A viewer's first impression is of a robot's photograph from Mars, not a game's red desert.

Principles:

1. **Restraint.** Mars is low-contrast, butterscotch, and dusty, not saturated orange.
2. **Scale from detail.** Rock size distribution and fine surface texture make distances believable.
3. **Light tells the time.** Diffuse sky light dominates in haze, with long shadows and a blue glow
   around the Sun near sunset, caused by dust scattering.
4. **Robot's-eye framing.** Mast and hazard camera views at human-like height, with a realistic lens.
5. **Dust links it all.** A thin film on the rover, wheel plumes, and distance haze.

Reference board: credited rover images, stored outside Git unless terms are confirmed. Each look
milestone is compared against the same reference frames at noon, late afternoon, and sunset.

Avoid: oversaturated red, strong bloom, Earth-like blue day sky, clouds as a main feature, uniform
rock scatter, tiling visible from the rover's mast.

## Terrain data pipeline

Nothing has been downloaded. Tools such as GDAL are not installed, and these commands have not been run.

| Step | Action | Output |
| --- | --- | --- |
| 1 | Search the [USGS STAC collection](https://stac.astrogeology.usgs.gov/api/collections/mro_hirise_controlled_socet_dtms) for tiles with varied slopes and few artifacts | Candidate list |
| 2 | Inspect the figure of merit image and orthoimage. Reject artifacts crossing the site | Selected product ID |
| 3 | Download from `s3://astrogeo-ard/mars/mro/hirise/controlled/dtm` (no sign-in) | Local files, outside Git |
| 4 | Crop about 1 km around the site, in the product's metric coordinates | Cropped DTM |
| 5 | Fill nodata explicitly, and record the filled area | Clean DTM, QA notes |
| 6 | Resample to a valid Landscape size such as 1009 × 1009 at about 1 m | Heightfield |
| 7 | Scale to unsigned 16 bits. Record minimum, maximum, and vertical scale | `.r16` and metadata |
| 8 | Import. Check known elevation differences against the source | Landscape |
| 9 | Commit the script and metadata, not raw data, and update [the register](assets-and-sources.md) | Reproducible record |

**Source facts** from [USGS](https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms/): CC0-1.0;
Cloud Optimized GeoTIFF; post spacing 1–2 m; orthoimage about 0.25 m at full resolution; heights
relative to the aeroid; equirectangular or polar projection; horizontal accuracy about ±100 m and
vertical about ±1.3 m relative to MOLA. USGS warns that true resolving power can be coarser than the
spacing, and lists artifacts including seams and jitter.

**Example vertical scale:** Epic's convention to verify at import is that 100% Z scale spans about 512 m,
so scale percent = elevation range in m ÷ 512 × 100.

**Honesty rules:**

- Label detail smaller than the DTM's resolution as generated, not measured.
- Display "site derived from HiRISE data, with generated detail", with the product ID and credit.
- Real terrain shape **does not validate** soil behavior, slip, or physics.
- Site-frame coordinates are local. No real-world navigation accuracy is implied.
- Keep the `terrain_id` mapping in one file. Lightweight terrain and Unreal terrain with the same ID
  would need a shared heightmap before their results can be compared at all.

## Terrain, rocks, materials, lighting, and dust

### Terrain LOD

| Range | Representation |
| --- | --- |
| Under 20 m | Fine displacement or Nanite detail, small rocks, pebbles, tracks |
| 20–200 m | Landscape with macro normal, mid rocks |
| 200 m to edge | Landscape LOD, large rocks |
| Beyond site | Low-resolution mesh or skyline from wider coarse data, in haze |

Start with Landscape. Test Mesh Terrain only if overhangs prove worthwhile, because it is reported as
experimental. Physics collision uses a simplified surface that must match the rendered one near wheels.

### Rock placement

- PCG with size classes following a power-law style distribution: few large, many small.
- Density and size driven by masks from slope and orthoimage, plus clusters near ejecta-like areas.
- Fixed seed in the level, committed with parameters. Larger rocks have collision; pebbles do not.
- Agents see only what sensors return. Export rock positions as ground truth for evaluation.
- Sources: original or CC0 only for anything required. Fab goes in `Content/Licensed/` for private look
  tests only.

### Materials

- Master landscape material with slope, height, and macro color layers.
- Macro color from the orthoimage tinted by reference. The red-band image alone has no true color.
- Detail: dust, gravel, bedrock, fine sand, using distance-based tiling breakup.
- Roughness high overall. Runtime virtual texture for wheel tracks.
- Rover: dust mask by height and orientation, increasing over time.

### Lighting and atmosphere

| Element | Starting value, to tune against references |
| --- | --- |
| Sun | About 590 W/m² at mean distance, apparent size about two-thirds of that from Earth |
| Sky Atmosphere | About 3390 km planet radius, about 11 km scale height, weak molecular scattering |
| Dust | Strong Mie-like scattering, forward peak, blue absorption so that it reddens daytime sky |
| Exposure | Fixed, per-preset exposure, as a camera would; avoid strong auto exposure |
| Global illumination | Lumen or Lumen Lite by profile. Sky light matches the atmosphere |

Three presets are required: clear, normal, and dusty. Dust optical depth is a parameter logged per run.

### Dust effects

- Niagara plumes per wheel, from speed and slip, low cost and drifting with wind.
- Height fog for distance haze. Slow ground-level sheets at low density.
- Effects are visual only unless a scenario defines sensor impact, which is a separate decision.

## Standard rover

Original design. All values are starting points to confirm with physics tests.

| Item | Design |
| --- | --- |
| Size | About 3.0 m long, 2.7 m wide, 2.2 m to mast top |
| Mass | 1000 kg; gravity 3.71 m/s² |
| Wheels | Six at 0.5 m diameter, 0.4 m width, grousers; independent drive |
| Steering | Skid steering first, matching the `Action` model. Corner steering later |
| Suspension | Rocker-bogie: rockers joined by a differencing mechanism across the body; bogie carries middle and rear wheels. Passive, with no springs in the first version |
| Ground clearance | About 0.5 m. Design step about one wheel diameter |

Coordinate origin at center of the body on ground plane, X forward, Z up, in rover frame. Unreal
conversion is applied only at the bridge boundary.

### Sensors

| Sensor | Mount | Use |
| --- | --- | --- |
| Mast navigation camera | Mast, about 2.0 m high, pan and tilt later | First-person view; recorded images later |
| Front and rear hazard cameras | Body, low, wide lens | Near-ground view |
| Range sensor | Front body, about 1.0 m high, bearings per rover file | Maps to `range_scan` |
| Wheel odometry | All wheels | `estimated_speed_mps` |
| Pose estimate | Body; truth plus configured noise at first | `estimated_pose` |

Camera images are not part of `Observation` today. Adding them needs a design for size and rate.

## C++ and Blueprint responsibilities

| C++ | Blueprint |
| --- | --- |
| Rover physics, wheel contact, power | Rover visual assembly |
| Action input path, router, watchdog | Enhanced Input mapping to commands |
| Bridge, messages, coordinate conversion | HUD and camera UI |
| Telemetry, manifest, replay core | Camera rigs and transitions |
| Fault and scenario application | Niagara and material parameter wiring |
| Automated plausibility tests | Level dressing tools and presets |

Rule: behavior that affects logs or scoring is in C++ and tested. Presentation is in Blueprint.

## Communication with the Python Mission Core

See [unreal-integration.md](unreal-integration.md). Summary: loopback TCP with the same JSON Lines
messages already running on the lightweight backend. Unreal reads the same scenario files, writes the
same log formats, and is scored by the same evaluator. Its `model_version` must differ, and results
are not comparable between backends.

## Unreal MCP automation candidates

All **unverified**. Run in a disposable level first, with read-only checks before edits.

| Task | Tool order | Human review |
| --- | --- | --- |
| List actors, check level contents | MCP | Low |
| Run automation tests, collect results | MCP | Low |
| Capture reference camera screenshots | MCP or Editor Python | Compare images |
| Check asset naming and license folders | Editor Python | Report |
| Spawn test rigs, set lighting presets | MCP | Check level |
| Tune material instance parameters | MCP | **Required**, by eye |
| Batch import from pipeline | Editor Python, versioned | Check result |
| Rock scatter parameters | MCP or Editor Python | **Required** |
| Author core rover C++ | Not MCP; normal code and review | Required |

Do not automate: license decisions, final look approval, or anything through MCP at runtime.

## First 3D slice order

1. Install after approval. Record engine version, and measure an empty project.
2. Verify MCP using [the read-only plan](unreal-mcp.md).
3. Create the C++ project. Confirm a clean clone opens.
4. Greybox: flat plane, box rover, keyboard input through the `Action` path.
5. Physics spike with rocker-bogie, and the plausibility test suite. Record ADR.
6. Bridge: Python agent drives greybox. Write logs, then score them with `roverloom score`.
7. Replay from logs. Add camera switching.
8. Import real terrain, and rerun plausibility tests.
9. On a capable machine: materials, rocks, lighting, atmosphere, dust.
10. Visual rover, sensor views, polish. Publish graphics and physics reports separately.

Greybox steps 3–7 can be done at low settings on the current laptop if testing allows.
