# Architecture decision records

Each record states one decision, why it was made, and its consequences. Do not rewrite
accepted records. Supersede them with a new one.

| ID | Decision | Status |
| --- | --- | --- |
| [0001](0001-monorepo.md) | Single repository | Accepted |
| [0002](0002-backend-neutral-contract.md) | Backend-neutral contract and file-based evaluation | Accepted |
| [0003](0003-unreal-engine-5-8.md) | Unreal Engine 5.8 and official MCP first | Proposed, pending verification |
| [0004](0004-git-lfs.md) | Git LFS for binary assets | Accepted |
| [0005](0005-runtime-bridge.md) | Loopback TCP bridge for Python control | Implemented on the lightweight backend; Unreal pending |
| [0006](0006-mission-core-layout.md) | Mission core layout and contract extensions | Accepted |
| [0007](0007-rover-designs-compile-to-parameters.md) | Rover designs compile to parameters | Accepted |
| [0008](0008-skills-are-data-not-code.md) | Rover tasks and typed skills; plans are data, never code | Accepted |
| [0009](0009-pinned-benchmarks-and-leagues.md) | Pinned benchmarks and separate leagues | Accepted |
| [0010](0010-design-budgets-instead-of-cost-points.md) | Design classes, not cost points | Accepted |
| [0011](0011-tripwire-guard-for-local-evaluation.md) | A tripwire for local evaluation, not a sandbox | Accepted |
| [0012](0012-m4-mac-for-unreal.md) | Apple M4 Mac for Unreal development | Accepted, measured in [0013](0013-ue-5-8-4-on-macos-27.md) |
| [0013](0013-ue-5-8-4-on-macos-27.md) | UE 5.8.4 with Xcode 27.2 on macOS 27 | Proposed |
