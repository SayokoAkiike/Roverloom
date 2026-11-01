# Security notes

Status of the current local-only software. Reviewed 2026-11-02. **No external security review has
been done.**

## What exists

| Area | Protection | Limit |
| --- | --- | --- |
| Preview server | Loopback only; Host and Origin checks; JSON content type; body size limit; schema-checked commands | No authentication; another local program can control it |
| Bridge | Refuses non-loopback addresses; line length limit; schema-checked messages | No authentication; for local use |
| Run logs | Strict parser; SHA-256 per file; ordering and schema checks | Detects accidents and simple edits, not forgery: anyone can recompute hashes |
| Configuration | Schema validation and semantic checks; NaN and duplicate keys rejected | Validity does not prove a mission is solvable |
| Agent loading | Explicit user action only | **Runs the file's code with your permissions** |
| Skill plans | Fixed skill list and strict schema; no code execution | No planner is connected |

## Unresolved

- [ ] No sandbox for untrusted agents, so do not run agents from people you do not trust.
- [ ] No time limit per `act()`. A hung in-process agent hangs the run.
- [ ] Information boundaries prevent accidents, not deliberate cheating in the same process.
- [ ] Logs are not signed.
- [ ] A dependency vulnerability and license audit has not been run.
- [ ] Generated viewer HTML embeds scenario text and is designed to escape it, but has not been
      independently reviewed. Only open reports you generated.
- [ ] Unreal bridge and Unreal MCP, when added, will need their own review. Epic's MCP server has no
      authentication.
- [ ] Licensing questions in [licensing-review.md](licensing-review.md) remain open, including the
      unread Unreal and Fab EULA texts.

## Reporting

The repository is private. A public reporting process must be added before release.

## Never commit

Credentials, private evaluation scenarios, or assets without redistribution rights. The check at
`scripts/check_repo.py` catches common mistakes only. It does not replace reviewing what you commit.
