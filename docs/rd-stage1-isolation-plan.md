# Night factory: isolation plan for Stage 1

**Status, 2026-11-07: approved by the owner; in progress.** Done: the engine clone, the night user's script and keys
staged, the Air side built and tested in fake mode. Waiting for the owner: creating the user, removing the night key
from the owner's account, and the firewall, in [`rd/mini/OWNER-STEPS.md`](../rd/mini/OWNER-STEPS.md). No night has run. Stage 0 is recorded in [results/rd-stage0](results/rd-stage0/README.md);
the design in [autonomous-rd-director.md](autonomous-rd-director.md).

## What the checks after Stage 0 measured

All on the Mac mini, in the night area, with temporary sandbox profiles in `/tmp` (since removed); the installed
profile was not changed. Evidence is under `~/RoverloomNight/evidence/rd-s1-probe-*`.

| Question | Result |
| --- | --- |
| Can night processes read the owner's credentials today? | **Yes**, under the installed profile: two SSH private keys in `~/.ssh`, `~/Library/Keychains`, `~/.config`, `~/.gitconfig`, Claude's data |
| Does a `deny file-read*` rule stop that? | Yes: the private key, `.gitconfig`, Keychains, and the owner's clone became unreadable; the engine stayed readable |
| Does a `deny network-outbound` rule, except loopback, work? | Yes: a connection to an outside address was refused, and loopback was allowed |
| Can the sandbox allow only loopback binds, or one port? | **No.** `allow network-bind (local ip "localhost:*")` also allowed `0.0.0.0`; rules naming a port (`localhost:8100`, `*:8100`) allowed nothing |
| Can it refuse inbound connections from the network? | **No.** With `deny network-inbound` except localhost, the MacBook Air still connected over Tailscale |
| Under "deny all binds", what happens? | Port 1985 disappears and the game renders, but MCP cannot listen, and Unreal's Zen cache server cannot start, so derived data is not cached |
| Does `-notracethreading` stop port 1985? | **No.** TraceLog's control port binds `INADDR_ANY` in `TraceLog/Private/Trace/Detail/Apple/AppleTrace.cpp`, with no option for the address |
| Can a game render with no window? | **Yes:** `-RenderOffscreen`, from the SSH session, 1280 × 720, 97.9 fps uncapped, GPU 9.35 ms, a correct screenshot with the HUD. Not yet tried from a user with no graphical session |

## Facts about the Mac mini that shape the plan

