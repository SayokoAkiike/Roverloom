# Night factory Stage 1: the night user on the Mac mini, 2026-11-07

**Status: as `rdnight`, with its own graphical session (option A, a temporary trial), build, 5 of 5 automation tests,
a 20 s offscreen game with a screenshot, and MCP start, a read-only call, and a clean stop all passed. Without a
graphical session no Unreal process starts. File, key, and network isolation verified. No night loop has run; nothing
is scheduled; the firewall is unchanged; nothing was pushed to GitHub.**

Plan: [`docs/rd-stage1-isolation-plan.md`](../../rd-stage1-isolation-plan.md). Owner steps:
[`rd/mini/OWNER-STEPS.md`](../../../rd/mini/OWNER-STEPS.md). Stage 0: [`../rd-stage0/README.md`](../rd-stage0/README.md).

Mac mini: Apple M4, 16 GB, macOS 27.0.1, UE 5.8.4 (APFS clone at `/Users/Shared/UE_5.8-night`). Night code: `2555cc7`,
pushed from the Air's night clone to `rdnight`'s `repo.git` with the night key. All checks below ran over SSH with the
setup key (expires 2026-11-08 23:59) unless the night key is named; Unreal steps used `RD_OWNER_PRESENT_OK=1` because
the owner was at the Mac mini.

## The night user

Created by the owner with `create-night-user.sh` (step 1). Checked as `rdnight`:

| Check | Result |
| --- | --- |
| Identity | uid 601, gid 601 `rdnight`; groups `everyone`, `localaccounts`, `com.apple.access_ssh`, `_lpoperator`, and the owner's Public-folder share group (which nests `everyone`); not `staff`, not `admin` |
| Home | `/Users/rdnight` 700 with the standard `everyone deny delete` ACL; `.ssh` 700; `authorized_keys` 600, owner `rdnight` |
| Keys | Night key: forced command, `restrict`, `permitopen="127.0.0.1:8100"`. Setup key: `expiry-time="202611082359"` |
| `sudo -n true` | Refused: a password is required |

## Access to the owner's files, as `rdnight`

All refused with `Permission denied`: the owner's home (not even listable), `.ssh` and the private key, `Library/Keychains`
and `login.keychain-db`, `.claude` and `.claude.json`, `~/Roverloom` and `unreal/Saved`, the backup
`~/Roverloom-backup-20261107`, the Stage 0 `~/RoverloomNight`, the owner's engine, `Library/Application Support/Epic`,
`Documents`, `Desktop`, `Public`. Writes refused into both engine copies and `/Users/Shared/rdnight-setup`. Reading the
night engine copy works.

Shared places a non-admin user still sees: `/tmp` has world-writable folders made by the owner's tools (`/tmp/.dotnet`,
`/tmp/Zen_*_Startup`); `ps` shows every user's command lines; `memory_pressure` and the owner's idle time are readable,
which the dispatcher needs.

## Sandbox profile as `rdnight`

Installing the night area showed two gaps in the profile, closed before any Unreal step:

- sshd runs the forced command through the user's shell, which reads `~/.zshenv`; a sandboxed process writing it would
  run code outside the sandbox at the next dispatcher call.
- The dispatcher runs Git in `work/` outside the sandbox; a sandboxed process writing `work/.git/config` (for example
  `core.fsmonitor`) or hooks, or swapping `work/`, would do the same.

Now: `mini.write_protected` adds `work/.git`, `logs`, `run`, `~/.config/git`; a new `mini.write_protected_files` list
denies, as literals, the shell startup files, `~/.gitconfig`, and the entries of the night root and `work/`. The
dispatcher also runs Git with `core.fsmonitor=false` and `core.hooksPath=/dev/null`.

Probes (`evidence/sandbox-probes/20261107-095823/results.tsv` on the Mac mini), each its own exit code; no existing file
was opened for writing, and nothing that existed before was renamed or removed:

| Probe | Result |
| --- | --- |
| Create 10 shell and Git startup files in the home | 10 of 10 refused, `Operation not permitted` (the sandbox) |
| Create `work/`; new files in `bin`, `logs`, `run`, `repo.git/hooks`, `~/.ssh`, both `/Users/Shared` folders; `mkdir ~/Library/LaunchAgents` | All refused by the sandbox |
| Rename a protected clone and root, write its `.git/config` (stand-ins inside the probe folder, same rules) | Refused; a normal file in the stand-in clone was allowed |
| Read `~/.ssh/authorized_keys`, the setup folder | Refused by the sandbox; the engine copy is readable |
| Outbound to 1.1.1.1 and to Tailscale's 100.100.100.100 | Refused; unsandboxed controls connected |
| Outbound to the Mac mini's own addresses (loopback, LAN, Tailscale) | Allowed: SBPL's `localhost` means this host's addresses. These reach the same local services as loopback, not another machine |
| Write in evidence | Allowed |

