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
| Skill calls and plans | Fixed skill list and strict schema; model text is parsed, never executed | Only a mock model exists |
| Mission Control | Only published scenario, rover, and agent choices; bodies always read | Local programs can still control it |
| Mock submissions | Safe zip extraction, file type check, separate process, minimal environment, time and memory limits, guard hook | **Not a sandbox**: [a few lines of Python defeat the guard](evaluator-safety.md) |
| Leagues | Pinned hashes; private seeds left out of shareable files; CSV formula escaping | Run directories still contain seeds |

## Unresolved

- [ ] No sandbox for untrusted agents, so do not run agents from people you do not trust.
- [ ] No time limit per `act()` for in-process agents. A hung agent hangs the run. Bridge agents have limits.
- [ ] Information boundaries prevent accidents, not deliberate cheating in the same process.
- [ ] Logs are not signed.
- [ ] Declared dependency licenses were listed, and a vulnerability check was run once. See
      [licensing review](licensing-review.md). Neither is continuous, and neither replaces a legal review.
- [ ] Generated viewer HTML embeds scenario text and is designed to escape it, but has not been
      independently reviewed. Only open reports you generated.
- [ ] Unreal bridge and Unreal MCP, when added, will need their own review. Epic's MCP server has no
      authentication.
- [ ] **UE Trace listens on all interfaces.** A Development `.app` from `unreal/` listens on `*:1985`, measured on
      macOS with UE 5.8.4. The editor did too. No network setting or engine file has been changed. What the port
      accepts, and whether Shipping builds open it, are unverified. Decide before any distribution or public
      release. Until then, do not run these builds on untrusted networks.
- [ ] `scripts/check_repo.py` does not detect the `SecurityToken` that `AndroidFileServer` writes. That plugin is
      disabled in `unreal/`, and [the checklist](macos-checklist.md#unreal-results-on-this-mac) has the details.
- [ ] Licensing questions in [licensing-review.md](licensing-review.md) remain open, including the
      unread Unreal and Fab EULA texts.

## Reporting

The repository has been public since 2026-11-06. No public reporting process exists yet; one must be added before
release.

## Never commit

Credentials, private evaluation scenarios, or assets without redistribution rights. The check at
`scripts/check_repo.py` catches common mistakes only. It does not replace reviewing what you commit.
