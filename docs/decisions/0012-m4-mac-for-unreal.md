# 0012: Apple M4 Mac for Unreal development

Status: Accepted by the owner, not yet tried (2026-11-02)

## Context

The Windows laptop has an integrated GPU and about 14 GB of memory, and was judged unsuitable for high-quality work. The owner chose to continue
on an Apple M4 Mac with 16 GB or 32 GB. This replaces the machine options in [graphics strategy](../graphics-strategy.md) for now.

Epic lists 16 GB as the minimum, and 32 GB as recommended, for UE 5.8 on macOS. On Apple silicon, it lists Nanite and Virtual Shadow Maps as beta,
and hardware ray tracing and MegaLights as experimental. Unreal MCP documentation does not state macOS support.

## Decision

Do Unreal development on the Mac, starting from a fresh clone. Keep separate `Dev` and `Capture` profiles, following
[the Mac plan](../mac-unreal-plan.md), so that editor limits do not lower final quality.

## Consequences

- Every Mac result must be measured. No Unreal or Python behavior on macOS has been observed yet.
- CI stays on Windows and Ubuntu, so macOS and Unreal results are recorded by hand.
- Packaged builds for Windows, which a future competition may need, are not addressed here.
- If the measured look or speed falls short, a separate machine is the owner's decision.
