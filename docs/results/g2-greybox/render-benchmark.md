# G2 greybox render benchmark, 2026-11-07

**What this is:** a GPU baseline for the greybox test ground, before any Mars terrain or lighting work. One machine, one
nearly empty scene, rover at rest, chase camera. **It does not predict cost on a real site,** where geometry, materials,
and lighting change the balance. Nothing here changes the drive model, the Mission Core, or any research data.

## Read this first

- **Display sync shapes every number.** A windowed game on Mac cannot exceed 60 fps, whatever `r.VSync` says. Under that
  cap the GPU reported about 4 ms more per frame than uncapped, for the same scene. Only the exclusive-fullscreen,
  uncapped rows measure cost; the capped rows only rank conditions.
- **TSR against TAA:** about 4.2 ms of GPU time at 1600 × 900 here (10.75 ms against 6.57 ms, uncapped), the largest
  difference measured. The profiler puts most of it in one pass whose cost is not explained.
- **Image quality is mostly not evaluated.** Still crops were looked at by one person. Temporal stability, ghosting,
  softness at lower screen percentages, and TSR's advantage over TAA were not judged, and no reviewer compared shots.
- **Everything must be measured again after real terrain is added,** and on the MacBook Air, in a packaged build, and over
  25 minutes. Lumen, Virtual Shadow Maps, and Nanite cost almost nothing in this empty scene, which says nothing about a
  site.

## Setup

| Item | Value |
| --- | --- |
| Machine | Mac mini, Apple M4, 16 GB, macOS 27.0.1, one display at 60 Hz |
| Engine | UE 5.8.4 (CL 58902052), editor binary with `-game` (not a packaged build), Metal SM6 |
| Code | `0f7b2f6`, with the benchmark mode `-RoverBench=<s>` |
| Scene | `RoverPlaygroundGameMode` on `/Engine/Maps/Entry`: 30 blocks, 24 of them rocks, sun, sky atmosphere, sky light, fog |
| Run | Fresh process per condition, 40–45 s; the first 10 s window discarded as warm-up, and any window with a frame over 100 ms |
| Measures per 10 s window | Frames, FPS, frame time mean and p95, max, game-thread, render-thread, and GPU time (`RHIGetGPUFrameCycles`), share of frames with focus |
| Checks | Effective CVars and viewport logged at start and end of each run; one `ProfileGPU` frame per run; one chase screenshot per run |
| Restore | `GameUserSettings.ini` copied back after each run; checked equal to the pre-benchmark copy by SHA-256 at the end |

Raw logs, screenshots, and the run script are on the Mac mini under `unreal/Saved/G2Bench/`, outside Git.

## The project's effective defaults

`DefaultEngine.ini` sets no renderer options, so engine base defaults apply, not a template project's Lumen defaults:
dynamic GI **off** (`r.DynamicGlobalIlluminationMethod=0`), reflections SSR (`2`), Virtual Shadow Maps **off**, AA TSR
(`4`), screen percentage automatic from display resolution (1336 × 751 inside a 1600 × 900 window, 83.5%), Nanite on,
scalability Epic (3). Hardware ray tracing is unavailable without a project setting and a restart (`r.RayTracing=0`),
and was not tried. `r.MegaLights.Enable` does not exist in this build.

## Measurement validity

- **A windowed game cannot run above the display rate on Mac.** `MetalViewport.cpp` sets the Metal layer's
  `displaySyncEnabled` unless the game is in true fullscreen. `r.VSync 0`, `t.MaxFPS 0`, `rhi.SyncInterval 0`, and
  `-fullscreen` all stayed at 60 fps. `r.SetRes 1600x900f` (exclusive fullscreen) removed the cap.
- **Capped GPU times overstate cost.** The same baseline gave GPU 14.6 ms capped and 10.75 ms uncapped. The likely cause is
  the GPU running more slowly when not saturated; this is not confirmed. Capped numbers below are used only to rank.
- The RHI reports that its GPU frame time removes idle gaps (`GRHISupportsFrameCyclesBubblesRemoval=1`).
- **One profiled pass is unexplained:** `TSR ClearPrevTextures` takes 3.2–7.1 ms in every TSR frame profiled, and scales with
  resolution. With TSR and Virtual Shadow Maps together, the large pass appears instead as `VSM Log Stats And Status`. The
  per-pass attribution may be off; the total, and the TSR-against-TAA difference, are consistent.
- A first `validate_exclusive` run inherited `sg.*=4` from the previous run's saved settings, and was set aside. That is how
  the restore step above was found to be needed.

