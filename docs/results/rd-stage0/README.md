# Night factory Stage 0: environment and safety checks, 2026-11-07

**Status: Stage 0 complete on 2026-11-07, including the final integration test with the night key. Stage 1 is not
ready: the open items below come first. No night loop has run; nothing is scheduled; nothing was pushed.**
Approved by the owner on 2026-11-07: a separate night clone, a restricted night key and dispatcher, MCP on 8100,
exclusion from the owner's Unreal, and a small rendering check with the display asleep or locked. Install notes are in
[`rd/mini/README.md`](../../../rd/mini/README.md); settings in [`rd/charter.json`](../../../rd/charter.json).

Mac mini: Apple M4, 16 GB, macOS 27.0.1, UE 5.8.4. Code: `38b28d4` in the night clone. The dispatcher installed is
SHA-256 `dbe36579…2ca8`, equal to `rd/mini/dispatch.py`. The Unreal steps in the second table ran with the owner's own
key and `RD_OWNER_PRESENT_OK=1`, because the owner had used the Mac mini within `owner_idle_min_s`; the final
integration test ran with the night key alone. A session interruption after the exclusion retests left no process,
lock, or PID file behind; the final test had not started, and was run once afterwards.

## Safety boundaries tested

| Boundary | Test | Result |
| --- | --- | --- |
| OS sandbox (`sandbox-exec`, `night.sb`) | `touch` under 3 allowed and 7 protected paths; append, rename, and `mkdir` in the owner's clone | 10 of 10 as intended; the 3 attacks on the owner's clone got `Operation not permitted`. The rule for `~/Roverloom` does not catch `~/RoverloomNight` |
| Forced command | `status` with the night key | Allowed |
| Arbitrary commands | `sh -c id`, `id`, `status; id`, `status $(id)` | Refused: unknown verb, or extra arguments |
| Argument checks | Path traversal in run ids, out-of-range seconds, spaces, non-`rd/` branch, `;` in a branch, `../..` evidence | Refused |
| Git transport | Push to `repo.git` with the night key; push and fetch to the owner's `.git` | Night repository accepted; owner's repository refused, and no branch appeared there |
| PTY | `ssh -tt` with the night key | `PTY allocation request failed` |
| Port forwarding | Remote 22 and 8000; remote 8100 | 22 and 8000 `administratively prohibited`; 8100 permitted. Control: the owner's key carried the SSH banner on 22 |
| Exclusion | A stand-in process whose command line reads `…/MacOS/UnrealEditor …/Roverloom.uproject` | `game`, `build`, `test`, `editor-start` refused, naming its PID; the stand-in still ran afterwards |
| Own processes only | A PID file planted to point at a process the night did not start | `editor-stop-own` refused to signal it; the process still ran |
| Owner present | Night key `game` while the owner had used the Mac mini 605 s earlier | Refused, with nothing created |

## Unreal in the night clone

| Step | Result |
| --- | --- |
| Editor build, sandboxed | Succeeded, 47 s, binaries in the night clone |
| Automation tests, sandboxed, `-nullrhi` | 5 of 5 passed; 0 sandbox denials in the log |
| Game, launched directly from the SSH session, sandboxed, 20 s | Window rendered at 60 fps; `Chase.png` saved; normal exit; no process left; lock released |
| Evidence fetch with the night key | Logs and the shot arrived as a stream |
| Editor with MCP | Listened on `127.0.0.1:8100` only; read-only `get_current_level` and `list_toolsets` through the night tunnel; stopped by `editor-stop-own` through Unreal's normal shutdown; port closed |
| **Display asleep** (`pmset displaysleepnow`, no setting changed) | **Rendered, and uncapped:** 87 fps, GPU 10.6–10.7 ms, matching the exclusive-fullscreen baseline. The shot matched the awake one region by region. The display was woken with `caffeinate -u -t 1` |
| **Screen locked** | **Not run.** This macOS has no `CGSession`, and locking otherwise needs UI automation or a setting change, which the owner reserved |
| **Final integration test, night key only** | After waiting for the owner idle time to pass the threshold: `game rd-s0-final 20` rendered in the night clone, wrote `Chase.png` and `game.log`, exited normally through `RequestExit`, left no process, and released the lock; `fetch-evidence` brought both to the Air. No fatal error and no sandbox denial in the log. The shot's region values equal the earlier runs' |

The Mac mini's present settings already leave the screen unlocked with the display never sleeping
(`screenLock is off`, `displaysleep 0`). Nothing was changed.

## Existing environment

