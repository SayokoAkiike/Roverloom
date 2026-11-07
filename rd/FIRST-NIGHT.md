# First night: what the owner approves, and when it may start

Proposal, not approved. The charter is [`charter.json`](charter.json); the wrapper is [`night/night.py`](night/night.py);
Stage 1 results are in [`docs/results/rd-stage1/README.md`](../docs/results/rd-stage1/README.md).

## Charter values still open

| Key | Now | Proposed | Why |
| --- | --- | --- | --- |
| `approved_by_owner` | `false` | `true`, set by the owner | The night refuses to start without it; the charter is a protected path the night cannot edit |
| `night.usd_per_cycle` | `null` | 5 | A guard on Claude Code's list-price estimate (`--max-budget-usd`), not a bill: the Air uses a claude.ai subscription, whose usage limits and charges are separate. The first night measures the real estimates; adjust after it |
| `night.usd_per_night` | `null` | 12 | As above; below 3 × 5 so one runaway cycle cannot be followed by two more |
| `evaluation.perf_mode` | exclusive fullscreen, uncapped | offscreen 1600 × 900, uncapped | Nights render with `-RenderOffscreen` (81.7 fps, GPU 10.97 ms measured as `rdnight`); comparisons must use the same mode |
| `mini.min_free_memory_pct` | 20 | 25 | Lowest measured was 28% with the owner's apps open; 25 stops a night before the owner's work slows |

Unchanged and to be confirmed: 3 cycles, 120 minutes, the same failure twice stops, at most 4 builds and 8 Unreal
launches, domains Verification, Visual, Gameplay; Physics limited to measuring drive model P and drafting proposals; the
`forbidden` list, including the Microsoft and employer-account rules; the protected paths.

## Conditions to start the first night

1. `rdnight` logged in with its own graphical session and locked; no owner Unreal process running.
2. Old night key removed from the owner's account (done 2026-11-07).
3. Firewall step done, or the owner accepts 1981, 1985, 1989, and 8558 reachable on the tailnet and LAN for that night.
4. No Microsoft process as `rdnight` (the dispatcher refuses otherwise).
5. Charter approved with both caps set.
6. The Air on power and kept awake; started once by hand: `/usr/bin/python3 rd/night/night.py`. No launchd.
7. The next morning: the report in `rd/sessions/`, the night branch's commits, and the evidence, reviewed together.

## What each cycle records

Domain, task, registered checks and their result, evidence files (logs, screenshots), commits on the night branch,
minutes, the estimated cost, and the failure signature. A cycle whose checks did not run or did not pass is not counted
as done. Nothing reaches GitHub; the only transfer is `rd/night/mini.sh push` to the night repository on the Mac mini.

GLM and OpenCode are out of scope for the first night.