## Uncapped results, exclusive fullscreen

| Condition (one change from base) | FPS | Frame mean / p95 ms | Game ms | GPU ms |
| --- | --- | --- | --- | --- |
| **Base**: TSR, auto 83.5%, Epic, no GI, SSR, no VSM, 1600 × 900 | 83.5 | 11.97 / 12.50 | 1.61 | **10.75** |
| AA TAA | 133.9 | 7.46 / 8.11 | 1.57 | 6.57 |
| Screen percentage 50 | 132.2 | 7.56 / 8.41 | 1.43 | 6.31 |
| Screen percentage 75 | 91.8 | 10.89 / 11.62 | 1.62 | 9.61 |
| Screen percentage 100 | 66.0 | 15.14 / 15.68 | 1.46 | 13.95 |
| Window 1280 × 720 | 93.9 | 10.64 / 11.30 | 1.58 | 9.43 |
| Window 1920 × 1080 | 71.1 | 14.07 / 14.63 | 1.57 | 13.04 |

## Capped results, windowed 1600 × 900, for ranking only

All at 60.0 fps, frame p95 16.94–17.34 ms, game thread 1.25–2.00 ms.

| Condition | GPU ms | Change from base |
| --- | --- | --- |
| Base | 14.57 | — |
| Lumen GI and Lumen reflections | 14.78 | +0.2 |
| Lumen GI, SSR | 14.88 | +0.3 |
| SSGI | 14.92 | +0.4 |
| No reflections | 14.86 | +0.3, within noise |
| Virtual Shadow Maps on | 14.22 | −0.4, within noise |
| AA none | 9.86 | −4.7 |
| AA FXAA | 9.43 | −5.1 |
| AA TAA | 10.10 | −4.5 |
| Scalability Low (all groups 0) | 15.97 | +1.4, **unexplained**; `Scene` takes 8 ms in its profile |
| Scalability Medium (1) | 12.59 | −2.0 |
| Scalability High (2) | 14.50 | −0.1 |
| Scalability Cinematic (4) | 15.83 | +1.3 |

In this scene Lumen, SSGI, and Virtual Shadow Maps cost under half a millisecond, because there is almost nothing to light
or shadow. Their real cost will show only on a site.

## Image quality

Same chase camera in every run. Crops of the rover are kept with the logs.

| Condition | What changes on screen |
| --- | --- |
| TAA, FXAA, none against TSR | Edge differences barely visible at this scale. Not judged in motion |
| Lumen GI, Virtual Shadow Maps | Small change in shading under the rover |
| **Scalability Low and Medium** | **The rover's ground shadow disappears**, and its underside turns flat and bright |
| Screen percentage 50 | Not judged; the crop is too small to show softness |

Visual judgment here is one person's look at still crops, not a review.

## Profile candidates, measured uncapped at 1600 × 900

| Candidate | Settings | FPS | Frame p95 ms | GPU ms | Note |
| --- | --- | --- | --- | --- | --- |
| Dev, as run | TAA, 75%, Medium, no GI, no VSM | 190.0 | 7.92 | 4.23 | **Loses the rover's shadow**; not acceptable as run |
| Play | TAA, 100%, Epic, Lumen GI and reflections, VSM | 93.4 | 11.46 | 10.43 | Meets the 30 fps p95 target here with wide margin |
| Capture | TSR, 100%, Cinematic, Lumen GI and reflections, VSM | 55.0 | 18.68 | 17.95 | Real-time only as a preview; final frames go through Movie Render Graph |

## Proposed profiles, not yet adopted

| Profile | Proposal | Status |
| --- | --- | --- |
| `Dev` | TAA, screen percentage 75, Scalability **High (2)** so that shadows stay, no dynamic GI, SSR, no VSM | Not measured as a whole; the Medium version above lost shadows |
| `Play` | TAA, screen percentage 100 on the Mac mini, Epic, Lumen GI and reflections, VSM; drop to 83% (automatic) or TSR only if a site needs it | Measured above on the greybox only |
| `Capture` | TSR at 100%, Cinematic, Lumen GI and reflections, VSM, fixed exposure; rendered offline through Movie Render Graph | Measured in real time only; Movie Render Graph not tried |

Choosing TAA over TSR saves about 4 ms here, the largest single difference measured. TSR's quality advantage at lower
screen percentages was not judged. Each profile needs re-measurement on the first real site, on the MacBook Air, in a
packaged build, and over 25 minutes, before it is adopted in a decision record.
