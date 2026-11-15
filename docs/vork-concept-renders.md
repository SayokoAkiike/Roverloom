# Concept renders with vork

How to make promotional images of the V2 rover with [vork](https://github.com/voyager-so/vork), on the Mac. The
rules are in [ADR 0015](decisions/0015-vork-for-concept-renders.md). **Every image is labeled "Concept render (vork),
not a game screenshot".**

## State, 2026-11-15

| Step | Done where | Result |
| --- | --- | --- |
| Rover glTF from `scripts/blender/build_rover.py` | Linux cloud container, `bpy` 5.0.1 | Built; body, 6 wheels, struts, axles |
| Scenes from `scripts/vork/rover_concept.py` | Same container, vork 0.5.1 | `hero`, `side`, `sunset` written |
| `vork check` on the three scenes | Same container, no GPU | `Scene checked successfully` for all three |
| `vork check --shaders` on `hero` | Same container | See the [V2 results](results/v2-rover-model/README.md#concept-renders-with-vork) |
| Rendering, and judging the look | Mac mini M4, vork 0.5.1, 2026-11-15 | Three images at 1600 × 900. See the [results](results/concept-renders/README.md) |

The first drafts were washed out, because vork's physical sky is Earth's. The script now uses its own sky program,
thinner dust, generated terrain, and faceted rocks. The look was judged by Claude Code only, not yet by the owner.

## On the Mac

vork needs Apple silicon and macOS 26 or later. Read its [license](https://github.com/voyager-so/vork/blob/main/LICENSE)
first. Install it with its own installer, which places it in `~/.local/bin`:

```shell
curl -fL https://github.com/voyager-so/vork/releases/latest/download/install.sh -o /tmp/vork-install.sh
```

```shell
sh /tmp/vork-install.sh
```

Then, from the repository root, build the rover with Blender, write the scenes, check them, and render a quick
preview first:

```shell
blender -b -P scripts/blender/build_rover.py -- --out unreal/Saved/RoverModel
```

```shell
python3 scripts/vork/rover_concept.py --out unreal/Saved/RoverConcept
```

```shell
vork check unreal/Saved/RoverConcept/hero.json
```

```shell
vork render unreal/Saved/RoverConcept/hero.json --profile std/draft --out unreal/Saved/RoverConcept/hero-draft.png
```

The dust haze makes vork use path transport, which is slower. Use `--no-fog` while framing shots, and `--only hero`
to write one shot. Render final
images with `--profile std/final`, or `std/path` if indirect light looks too dark.

## What to tune, by eye

| Look | Where |
| --- | --- |
| Too bright or dark | `--exposure` (AgX stops) |
| Too bright or dark, per shot | `SHOTS`: `exposure` |
| Sky colors and glow | `SKY_PROGRAM` inputs: `zenith`, `horizon`, `glow`, `aureole`. vork's own `std/sky` models Earth's air and looked wrong |
| Sun and sky strength | `SHOTS`: `tau`, the dust's optical depth |
| Haze too thick or thin | `SHOTS`: `haze`; `DUST_PROGRAM`: `scattering`, `falloff` |
| Shots | `SHOTS`: camera, target, lens, sun elevation and rotation. Sun yaw in the world is rotation minus 90° |
| Ground and rocks | `terrain_height()`, `regolith_color()`, `rock_shape()`, `rock_nodes()`: count, size law, seed |

Record each choice and who judged it. Match the sky only against approximately true-color references, as
[site-and-look-references.md](site-and-look-references.md) says.

## Committing images

- Commit from the Mac, through Git LFS, under `docs/images/concept/`, as JPEG or PNG under 500 KB.
- Next to each image, record the vork version, profile, samples, resolution, commit, and machine.
- In the README, put concept renders in their own labeled section. Never use them as the game's screenshot.
