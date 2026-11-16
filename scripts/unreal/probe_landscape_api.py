"""List the Unreal Python names that could build or fill a Landscape, to choose an import path. Read-only.

UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script=scripts/unreal/probe_landscape_api.py -unattended -nullrhi
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import unreal  # type: ignore[import-not-found]

WORDS = (
    "andscape",
    "Heightmap",
    "HeightMap",
    "Foliage",
    "PCG",
    "Niagara",
    "Decal",
    "SkyAtmosphere",
    "VolumetricCloud",
)
for name in sorted(dir(unreal)):
    if any(word in name for word in WORDS):
        print(f"PROBE {name}")