## Night key and Git transport, as `rdnight`

`status` with the night key works; `id` is refused (`unknown verb`). The Air's night clone pushed `rd/stage1-check` to
`repo.git` through `git-receive-pack`. The Air's Git LFS pre-push hook first tried `git-lfs-transfer`, which the
dispatcher refused; `rd/night/mini.sh push <rd/branch>` now pushes to that one URL with the hook skipped, and refuses
other branches (6 tests). `dispatch.py sync` checked out `2555cc7` in a clone made for `rdnight`.

## Unreal as `rdnight`, without a graphical session

| Step | Result |
| --- | --- |
| Editor build, sandboxed | First run failed: UBT tried to create `/Users/Shared/UE_5.8-night/Epic`, refused by the sandbox. A new user has no `~/Library/Application Support`, and .NET then returns an empty folder. After creating it: **succeeded, 56 s** |
| Automation tests, `UnrealEditor.app`, `-nullrhi` | **Hung**: no log line in 15 minutes, CPU 0%. The main thread waits in `NSApplication run`; stdout shows an XPC failure for `ClientCallsAuxiliary`. `launchctl managername` is `Background`: no graphical session |
| Automation tests, `UnrealEditor-Cmd`, `-nullrhi` | **Hung the same way**; it links AppKit too. Ignored SIGINT and was stopped with SIGKILL after 420 s |
| Offscreen game, MCP editor | Not run: both start the same binary |

So on this macOS every Unreal process needs a graphical session of its user. Stage 0 worked because the owner is logged
in at the Mac mini and an SSH session of the same user can reach that session.

The timeout also exposed a dispatcher fault: after SIGINT the editor exited, but the dispatcher had not reaped it, so
the zombie stayed in `ps`, and the later SIGTERM got `EPERM` and was logged as an error. Lock and PID files were cleared
and no process was left. `stop_gracefully` now reaps its own children, treats `EPERM` on a zombie group as exited, and
escalates SIGINT, SIGTERM, SIGKILL (3 tests with throwaway children).

## The owner's environment afterwards

Read with the owner's key: `~/Roverloom` at `0f7b2f6`, clean, `stash@{0}` kept; no file in `unreal/Saved` changed since
09:30; `authorized_keys` hash unchanged (`4e66b733…`, still holding the night key line until step 2); the owner's engine
and the engine copy unchanged (03:59). No Unreal or Zen process of either user running. The only new files outside
`rdnight`'s home were two stack samples in `/tmp` from this check; one was kept as evidence, both removed by name.

## Options considered for a graphical session

| Option | What changes | Cost |
| --- | --- | --- |
| A. `rdnight` logged in to its own graphical session alongside the owner's | A second logged-in session | Memory for a second session; keeps user isolation |
| B. Run the night as the owner, as in Stage 0 | Nothing new | Loses user isolation |
| C. A different machine or a VM | New hardware or a VM | A macOS VM has only a paravirtual GPU; not measured |

The owner chose A for a trial.

## Option A trial: `rdnight` with its own graphical session

How the session was made. Screen Sharing, given `rdnight`'s name and password, showed the owner's existing desktop and
offered no session of its own; the Mac mini's Screen Sharing logs show one continuous connection since 05:15 and no
new authentication, so the Air most likely reused the owner's connection (not proven). The owner then set `rdnight`'s
`IsHidden` to 0, locked the screen, and used fast user switching to log `rdnight` in; the owner's session kept running
behind it. Checks from the Air: `launchctl print gui/601` shows `type = login`, created by `loginwindow`; Finder, Dock,
and SystemUIServer run as `rdnight`; `who` lists `rdnight` on the console; Tailscale ping and SSH kept working.
OneDrive, installed in `/Applications`, started in `rdnight`'s session as a login item.

Unreal steps, through the dispatcher (setup key, `RD_OWNER_PRESENT_OK=1`), sandboxed:

| Step | Result |
| --- | --- |
| Automation tests | First run 4 of 5: `Frames.GoldenVectors` checked its 14 cases, then failed on an error logged during it by Unreal's UDP message bus, whose multicast send to `230.0.0.1:6666` the sandbox refused. The bus also bound `0.0.0.0` and joined multicast on the LAN and Tailscale interfaces. The dispatcher now passes `-ini:Engine:[/Script/UdpMessaging.UdpMessagingSettings]:EnableTransport=False` to every Unreal run. **Rerun: 5 of 5 passed**, no message-bus lines, 1 min 23 s |
| Offscreen game, `-RenderOffscreen`, 1600 × 900, 20 s | **Rendered**: 81.7 fps, frame p95 14.09 ms, GPU 10.97 ms (ProfileGPU frame 11.52 ms); `Chase.png` shows the rover, terrain, shadows, and HUD; exit code 0; fetched to the Air with the night key's `fetch-evidence` |
| Editor with MCP, `-RenderOffscreen` | MCP listened on `127.0.0.1:8100` only, after 25 s. Through the night key's tunnel: `initialize`, `tools/list` (3 meta tools), `list_toolsets` (19), and `call_tool` `SceneTools.get_current_level` → `/Temp/Untitled_1`; the editor log records the one `Dispatching toolset tool` line. `editor-stop-own` with the night key: `exited`; ports 8100 and 1985 closed; `run/` empty |

