# Sunset sky: a blue glow around the sun, 2026-11-16

The owner asked for a sunset sky like the photographs of Mars: blue around the sun, red-brown toward the horizon, by changing the Sky Atmosphere's own
Rayleigh and Mie colour, coefficients, and absorption (the height fog did not reach the sky). **The blue glow around the sun is now possible, as a second
preset (`-RoverLight=sunset_blue`), but not together with a red-brown horizon.** The first preset, `sunset`, is unchanged: its sky is red-brown and has no
blue glow. Looks only: no physics, collision, or drive value changed.

## What was found

1. **My earlier tests never had the sun in view.** The sunset sun sits 5.5 degrees above the horizon, and the cameras I used did not see it. The tests below use a
   camera that does (`scripts/unreal/render_mrq.sh sky sunset`: 2 m up, 6 degrees above the horizon, azimuth 15, 90 degrees of field of view). In it the engine's
   glow is a wide warm patch along the sun's azimuth, brightest at the top of the frame.
2. **The sky's colour is the sun light's colour times the Mie scattering.** With the Mie scale at zero the whole sky goes dark (far sky 14, 7, 5). With a blue sun light,
   the whole sky turns blue, near and far alike (far B/R 1.55). The Rayleigh scale and colour, and the fog, change nothing (identical to the base, D3 and D4 below).
3. **A low sun's light reaches the sky already reddened.** The Mie colour is also its extinction, and blue is extinguished first along the long path. So a blue Mie
   colour (even with an anisotropy of 0.93) gives a yellow glow, not a blue one (T4).
4. **A layer that absorbs red and green does the job.** The engine's "other absorption" (an ozone-like layer), strong in red and green, leaves the blue. With a pale
   sun light it turns the sky around the sun blue-white, fading to violet and pink at the horizon (E3, F1, F2): the blue sunsets photographed on Mars.
   The price: the whole sky goes blue, and the horizon is pale pink-beige (B/R 0.84), not red-brown. The sun is the only light, so the ground is lit by that sky and is dim.

## Pixel values

Sky view, the same camera, `-RoverLight=sunset` with the overrides listed. "Near" is within 80 px of the glow's centre (x 960, y 30), "far" is 300 to 500 px from it, and
"horizon" is a band along the horizon. Mean sRGB 0 to 255. B/R is blue over red.

| Run | Settings changed from `sunset` | Near RGB | Near B/R | Far B/R | Horizon B/R |
| --- | --- | --- | --- | --- | --- |
| **base** | none (red sun light, Mie blue, absorption `0.35, 0.55, 0.75` x 0.006) | 226, 188, 134 | **0.59** | 0.38 | 0.62 |
| T1 | sun light 1, 0.9, 0.8; Mie absorption 0.9, 0.5, 0.15 x 0.02 | 212, 218, 208 | 0.98 | 0.94 | |
| T2 | T1 and Mie scale 0.3 | 221, 210, 151 | 0.68 | 0.58 | |
| T3 | T2 and Rayleigh scale 0.02, colour 0.02, 0.08, 0.4 | 221, 209, 147 | 0.67 | 0.57 | |
| T4 | Mie colour 0.1, 0.3, 1, anisotropy 0.85, scale 0.4, absorption 1, 0.7, 0.1 x 0.05, Rayleigh 0.03 | 216, 213, 121 | 0.56 | 0.46 | |
| D1 | sun light 0.3, 0.5, 1 (blue) | 165, 196, 211 | 1.28 | 1.55 | |
| D2 | Mie scale 0 | 70, 41, 29 | 0.41 | 0.33 | |
| D3 | Rayleigh scale 0 | 226, 188, 134 | 0.59 | 0.38 | |
| D4 | fog maximum opacity 0 | 226, 188, 134 | 0.59 | 0.37 | |
| E1 | other absorption 1, 0.55, 0.05 x 0.02 | 206, 174, 124 | 0.60 | 0.43 | |
| E2 | the same x 0.1 | 91, 98, 93 | 1.02 | 0.88 | |
| E3 | the same x 0.1 and sun light 1, 0.9, 0.8 | 107, 162, 193 | 1.80 | 2.24 | |
| E4 | the same x 0.3 and sun light 1, 0.9, 0.8 | 73, 45, 81 | 1.11 | 6.28 | |
| F0 | base, with the horizon band measured | 226, 188, 134 | 0.59 | 0.38 | 0.62 |
| F1 | sun light 1, 0.9, 0.8; other absorption x 0.05 | 178, 198, 199 | 1.12 | 1.21 | 0.83 |
| **F2** | sun light 1, 0.9, 0.8; other absorption x 0.07 | **151, 185, 196** | **1.30** | 1.52 | 0.84 |
| F3 | sun light 1, 0.7, 0.45; other absorption x 0.07 | 143, 167, 160 | 1.12 | 1.09 | 0.74 |
| **`sunset_blue`** | F2 with exposure 12.2 (raised, because the ground is dim) | **192, 215, 223** | **1.16** | 1.42 | 1.08 |

**Before and after, near the sun:** B/R rises from **0.59 to 1.16** (RGB 226, 188, 134 becomes 192, 215, 223) in the shipped preset, and to 1.30 in F2 at the base exposure.
The blue is not local to the sun: the far sky is blue too (B/R 1.42), so this is a blue sky that is brightest around the sun, not a blue halo in a brown sky. E4 and E2 are too dark, and D1 is the whole sky blue.

## Images

| | |
| --- | --- |
| The sky view, base | [sky_base.jpg](sky_base.jpg) |
| The sky view, F2 | [sky_F2_blue_near_sun.jpg](sky_F2_blue_near_sun.jpg) |
| Base, F1, F2, E3 (top left to bottom right) | [sky_trials_base_F1_F2_E3.jpg](sky_trials_base_F1_F2_E3.jpg) |
| `sunset_blue`, Capture, 1920 x 1080 | [capture_still_sunset_blue.jpg](capture_still_sunset_blue.jpg) |
| `sunset` (red-brown, no glow), for comparison | [capture_still_sunset.jpg](../gale-effects/capture_still_sunset.jpg) |

## How to use

`-RoverLight=sunset` is the red-brown sunset. `-RoverLight=sunset_blue` is the blue one. The settings can be tried without a rebuild with
`-RoverSunElevation`, `-RoverSunYaw`, `-RoverSunColor=r,g,b`, `-RoverMieScale`, `-RoverMieAniso`, `-RoverMieColor=r,g,b`, `-RoverMieAbsScale`, `-RoverMieAbsColor=r,g,b`,
`-RoverRayleighScale`, `-RoverRayleighColor=r,g,b`, `-RoverOtherAbsScale`, and `-RoverOtherAbsColor=r,g,b`.

## Not achieved

A blue glow around the sun with a red-brown horizon, in one sky. The engine ties the sky's colour to the sun light's colour, so the horizon takes the same blue. A second
light, a hand-painted sky, or a post-process glow would be needed. The sun disc itself was never seen as a disc.