A baseline taken before any change was compared afterwards: the owner's clone (every file's path, size, and time, except
`Intermediate`, `DerivedDataCache`, and `.git`), `Saved/WheelSpike` and `Saved/PhysicsSpike`, the owner's Unreal log folder,
Git HEAD, status, and stash, the backup folder, launch agents, and the Claude Code processes. **All identical, except
`~/.ssh/authorized_keys`, which gained the night key's line as approved;** its original line is unchanged and a backup is
in the night area.

**Side effect, not covered by the baseline:** engine-wide Unreal files in the owner's account changed when the night
editor and build ran:
- `~/Library/Application Support/Epic/UnrealEngine/5.8/Saved/Config/MacEditor/EditorSettings.ini` lists the night project
  first among recently opened projects;
- `…/UnrealEngine/Editor/ProjectEditorRecords.json` records it;
- `…/UnrealBuildTool/Log.txt` and related logs were replaced by the night build's.

The owner's projects and data were not affected, but the editor's project list now offers the night project first. Not
reverted, pending the owner's decision.

## Failures and fixes during Stage 0

| Found | Fix |
| --- | --- |
| An empty command was refused outside the handler, with a traceback and no log entry | Parsing moved inside the handler; empty and unparsable commands are refused and logged |
| Refused Unreal calls had already created their evidence folders | Checks now run before anything is created; the 4 empty folders were removed |
| Git transport logged `exec` before checking the path, so the audit log showed two executions that never happened | `exec` is logged only after validation |
| Two of my own test scripts were wrong: zsh did not split a command variable, and a local port under 1024 could not bind | Rerun as bash with arrays and high ports; the invalid results were discarded, not counted |
| The dispatcher did not meet the project's lint rules | Restyled with the same logic (f-strings, context managers, `raise from`); still Python 3.9. Reinstalled, then the 15 night-key probes, the stand-in exclusion, and the planted PID file were run again: all as before |

## Open items before Stage 1

### 1. Credentials are readable from the sandbox (blocking)

Measured: a process under `night.sb` can read two SSH private keys in `~/.ssh`, `~/.ssh/authorized_keys`,
`~/Library/Keychains`, `~/.config`, `~/.gitconfig`, and `~/Library/Application Support/Claude`. The profile has no read or
network rules, so night code built into Unreal could read a private key and send it out. To close, in this order:
- add `(deny file-read* …)` for those paths, and any other credential folders found, to the charter's protected list
  and the profile; test that the editor, game, build, and tests still run;
- test whether `(deny network-outbound …)` except loopback lets Unreal and the build work; record what breaks;
- the strongest fix is a separate macOS user for the night, which needs the owner and an administrator. With it, file
  permissions, not only the sandbox, keep the owner's keys and clone out of reach.

### 2. Engine-wide Unreal user files are shared (should close)

The night editor and build changed files in the owner's account outside the night area:
`…/Epic/UnrealEngine/5.8/Saved/Config/MacEditor/EditorSettings.ini` (the night project is first among recent projects),
`…/Epic/UnrealEngine/Editor/ProjectEditorRecords.json`, `…/Epic/UnrealBuildTool/Log*.txt` and `.json`, and
`…/Epic/UnrealEngine/XmlConfigCache-…bin`. The shared Zen derived data cache also grew; that is a cache, and safe to share.
The game runs added nothing to the editor settings. To close: test the editor's `-userdir=` option for the night, or a
separate macOS user (item 1); and the owner decides whether to remove the night project's recent-projects entry, which
was left as it is.

### 3. Port 1985 on all interfaces (accept with conditions, or close)

Every editor and game process, the owner's and the night's, listens on `*:1985`: the UE Trace issue already open in
[security.md](../../security.md#unresolved), where what it accepts is unverified. Night runs widen the time it is open. Until
it is understood: run night Unreal only on a trusted network, check the macOS firewall state, and try disabling trace for
night runs (for example `-trace=none` or `-notrace`), confirming with `lsof` that the port is closed.

### 4. Other items

- **The Air side is not built:** the wrapper, `PreToolUse` hook, per-run settings, Air worktree, and stop watcher. The
  Director cannot run without them.
- **The night key is unencrypted on the Air,** as unattended use requires; its power is the dispatcher's verbs only.
- **Screen lock** is untested; the Mac mini already leaves the screen unlocked with the display never sleeping, a setting
  this work did not change.
- `charter.json` has `approved_by_owner: false` and no spending caps.

## Can Stage 1 start?

**Not yet.** Stage 1 runs code written at night inside Unreal. It can start when item 1 is closed and tested, item 2 is
closed or accepted by the owner, the Air side of item 4 is built and dry-run, and the owner has approved the charter,
set spending caps, and written the blind validation cases. Item 3 needs at least the trusted-network condition and a
trace check. Then Stage 1 starts by hand, within the charter's limits, with G2 run logs, gameplay, and visual tasks as
candidates.
