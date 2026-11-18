# Unreal project

A UE 5.8 C++ project with a generated practice ground, keyboard-controlled rover, cameras, HUD, and an experimental Python mission link. The drive model is provisional and unvalidated. The Gale landscape and imported art are outside Git.

Start with [First 3D mission](../docs/first-3d-mission.md) for the same-machine build/launch candidate. It needs no project art assets; a fresh-machine Unreal build and playtest of that launcher are still pending. Earlier keyboard-play evidence is in [G4a](../docs/results/g4a-manual/README.md).

Python owns mission verdicts. Real-time Unreal runs are not scored or ranked. See [the contract](../docs/unreal-contract.md).

## Build on a Mac

Requires the tools recorded in [ADR 0013](../docs/decisions/0013-ue-5-8-4-on-macos-27.md). `UE_ROOT` is your engine directory.

```shell
"$UE_ROOT/Engine/Build/BatchFiles/Mac/Build.sh" RoverloomEditor Mac Development -project="$PWD/Roverloom.uproject" -WaitMutex
```

Package, always with `-package`, then run the `.app`:

```shell
"$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project="$PWD/Roverloom.uproject" -noP4 -platform=Mac \
  -clientconfig=Development -build -cook -allmaps -stage -pak -package -archive -archivedirectory="$PWD/Packaged" \
  -nocompileeditor -utf8output -unattended
```

Run the module test without rendering:

```shell
"$UE_ROOT/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$PWD/Roverloom.uproject" -nullrhi -unattended -nosplash \
  -nosound -culture=en -ExecCmds="Automation RunTests Roverloom" -TestExit="Automation Test Queue Empty" -log
```

Run the physics spike from the repository root. Records go to `Saved/PhysicsSpike/`, which Git ignores:

```shell
python3 scripts/physics_spike.py run r0 --batch <name>
python3 scripts/physics_spike.py analyze --batch <name>
```

Unreal MCP is enabled for the editor target only, and is not a runtime dependency. See [Unreal MCP](../docs/unreal-mcp.md).

## Editor changes to `Config/`

Review `git diff Config/` before committing. `AndroidFileServer` is disabled because it writes a changing `SecurityToken` to `DefaultEngine.ini`.
See [ADR 0013](../docs/decisions/0013-ue-5-8-4-on-macos-27.md). The Development build also listens on port 1985 on all interfaces, an
[open security issue](../docs/security.md#unresolved).
