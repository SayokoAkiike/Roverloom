"""List what a Niagara template system exposes, to see whether it can be styled as dust from code. Read-only.

UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script=scripts/unreal/probe_niagara.py -unattended -nullrhi
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import unreal  # type: ignore[import-not-found]

for path in (
    "/Niagara/DefaultAssets/Templates/Systems/FountainLightweight",
    "/Niagara/DefaultAssets/Templates/Systems/DirectionalBurstLightweight",
    "/Niagara/DefaultAssets/Templates/Systems/MinimalLightweight",
):
    name = path.rsplit("/", 1)[1]
    print(
        f"PROBE exists={unreal.EditorAssetLibrary.does_asset_exist(path)} / {unreal.EditorAssetLibrary.does_asset_exist(path + '.' + name)}"
    )
    system = unreal.load_object(None, path + "." + name)
    print(f"PROBE {path} -> {system}")
    if system is None:
        continue
    for name in dir(system):
        if any(
            word in name.lower() for word in ("param", "emitter", "exposed", "user")
        ) and not name.startswith("_"):
            print(f"PROBE   {name}")
    for getter in ("get_exposed_parameters", "get_emitter_handles"):
        try:
            print(f"PROBE   {getter}: {getattr(system, getter)()}")
        except Exception as error:  # Not every build exposes these
            print(f"PROBE   {getter} failed: {error}")
print(
    "PROBE factory:",
    [
        n
        for n in dir(unreal)
        if "NiagaraSystemFactory" in n or "NiagaraEditor" in n or "NiagaraSystemEditor" in n
    ],
)

registry = unreal.AssetRegistryHelpers.get_asset_registry()
found = registry.get_assets_by_path("/Niagara/DefaultAssets/Templates/Systems", recursive=False)
print("PROBE registry:", [str(a.asset_name) for a in found])
