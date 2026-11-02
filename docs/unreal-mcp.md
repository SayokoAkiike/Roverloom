# Unreal MCP

**Connection status: verified on one Mac.** Reads, edits, and saves in a disposable project. Reads only in `unreal/`. See [Measured results](#measured-results).
The plugin remains Experimental, and is an editor tool, never a runtime or build dependency.

Reviewed 2026-11-02 against
[Epic: Unreal MCP in Unreal Editor](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?lang=en-US).

**macOS:** Epic's page neither lists nor excludes macOS. The plugin ships with Mac binaries in the UE 5.8.4 Launcher build, and worked
here. That is a measurement, not a statement of support by Epic.

## Facts from Epic's documentation

- Documented for Unreal Engine 5.8 and marked **Experimental**. APIs may change.
- Requires the **Unreal MCP** plugin (`ModelContextProtocol`) and **All Toolsets**. `unreal/` enables `EditorToolset` instead. See [Use from `unreal/`](#use-from-unreal).
  **Toolset Registry** is enabled as a dependency.
- Runs inside the editor at `http://127.0.0.1:8000/mcp`. HTTP and SSE only.
- No authentication. Loopback only; do not expose it beyond the local machine.
- Tool calls run serially on the game thread.
- Tool Search is on by default, exposing `list_toolsets`, `describe_toolset`, and
  `call_tool` as meta-tools. Example toolsets are `SceneTools`, `ActorTools`,
  `MaterialInstanceTools`, and `ObjectTools`.

## Setup procedure (to perform after installing UE 5.8)

1. Open `unreal/` project. In Edit > Plugins enable **Unreal MCP** and **All
   Toolsets**, then restart the editor.
2. In Editor Preferences > General > Model Context Protocol enable **Auto Start
   Server**, or run `ModelContextProtocol.StartServer` in the console.
3. Run in the editor console:
   `ModelContextProtocol.GenerateClientConfig ClaudeCode`.
   This writes `.mcp.json` to the project root. It is ignored by Git for now.
4. With the editor already running, start Claude Code from `unreal/`.

In `-ExecCmds`, separate console commands with commas. A semicolon is passed on as part of the first command.

Expected entry:

```json
{
  "mcpServers": {
    "unreal-mcp": { "type": "http", "url": "http://127.0.0.1:8000/mcp" }
  }
}
```

## Verification plan (read-only, on a disposable map)

Report as connected only after all of these are done and recorded here with engine
version and output:

1. `claude mcp list` reports `unreal-mcp` as connected.
2. `list_toolsets` returns toolsets.
3. `describe_toolset` on the actor toolset identifies a read-only query tool. Epic's
   page does not document a specific "list actors" tool name, so find it here.
4. Call that tool and compare the result with the editor's Outliner.
5. Confirm with `git status` that no project files changed, other than ignored files.

## Measured results

UE 5.8.4 (CL 58902052), macOS 27.0.1, Xcode 27.2, Apple M4, 16 GB, 2026-11-03. Client: Claude Code 2.1.309 with
`claude -p --mcp-config .mcp.json --strict-mcp-config`. Editor on Metal, with `ModelContextProtocol.StartServer`.

| Step | Exact call, under `editor_toolset.toolsets` | Result |
| --- | --- | --- |
| Connect | Client start-up | `status: connected`. `lsof` shows `127.0.0.1:8000` only |
| Discover | `list_toolsets`, `describe_toolset` | 52 toolsets with All Toolsets enabled |
| Read actors | `scene.SceneTools.find_actors` | Matches the actors placed by the same tools. The Outliner was not compared by a person |
| Create | `scene.SceneTools.add_to_scene_from_asset` | Actor created. `name` becomes the label, not the object name |
| Change transform | `actor.ActorTools.set_actor_transform`, `get_actor_transform` | Values read back |
| Delete | `scene.SceneTools.remove_from_scene` | Actor removed |
| Save | `asset.AssetTools.save_assets`, `is_dirty` | `is_dirty` false, and the file changed |
| Restart | Quit, start, then read again through a new client | All labels and transforms matched |
| Material | `material.MaterialTools`, `object.ObjectTools.set_properties` | Compiled, applied, and seen in `EditorToolset.EditorAppToolset.CaptureViewport` |

Connect, read, create, change, save, and restart also worked with `-nullrhi`, without Metal, before Xcode was installed.

**Not verified:** edits and saves from `unreal/`, any toolset not listed above, and a person comparing results with the Outliner.

### Use from `unreal/`

Same machine and versions, 2026-11-03. `Roverloom.uproject` enables `ModelContextProtocol` and `EditorToolset` for the editor target only, which
differs from Epic's page. The editor log reports 19 toolsets.

| Check | Result |
| --- | --- |
| `claude -p --mcp-config .mcp.json --strict-mcp-config`, started from `unreal/` | `status: connected` |
| `list_toolsets`, `describe_toolset`, `scene.SceneTools.get_current_level`, `find_actors`, `asset.AssetTools.is_dirty` | Succeeded. The editor log shows no other tool dispatched |
| Tracked and generated files before start, after start, after the calls, after exit | Identical |
| `GameFeatureData` error seen with All Toolsets | Not logged |
| Packaged `.app` | No plugin files, and no plugin text in its executable. The `.uproject` copied into the `.pak` still names the plugin |

### Behavior worth knowing

- `call_tool` takes the full `toolset_name` and a bare `tool_name`.
- `set_properties` takes `values` as a JSON **string**, with names from `list_properties`. A wrong form returns `false` with no other error.
- A duplicated level is unsaved. `load_level` refuses it until `save_assets` has run.
- After an editor crash, `CrashReportClient` kept the listening socket, and still held port 8000 about 18 minutes later, until it was stopped.
- Started right after another editor exited, an editor logged `HttpListener unable to bind`, and had no server. The cause is not confirmed. Waiting until the port could be bound avoided it.
- The plugin's log warning cites Section 6(e) of the UE EULA. Read [Epic's EULA and change log](https://www.unrealengine.com/eula-change-log/unreal) yourself. This page is not legal advice.

## Options if official MCP lacks something

| Option | Strengths | Weaknesses | Use for |
| --- | --- | --- | --- |
| Official Unreal MCP | First-party, in-process, no bridge | Experimental, 5.8, incomplete docs | First choice for editor inspection and edits by agents |
| Community MCP, e.g. [ChiR24/Unreal_mcp](https://github.com/ChiR24/Unreal_mcp) | Claims wider tools and 5.0–5.8 | Third-party code in the editor; review needed for security, license, and maintenance | Only for a specific gap, after audit |
| Editor Python | Stable scripted, reproducible, reviewable in Git | Editor only; not a runtime API | Repeatable content pipelines and batch tasks |
| Unreal C++ | Full control, runtime capable, can add custom toolset functions | Slow to build on this machine | Rover physics and runtime systems |

**Decision:** Start with official MCP. Move repeatable work into versioned Editor
Python scripts. Use C++ for all runtime behavior. Consider community MCP only for a
gap that the above cannot fill.
