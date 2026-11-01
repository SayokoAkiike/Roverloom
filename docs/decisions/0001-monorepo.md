# 0001: Single repository

Status: Accepted (2026-11-02)

## Context

Unreal content, Python tooling, and shared schemas must change together while the
contract is still evolving, and the team is small.

## Decision

Keep `unreal/`, `python/`, `schemas/`, `scenarios/`, `docs/`, and `scripts/` in one
repository, with no services or separately versioned packages.

## Consequences

- A contract change and its users land in one commit.
- Python-only contributors should use `GIT_LFS_SKIP_SMUDGE=1` or partial LFS fetches
  once assets grow.
- If `python/` and `schemas/` need a separate public license or release cycle, they
  can be split out later.
