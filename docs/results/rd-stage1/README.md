# Night factory Stage 1: the night user on the Mac mini, 2026-11-07

**Status: isolation of files, keys, and network verified as `rdnight`; Unreal does not run as `rdnight`. A user with no
graphical session cannot start any Unreal process on macOS, so build is the only Unreal step that passed. Stage 1
cannot start until the owner decides how the night gets a graphical session (below). No night loop has run; nothing
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

## Unreal as `rdnight`

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

## Decision needed: a graphical session for the night

| Option | What changes | Cost |
| --- | --- | --- |
| A. `rdnight` logged in to a background graphical session (fast user switching, or Screen Sharing's own-session login), then locked | A second logged-in session stays on the Mac mini; it needs rdnight's password at a login window or Screen Sharing, and Screen Sharing or login-window settings may need to list `rdnight` | Memory for a second session (not measured); keeps user isolation |
| B. Run the night as the owner, as in Stage 0 | Nothing new | Loses user isolation: the sandbox is the only file barrier, and the owner's editor settings change again |
| C. A different machine or a VM for the night | New hardware or a VM | Most isolation; a macOS VM has only a paravirtual GPU, and whether Unreal renders there is not measured |

A is the only option that keeps both isolation and the GPU. Each changes system settings or sessions, so Claude has
not tried any.

## Still open for Stage 1

- The owner's choice above, then: tests, offscreen game, MCP, and a clean stop as `rdnight`.
- Step 2: remove the night key from the owner's `authorized_keys`.
- Step 3: firewall trial for 1985 and 8558.
- Charter approval and spending caps; blind validation cases.