Other listeners while the editor ran, all `rdnight`'s and on every interface: the editor's trace control port `*:1985`,
UnrealTraceServer `*:1981` and `*:1989`, and `rdnight`'s own Zen `*:8558`. UnrealTraceServer and Zen outlive the
editor briefly and then exited by themselves; none was left. Firewall step 3 must cover UnrealTraceServer too. What
happens when the owner's Zen already holds 8558 is not tested; the dispatcher refuses while an owner Unreal process runs,
but Zen can outlive it.

Memory, sampled every 10 s from the Air, 11:51–12:00 (16 GB Mac mini, owner's apps open): free 47–50% between runs,
**lowest 28%** during the game and the MCP editor (the charter's stop line is 20%); swap 2,809 → 2,892 MB (+83 MB);
Unreal's resident size at most 2.5 GB in the samples. The 10 s sampling can miss short peaks.

## Locked, and in the background

Same dispatcher steps, once per condition, memory sampled every 5 s. A: `rdnight`'s screen locked by the owner, its
session on the console. B: the owner switched back with fast user switching; `rdnight` stayed logged in behind
(`IOConsoleUsers`: `csmm_19` on the console, `rdnight` not). This macOS has no `CGSSessionScreenIsLocked` key, so the
lock in A is the owner's report, not a measurement.

| | A: locked | B: background |
| --- | --- | --- |
| Automation tests | 5 of 5 | 5 of 5 |
| Offscreen game, first 10 s | 82.2 fps, p95 13.79 ms, GPU 11.30 ms | 87.1 fps, p95 12.39 ms, GPU 10.75 ms |
| Screenshot | Saved | Saved; checked by eye: rover, terrain, shadows, HUD |
| MCP | `127.0.0.1:8100` after 20 s; `get_current_level` answered; `editor-stop-own` `exited`; port closed | Same |
| Memory: lowest free, swap change, Unreal peak in samples | 27%, +625 MB, 1.95 GB | 38%, 0 MB, 2.25 GB |
| Tailscale ping, owner SSH | 12.6 ms, ok | 12.9 ms, ok |

Neither condition slowed rendering; B was the fastest run measured as `rdnight`.

## Microsoft separation, as `rdnight`

Read-only, printing names, counts, and booleans only. At its first login, three machine-wide Microsoft launch agents
(`com.microsoft.update.agent`, `com.microsoft.OneDriveStandaloneUpdater`, `com.microsoft.SyncReporter`) loaded into
`rdnight`'s session, and `OneDrive Sync Service /silentConfig` started; it listened on `[::1]` only. No account was
configured (empty `settings`), no `CloudStorage` sync folder existed, `rdnight`'s keychain held no Microsoft item, and
the Mac mini has no MDM enrollment or Platform SSO. The updater keeps a telemetry cache, so contact with Microsoft's
update and telemetry service is possible. `rdnight` now has per-user launchd overrides disabling the three agents, and
its OneDrive process was ended; machine-wide agents and the owner's OneDrive were not touched. The charter forbids
Microsoft and employer sign-in and sync, and the dispatcher refuses Unreal steps while `OneDrive`, `Microsoft
AutoUpdate`, `Microsoft Update Assistant`, or `SyncReporter` runs as the night user; it does not cover other Microsoft
apps, processes started mid-run, or root daemons. This lowers the risk; it does not prove separation, which also
depends on machine and tenant settings.

## Still open for Stage 1

- The trial session: log `rdnight` out and set `IsHidden` back to 1 (owner). How the night gets a graphical session
  unattended is a separate decision: the trial does not provide one after a logout or restart.
- At `rdnight`'s next login: check that no Microsoft agent or OneDrive process starts again.
- Step 2 done 2026-11-07: the night key's line removed (backup kept); owner login works, the night key is refused for
  the owner and accepted for `rdnight`.
- Step 3: firewall trial for 1985, 8558, 1981, and 1989.
- Memory headroom: 28% free at the lowest with the owner's apps open; decide whether nights need the owner's apps closed
  or a lower `min_free_memory_pct` margin is acceptable.
- Charter approval and spending caps; blind validation cases.
