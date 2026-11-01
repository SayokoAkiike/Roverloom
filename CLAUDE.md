# Roverloom: rules for Claude Code

Read `docs/architecture.md` before structural changes. Past decisions live in
`docs/decisions/`; add an ADR rather than silently reversing one.

## Hard limits

Do not do these without an explicit request from the owner in the current
conversation:

- Change repository visibility, or delete the repository
- Sign up for paid services or cloud resources
- Install large tools (Unreal Engine, Visual Studio, GPU drivers)
- Modify anything outside this repository

Never commit Unreal Engine source or binaries, engine or Fab content without a
confirmed redistribution right, secrets, or generated build output.

## Architecture rules

- `schemas/` is the contract. Python evaluation must never depend on Unreal
  types, and missions must run on any backend.
- Contract units are SI in a right-handed frame. Convert to Unreal centimeters
  and its left-handed frame only at the Unreal boundary.
- MCP is an editor development tool, not the runtime agent interface.
- Avoid microservices and abstractions without a current user.

## Commands

Run from `python/`:

```shell
uv sync
uv run pytest
uv run ruff check . ../scripts
uv run ruff format --check . ../scripts
uv run mypy
uv run python ../scripts/check_repo.py
```

Run all of these before committing. After changing the preview, also run
`uv run python ../scripts/capture_preview.py` and look at the screenshots.

## Mission core rules

- Agents receive only `MissionBrief` and `Observation`. Never pass scenarios or `RoverState`.
- Any change to simulated behavior must increase `MODEL_VERSION`.
- Scoring changes must increase `SCORING_VERSION`.
- Models are approximations. Never describe them as validated, and report only measured numbers.
- Never add `eval`, `exec`, or LLM-generated code execution to the agent or skill path.
- Never commit evaluation scenarios.
- After changing a pinned file, rerun `uv run roverloom league verify`. Lock only deliberately.
- Label events `mars_inspired` or `stress_test`, and never attribute invented rates to NASA.

## Unreal Engine

- Target engine: UE 5.8 (see ADR 0003). Project lives in `unreal/`.
- Launch the editor before Claude Code when using Unreal MCP. The server has no
  authentication; keep it bound to loopback.
- Inspect with read-only tools first. Save or commit only after reviewing changes.
- Never report MCP or any integration as working without running it. State the
  engine version and the exact call you ran.
- The primary dev machine is a low-power integrated-GPU laptop. See
  `docs/development-environment.md`, and do not raise editor settings or claim
  visual quality or performance results without measuring them.

## Documentation

- User-facing documentation is in English.
- The README must describe only what exists today; mark everything else planned.
- Do not state license conclusions as legal advice. Link the primary source.

## Git

- Default branch is `main`. Use feature branches once CI and PRs are in regular use.
- Stage files by name and review `git status` and `git diff --cached` first.
- Lock `.uasset` and `.umap` files before editing them.
