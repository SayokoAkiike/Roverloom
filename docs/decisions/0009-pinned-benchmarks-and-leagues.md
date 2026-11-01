# 0009: Pinned benchmarks and separate leagues

Status: Accepted (2026-11-02)

## Context

Comparing agents and comparing rovers are different questions, and results must not silently mix
across code changes.

## Decision

- Three leagues: Autonomy, Rover Design, and Full Mission.
- A benchmark file pins versions and hashes of scenarios, terrains, rovers, and built-in agent source.
  A mismatch stops the run.
- Hashes use parsed JSON and normalized line endings, so they match across platforms.
- Private seeds are injected by file, and do not appear in shareable result files.

## Consequences

Editing `agents/sdk.py` or a scenario requires a deliberate lock. Pinning a source file is coarser than
pinning behavior: a comment change also requires a lock, which errs toward safety.
