# Project status

The state of the project at the end of Windows verification, 2026-11-02, for whoever continues it. Measured code:
`2be6d9c`. Commits after that contain only results and documents.

## Implemented and tested on Windows and Ubuntu

| Area | State | Limit |
| --- | --- | --- |
| Mission core, faults, comms, science | Works | Unvalidated [game model](model-assumptions.md) |
| Rover Builder | Works: classes, volume, power, part rules | Limits are invented |
| Leagues and scientific study | Works: tracks, intervals, causes, pins | No held-out scenarios |
| Planners | Reactive, classical, mission, adaptive, human approval | Adaptive is a baseline, developed on these scenarios |
| Mission Control | Works, with E2E tests in Edge or Chrome | No human, Safari, phone, or touch testing |
| Local evaluator | Works, with hostile submission tests | [Not a sandbox](evaluator-safety.md). Never run on Codabench |
| Unreal contract | [Specified](unreal-contract.md), and tested with a Python stand-in | `unreal/` is a skeleton, and implements none of it |

## Not done

- `unreal/` has no terrain, bridge, or logs, and no working rover. A physics spike [failed R0 twice](results/unreal-physics-spike/README.md), on turning and on time step sensitivity. It is independent of the Mission Core. A separate [wheel model](results/unreal-wheel-model/README.md) failed 2 of 15 tests on its first attempt, both slope holds, and passed all 15 on its second, on one-wheel and two-wheel rigs. A six-wheel version found a friction defect in diagnostics. After a fix, phases A and B passed again on a third attempt. Six-wheel tests then ran against their registered criteria and failed 7 of 9, on solver convergence, overshoot from body pitch, and a motor-limited turn. [Solver diagnostics](results/unreal-wheel-model/solver-diagnostics.md) followed, with no new gated run. UE 5.8.4 and Unreal MCP are [measured on one Mac](macos-checklist.md#unreal-results-on-this-mac), with one unexplained editor crash and an [open security issue](security.md#unresolved).
- macOS is not in CI. Python results on one M4 Mac are recorded by hand in the [checklist](macos-checklist.md#results-on-this-mac).
- No real language model is connected. `cap-mock` follows fixed rules.
- No real sandbox, log signing, or Codabench run. Do not run anyone else's code.
- `LICENSE` is not selected, and EULA texts are unread. See [licensing review](licensing-review.md).

## Known problems

- **Port on macOS:** `roverloom play` fails on the measured Mac unless given `--port`, because `sharingd` holds the default 8770.
- **Cross-platform study results:** Mac and Windows differ in score, energy, and time, for an uninvestigated reason. See the [comparison](macos-checklist.md#results-on-this-mac).
- **Withdrawal rule:** it lowers achievement outside the standard range. Not tuned further, because
  the final results must stay comparable. See [results](scientific-benchmark.md#what-each-behavior-contributes).
- **`ood_long_delay`:** every planner scores 0 with 2.5 s delay and 20% loss.
- **`frugal_survey`:** `pathfinder_6w` and `hauler_8w` score 0, because the planner has no energy budgeting and the
  mission's data window opens late. This is partly a planner limit, and not only a design difference.
- **Design interventions:** on `hauler_8w`, replacing the RTG with solar panels, or using a smaller battery, changed
  no achievement on any mission. Those parts do not currently bind for that rover.
- **Benchmark independence:** all scenarios and seeds were seen during development.
- **Memory:** `design-study` defaults to one worker per logical CPU less one, and a run including it was stopped
  for low memory on this 14 GB laptop. Use `--workers 2`. `study` has the same default. Logs need about 5.5 MB per run.
- **In-process agents:** there is no time limit on `act()` unless an agent runs over the bridge.
- **Cross-platform results:** not compared byte for byte. Golden vectors differ in the last bit between Windows and
  Ubuntu, so run digests may too.
- **Autonomy League files:** measured before the final commit. See [results](results/phase3/README.md).

## Before continuing

Start with [HANDOFF.md](HANDOFF.md).

1. Follow the [macOS checklist](macos-checklist.md). Set the noreply `user.email` on the new machine.
2. Install Unreal only by the owner's decision, following [the Mac plan](mac-unreal-plan.md).
3. Write new scenarios and seeds before looking at results, if any planner claim is to be made.
