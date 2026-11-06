# Night wrapper on the MacBook Air

Runs the Director's cycles within the limits in [`../charter.json`](../charter.json). Design:
[`docs/autonomous-rd-director.md`](../../docs/autonomous-rd-director.md). Not scheduled; never started automatically.

## Files

| File | Role |
| --- | --- |
| `night.py` | The wrapper: preflight, lock, worktree, cycles, watcher (STOP, time, Mac mini memory), counters, report, local commit |
| `hook.py` | `PreToolUse` hook: writes only inside the night worktree, never to protected paths; Bash limited to listed programs, with no shell operators; Git without push, merge, reset, config, or forced options |
| `settings.json` | Passed with `--settings`: tool permissions and the hook |
| `agents.json` | Passed with `--agents`: the Visual, Gameplay, Verification, Physics, and Research specialists |
| `cycle.schema.json` | Passed with `--json-schema`: what each cycle must return |
| `cycle-prompt.md` | The Director's instructions for one cycle |
| `mcp-night.json` | The night MCP server, through the night tunnel's local port |
| `air.sb` | Sandbox for the Claude Code process: no writes to the owner's clone, `~/.ssh`, shell and Git configuration, launch agents; no reads of SSH keys other than the night key, or of GitHub CLI tokens |
| `mini.sh` | The only way to the Mac mini: one dispatcher verb over the night key |

## One-time setup on the Air (done 2026-11-07)

- `~/RoverloomNightAir/repo`: the night's own clone of the owner's local clone, made with `--no-hardlinks`; its push URL
  is set to an invalid value, so it cannot push to the owner's clone.
- `~/.roverloom-rd/local.json` (mode 600, not in Git): `mini_host`, `mini_user`, `night_key`, `mcp_local_port`.
- `~/.ssh/id_ed25519_rdnight` (night key) and `~/.ssh/id_ed25519_rdsetup` (setup key, expires on the Mac mini).

## Commands

```shell
/usr/bin/python3 rd/night/night.py --check     # preflight only
touch ~/.roverloom-rd/STOP                      # stops a running night within one watcher interval
```

A real night refuses to start until `rd/charter.json` has `approved_by_owner: true` and both spending caps set. Tests:
`uv run pytest tests/test_rd_night.py` from `python/`.

## Billing

The Air is logged in to Claude Code with claude.ai, not an API key. The caps are compared with Claude Code's own
list-price estimate (`--max-budget-usd`, `total_cost_usd`), which third-party reports say may not match subscription
usage; they are a guard, not a bill. The wrapper removes `ANTHROPIC_API_KEY` from every cycle, so a stray key cannot
move a night to API billing.
