# 0005: Loopback TCP bridge for Python control

Status: Proposed, pending implementation spike (2026-11-02)

## Context

The vertical slice needs Python to command a rover in Unreal, using the same schemas as a
future lightweight simulator. Unreal MCP is an experimental editor tool. Remote Control is
Beta, and is off by default in packaged builds.

## Decision

Implement a small C++ TCP server bound to loopback, exchanging JSON Lines that conform to
`schemas/`. See [Unreal integration](../unreal-integration.md).

## Consequences

- One message format for every backend; no new build dependency.
- We maintain threading and a small protocol, and it has no authentication, so it must
  stay on loopback.
- Reconsider if a Remote Control spike proves simpler and reliable when packaged.
