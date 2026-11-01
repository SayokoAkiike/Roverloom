# 0003: Unreal Engine 5.8 and official MCP first

Status: Proposed, pending installation and verification (2026-11-02)

## Context

Epic documents the official Unreal MCP plugin for UE 5.8, released June 2026 with
hotfix 5.8.4 listed at review time. 5.8 also adds Lumen Lite, useful on the current
low-power machine, and Mesh Terrain, which is reported as experimental. Forum users
say 5.8 may be the last major UE5 release, which is unconfirmed by Epic.

## Decision

Target UE 5.8 with the Launcher build, and no custom engine. Use official MCP as the
editor automation path. See [Unreal MCP](../unreal-mcp.md) for alternatives.

## Consequences

- MCP is experimental, and must not be a runtime or build dependency.
- Terrain approach is decided by a timed spike in Phase 1. Default is Landscape unless
  Mesh Terrain's overhangs prove worth its experimental risk.
- Accept this record only after the engine runs and MCP verification passes.