| Fact | Consequence |
| --- | --- |
| One user, an administrator; `sudo` needs the owner's password | Every system step below is the owner's, run in Terminal through Screen Sharing |
| FileVault off | A new user needs no unlock token |
| Owner's home `drwxr-x---`, group `staff`; `~/Roverloom` is 755, `~/.config` 755, `~/.gitconfig` 644; `~/Library` and `~/.ssh` 700, private keys 600 | A new user **in `staff`** could read the owner's clone, `.config`, and `.gitconfig`. The night user needs its own primary group, and the owner's home is then closed to it with no change to the owner's permissions |
| SSH login is limited to the group `com.apple.access_ssh`, which nests `admin` (inferred from the group's UUID) | A standard night user can log in only after the owner adds it under Remote Login |
| The engine is inside the owner's home | The night user cannot reach it; it needs its own copy, 43 GB, with 555 GB free |
| Application Firewall off | Ports 1985 (TraceLog) and 8558 (Zen) of any Unreal process, the owner's included, accept connections from the network |

## Plan

### A. A separate macOS user for the night (recommended first)

The operating system, not only the sandbox, then keeps the owner's keys, Keychain, Claude data, clone, research data,
and Unreal user files out of reach, and the night gets its own `~/Library`, so the shared editor settings stop changing.

| Step | Who, and how | Check afterwards |
| --- | --- | --- |
| 1. Create a group `rdnight` and a standard user `rdnight` with it as primary group; no admin | Owner: `sudo sysadminctl -addUser rdnight …` and `sudo dscl` for the group and `PrimaryGroupID`; a long random password kept by the owner | `id rdnight`; `dseditgroup -o checkmember -m rdnight staff` says no; as `rdnight`, `ls ~<owner>` is refused |
| 2. Copy the engine to a path the night can read but not write, for example `/Users/Shared/UE_5.8-night`, owned by the owner | Owner or Claude with the owner's key: `ditto` | As `rdnight`: build, tests, and an offscreen game run; a write into the copy is refused |
| 3. Allow `rdnight` to log in over SSH | Owner: Remote Login, "Only these users", add `rdnight` | The night key logs in as `rdnight`; the owner's login is unchanged |
| 4. Move the night area to `/Users/rdnight/RoverloomNight`, with the dispatcher, charter, and profile; the night key's forced-command line in `rdnight`'s `authorized_keys` | Claude, as `rdnight` with the owner present | Stage 0's key and exclusion tests, repeated once as `rdnight` |
| 5. Remove the night key from the owner's `authorized_keys`, restoring the backup | Owner, or Claude with approval | `authorized_keys` hash equals the Stage 0 baseline |
| 6. Keep the sandbox as a second layer: writes denied as now, reads of anything outside the night user's home and the engine copy denied, outbound network to loopback only | Claude, after review | Probes as above; build, tests, game, editor, MCP all run |
| 7. Retire `~/RoverloomNight` in the owner's account, after the move is verified | Owner decides | — |

**Open question for step 4:** whether `-RenderOffscreen` renders for a user with **no graphical session**. If not, the
night user needs a background login session (fast user switching), which changes the login window and Screen Sharing's
choices, and is a further owner decision. Exclusion from the owner's Unreal must then also look at processes of both
users; the dispatcher's `ps` check already sees all users' processes.

### B. Port 1985 and Zen's 8558

The sandbox cannot close them without breaking MCP and the cache. Options, for the owner:

| Option | Effect | Cost |
| --- | --- | --- |
| **Application Firewall on, Unreal and Zen set to block incoming** | Closes 1985 and 8558 to the network for the owner's and the night's processes; loopback is unaffected, so MCP over the SSH tunnel and local tools still work | A system setting; check that SSH and Screen Sharing, which are system services, and Tailscale still connect |
| A `pf` rule blocking 1985 and 8558 except on `lo0` | Same, by port | Needs a persistent `pf` anchor and a launch daemon; more to maintain |
| Accept on a trusted network | No change | The exposure in [security.md](security.md#unresolved) stays, for longer each night |

### C. Shared Unreal user files

Resolved by A for the future. The night project's entry in the owner's recently opened projects stays until the owner
decides to remove it. The shared Zen cache will no longer be shared once the night has its own user.

## Effects on what the owner uses

| Area | Effect of A | Effect of B (firewall) |
| --- | --- | --- |
| Owner's Unreal | None; the engine is copied, not moved | Remote trace connections refused; local Unreal Insights and MCP through loopback unaffected |
| SSH | Owner's login unchanged; `rdnight` added to the allowed users; the night key leaves the owner's account | System services allowed; to be checked |
| Screen Sharing | Unchanged with offscreen rendering. With a background session, the login window lists a second user | To be checked |
| Tailscale | Unchanged | To be checked |
| Disk | 43 GB for the engine copy, about 1 GB for the night area, the night user's own derived data | — |

## Before Stage 1

1. The owner approves A, steps 1–3 and 5, and runs the `sudo` steps.
2. Claude runs step 4 and 6 and repeats Stage 0's tests once as `rdnight`, including an offscreen render with no
   graphical session.
3. The owner chooses an option in B.
4. The Air side is built: wrapper, hook, worktree, watcher; and the owner approves the charter and spending caps.

## Progress after approval, 2026-11-07

| Item | State |
| --- | --- |
| Engine for the night | **Done:** `/Users/Shared/UE_5.8-night`, an APFS clone (`cp -c`) of the owner's engine. 265,174 files; a hash over every file's size, mode, and path equals the original's, as do the main binaries' hashes; 149 MB of disk used, not 43 GB; the original unchanged. Owned by the owner, so the night user can read but not write it. Sharing the original instead would have needed traversal of the owner's home, exposing its world-readable files |
| Night user script | **Staged** in `/Users/Shared/rdnight-setup/` with the two public keys; `rd/mini/create-night-user.sh`. Run by the owner |
| Night area for the night user | `rd/mini/install-night-area.sh`, run as `rdnight`; renders `night.sb` from the charter. A test render found and fixed a template bug that broke the profile |
| Air side | **Built:** `rd/night/`; 35 tests pass in fake mode, covering the hook policy and every stop rule; the Air sandbox keeps Claude Code logged in while refusing the owner's other SSH keys and writes to the owner's clone. Not run against a model |
| Billing | The Air uses a claude.ai login; `ANTHROPIC_API_KEY` is not set. Caps compare with Claude Code's list-price estimate, not billing, and stay unset until the owner sets them |
| Firewall | Procedure with an automatic 15-minute revert, in `OWNER-STEPS.md`. Not run |

Residual risks found while building:
- **The Air-side Keychain cannot be denied** to the night's Claude Code process: Claude Code's login is there, and
  denying it logged Claude Code out. Other Keychain items normally need the creating app or a confirmation that no one
  can give at night.
- The hook does not stop a program such as `python3` from writing where the sandbox allows; the sandbox, not the hook,
  protects the owner's files.
- Any user's `ps` shows other users' command lines on macOS; the night user can see the owner's process arguments.
