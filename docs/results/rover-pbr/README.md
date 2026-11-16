# Rover PBR materials and a 1080p HUD, 2026-11-16

Looks only, on the Mac mini (Apple M4, 16 GB, UE 5.8.4, Metal): no collision and no physics value changed. Colours are chosen by eye, not measured.

## Materials

The V2 rover had flat colours. `scripts/unreal/build_rover_materials.py` gives its six material slots, and the wheel's two, PBR materials, all
procedural: they do not rely on the meshes' UVs, so they take their patterns from the mesh's own coordinates and from noise, and no texture or
third-party asset is used (the Poly Haven CC0 textures were allowed, but a brushed metal and a rubber did not need them). They are in
`unreal/Content/Licensed/Gale/Rover/`, which Git ignores, and recorded in [assets-and-sources.md](../../assets-and-sources.md).

| Part | Material |
| --- | --- |
| Body | Cream painted panels, metallic 0.25, seams every 50 cm |
| Thermal blanket | Gold foil, fully metallic, crinkled by noise in the normal and the roughness |
| Arms, struts, wheel hubs and grousers | Brushed aluminium: a noise stretched along one axis drives the roughness |
| Wheel tyres | Matt rubber, roughness 0.86 to 0.96, with a bumpy normal |
| Solar deck | A grid of 15 cm cells, each a slightly different dark blue, with silver busbars between them; the silicon is a non-metal with a weak reflection |
| Mast and camera heads | Dark anodised metal |
| Lenses | Near-black glass with a violet coating that shows at grazing angles |

**Dust** sits on every material, scaled by a `DustAmount` parameter (0 to 1, default 0.85): it settles on faces that point up and on the low parts of each mesh
(height below the mesh origin, so the lower halves of the wheels and the underside of the body gather most), broken up by noise, and it turns a surface
matt and non-metallic where it lies. Stickiness differs by part: the solar deck 0.08, lenses 0.1, foil 0.5, aluminium and dark metal 0.7, body 0.8, tyres 1.0.
The first version let the dust cover the solar deck and the foil, so the cell grid and the foil could not be seen; the stickiness values are the correction.

## Images

Movie Render Queue, Capture profile, afternoon preset, 1920 x 1080, the same camera before and after. The before images have the flat first-import materials put back.

| View | Before | After |
| --- | --- | --- |
| Close three-quarter, 2.9 m, at the wheels' height | [close_before.jpg](close_before.jpg) | [close_after.jpg](close_after.jpg) |
| From above and behind (the solar deck, and dust on up-facing faces) | [top_before.jpg](top_before.jpg) | [top_after.jpg](top_after.jpg) |

In the close view the wheels show metal grousers, a dusty tyre, and a dusty hub; the body panels and arms are dusted from the top and low down; the lenses show a violet
glint. From above, the deck shows its cell grid. **Limits:** the body reads as a plain painted box more than as a real rover, because the V2 mesh is simple, and from the
top view the busbars alias into vertical stripes at a distance. I judged these images myself; nobody else has.

## Frame time

Windowed 1280 x 720, Dev, afternoon preset, rover at rest, two 10 s windows after the first, one run each.

| Rover materials | fps | GPU ms |
| --- | --- | --- |
| Flat colours | 33.5 | 27.1 |
| PBR with dust | 32.6 | 27.5 |

The cost is about 0.5 ms of GPU time, and Dev stays above 30 fps. At 1920 x 1080, Dev ran at 29.4 fps in one run (GPU 29.8 ms), a little under 30: the Dev profile is held at
30 fps or more at 1280 x 720 only.

## HUD at 1080p

The HUD's sizes were fixed in pixels for a 720p window, so on a 1080p screen it looked small. Everything in `RoverHud.cpp` now scales with the viewport
height (1.0 at 720p and below, 1.5 at 1080p, at most 3.0), and `-RoverHudScale=F` overrides it. The panel was 528 x 300 px at 720p and is 792 x 450 px at 1080p, 1.5 times larger
and the same share of the screen. **The "PROVISIONAL DRIVE MODEL P" label and the other lines are unchanged.**

| | Screenshot |
| --- | --- |
| 1280 x 720 | [hud_720p.jpg](hud_720p.jpg) |
| 1920 x 1080 | [hud_1080p.jpg](hud_1080p.jpg) |

## Not done

A mix of Poly Haven textures on the rover (not needed so far), a way to set `DustAmount` while the game runs (it is a material parameter with a default only), and
any dust that grows with time or with distance driven.
