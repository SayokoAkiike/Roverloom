# Site candidates and look references for G3 to G5

**Status: research only, 2026-11-07.** Nothing was downloaded. DTM listings come from the USGS STAC API's
[`mro_hirise_socet_dtms`](https://stac.astrogeology.usgs.gov/api/collections/mro_hirise_socet_dtms) collection,
CC0-1.0, queried on 2026-11-07 for metadata only. The owner chooses the site after viewing each product's
thumbnail and hillshade. Gates are in [release-gates.md](release-gates.md#g3-the-site).

## How to choose a site

| Criterion | Why |
| --- | --- |
| DTM at about 1 m post spacing (`DTEEC` products), not 2 m | Wheel-scale detail must be generated anyway; finer measured shape leaves less to invent |
| A 1 km square inside the DTM with mostly drivable slopes, under about 15°, and a few steeper features | The rover and phase G are tested to 15° |
| Three or more visually distinct targets within 1 km: outcrop, dunes, a crater rim, layered rock | The alpha mission needs three science targets |
| Ground-level images of the same kind of terrain, for look comparison | G5 compares `Capture` frames with credited rover images |
| No implication that the rover is a NASA rover | The rover is an original design wherever it drives |

## Candidates

All are `DTEEC` products at about 1 m, except where noted. The rationale is USGS's own text for the product.

| Site | Product ID | USGS rationale | For | Against |
| --- | --- | --- | --- | --- |
| **Gale crater, Aeolis Mons** | `DTEEC_063319_1745_052242_1745_A01` | Fan material at alcove on southwestern Aeolis Mons | Layered mountain slopes; many Curiosity images of similar terrain; [Cesium Mars](visual-technology-review.md#other-tools-found-20252026) has Gale at 1 m for a horizon | Steep in places; check drivable area |
| Gale crater, dunes | `DTEEC_040770_1755_039280_1755_A01` | Gale Crater dunes and Curiosity rover | Dunes beside rock; references for both | The orthoimage shows Curiosity itself, which invites comparison with NASA's rover |
| **Jezero crater** | `DTEEC_048842_1985_048908_1985_U01` | Candidate landing site for 2020 mission in Jezero Crater | Delta front, a clear scientific story; many Perseverance images | The same association with a NASA rover |
| **Eberswalde crater** | `DTEEC_001336_1560_001534_1560_U01` | Fan/deltaic landform in west Eberswalde Crater | A delta with no rover history, so no comparison with a real rover's path | No ground-level images of the site itself |
| Oxia Planum | `DTEEC_063839_1980_064261_1980_H01` | Candidate ExoMars landing site in Oxia Planum | Clay-bearing plains; ESA's planned site | Flat, so fewer visual features |
| Victoria crater, Meridiani | `DTEEC_021747_1780_022380_1780_U01` | Victoria Crater | A dramatic rim; Opportunity images | A rover path along a cliff edge is hard to make safe in 15 minutes |

Searches near Nili Fossae, at 21.5° N, 78.5° E, found no product in a 2° box.

**Recommendation for the alpha:** Gale, `DTEEC_063319_1745_052242_1745_A01`, if a 1 km drivable square exists in it;
else Eberswalde. Gale offers the most ground-level references for G5. Eberswalde avoids any comparison with a real
rover's path. Neither choice is final before the owner has seen the thumbnails.

## Look references

Stored outside Git unless their terms are confirmed, as the [production plan](unreal-production-plan.md#visual-direction)
requires. NASA states that its images are generally not protected by copyright, while its insignia, logotype, and
identifiers are protected and may not be used ([NASA media guidelines](https://www.nasa.gov/multimedia/guidelines/index.html)).
Some images on NASA sites belong to partners; check each credit line. This is not legal advice.

| Reference | What it shows | Use it for | Caution |
| --- | --- | --- | --- |
| [PIA19400](https://photojournal.jpl.nasa.gov/catalog/PIA19400), Sunset in Mars' Gale Crater, Curiosity, sol 956 | Blue glow around the setting Sun | Sky color near the Sun at sunset | NASA notes the blue is not quite what a human would see; compare hue structure, not exact color |
| [PIA00917](https://pds-rings.seti.org/press_releases/pages/PIA00xxx/PIA00917.html), Pathfinder sunset | The same effect, another site and camera | A second, independent sunset reference | Older camera |
| [PIA20840](https://www.jpl.nasa.gov/images/pia20840-rovers-panorama-taken-amid-murray-buttes-on-mars/), Murray Buttes panorama, Curiosity Mastcam | Buttes, sand, and haze from mast height | Scale, rock layering, and haze with distance | **White balanced** to resemble Earth daylight. Use it for shapes and relative albedo, not sky color |
| [PIA16768](https://en.wikipedia.com/wiki/File:PIA16768-MarsCuriosityRover-AeolisMons-20120920.jpg), Mount Sharp in white-balanced colors | Aeolis Mons from the plains | Distant mountain in haze | NASA notes that white balancing makes Martian scenes look too blue |
| The HiRISE product's own orthoimage and hillshade, from the STAC listing | The site from above | Checking that rendered terrain shading matches the measured shape | Grayscale or false color; not a color reference |

**Color rule:** match sky and overall tint only against images labeled natural or approximately true color. Use
white-balanced images only for material contrast and shape.

## Three fixed camera shots

Each is a fixed camera saved in the level, rendered in `Capture` through Movie Render Graph, and judged in G5 beside
its references. The same three are also taken in `Play` to record what real time loses.

### Shot 1. Mast view, late afternoon: the robot's photograph

| Setting | Value |
| --- | --- |
| Camera | On the rover's mast at 2.0 m, pitched 5° down |
| Lens | 45° horizontal field of view, as a navigation camera might have; a second 15° telephoto frame of the same view |
| Sun | 20° above the horizon, behind and to the left |
| Preset | Normal dust |
| Framing | Rover deck edge in the lowest tenth; outcrop or dunes at 50–200 m; horizon in the upper third, fading into haze |
| Compare with | PIA20840 for scale and layering; PIA16768 for distant haze |
| Passes when | Reviewers find the rock size distribution, haze with distance, and absence of visible tiling believable |

### Shot 2. From orbit to the surface: the site as data

| Setting | Value |
| --- | --- |
| Camera | 400 m above the site's center, pitched 35° down, the whole 1 km square in frame |
| Lens | 60° horizontal field of view |
| Sun | 60° above the horizon |
| Preset | Clear |
| Framing | The rover small near the center, with its track; an on-screen label: "Terrain: HiRISE DTM `<product ID>`, USGS, CC0. Detail below 1 m generated" |
| Compare with | The same product's hillshade and orthoimage, rendered from straight above at the same Sun angle, side by side |
| Passes when | Ridges, craters, and dunes line up with the hillshade, and nothing larger than the DTM's spacing is invented |

This shot does what NASA's Eyes does well: it shows where the data come from. It is also the one check of the
terrain's shape that needs no judgment.

### Shot 3. Low chase at sunset: the moment players remember

| Setting | Value |
| --- | --- |
| Camera | 1.2 m above the ground, 6 m behind the rover and 30° to its side, looking toward the Sun |
| Lens | 35° horizontal field of view |
| Sun | 3° above the horizon, ahead of the rover |
| Preset | Dusty |
| Framing | Rover in silhouette at the left third; long shadows of rocks toward the camera; wheel tracks and a thin dust plume |
| Compare with | PIA19400 and PIA00917 for the glow around the Sun |
| Passes when | The blue glow stays near the Sun, the sky away from it stays butterscotch, and exposure is fixed rather than automatic |

## What these choices do not claim

A real site's shape does not validate the rover's motion, the soil, or the light. Reference images are compared by
eye, and the reviewers and their verdicts are recorded. The look is judged in `Capture` only.
