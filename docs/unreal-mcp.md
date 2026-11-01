# Unreal MCP

**Connection status: not verified.** Unreal Engine is not installed, so no connection
or tool call has been attempted. Everything here comes from documentation.

Reviewed 2026-11-02 against
[Epic: Unreal MCP in Unreal Editor](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?lang=en-US).

## Facts from Epic's documentation

- Documented for Unreal Engine 5.8 and marked **Experimental**. APIs may change.
- Requires the **Unreal MCP** plugin (`ModelContextProtocol`) and **All Toolsets**.
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
