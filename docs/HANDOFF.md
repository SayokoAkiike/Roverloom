# Handoff

Start here if you have no memory of this project. It is written so that a new Claude Code session, on a new
Mac, needs nothing from earlier conversations. **The documents on GitHub `main` are the source of truth.**

State at handoff, 2026-11-02: Windows development ended. Measured code is `2be6d9c`. Later commits contain only
results and documents. **`unreal/` holds only a C++ skeleton.** The Python project now runs on macOS. See the [checklist results](macos-checklist.md#results-on-this-mac).

| Next | Document |
| --- | --- |
| Set up the Mac | [macos-checklist.md](macos-checklist.md) |
| Build the 3D demo | [mac-unreal-plan.md](mac-unreal-plan.md) |
| First prompt for Claude Code on the Mac | [mac-first-prompt.md](mac-first-prompt.md) |
| Working rules | [CLAUDE.md](../CLAUDE.md) |
| Current problems | [project-status.md](project-status.md) |

## Purpose and vision

Roverloom is a planetary robotics simulation and autonomy competition platform, intended to become open source
and to host competitions online. It combines:

- a realistic Mars environment in Unreal Engine, which is the next priority
- rover design by participants, and manual driving
- autonomous agents, including code-as-policy style agents through typed skills
- fault injection, communication delay, mission evaluation, replay, and benchmarks

The owner wants a platform researchers and robotics developers can trust and extend, not only a demo that looks
good. Visual quality and physical plausibility are judged separately, and passing one says nothing about the other.

Later ideas, none of which have been started, and none of which should begin without a request from the owner:

- open source release, and an online competition on Codabench or similar
- a real language model behind the existing `LanguageModel` interface, which is optional
- reuse of participants' rover designs. The [`provenance`](../schemas/provenance.schema.json) metadata format exists, but a public registry does not
- configurable rovers, day and night, and terrain properties in Unreal. See the [roadmap](roadmap.md)

## What exists

Details and limits are in [project-status.md](project-status.md) and the README table.

| Works on Windows and Ubuntu | Does not exist, or is unverified |
| --- | --- |
| Mission core: 2.5D fixed-step model, faults, delay, loss, noise, science, data windows | Unreal project, 3D physics, 3D rendering |
| Rover Builder, three standard rovers, Pareto analysis | Unreal MCP connection |
| Agents: reactive, classical, mission, adaptive with ablations, human approval, mock code-as-policy | A real language model |
| Seven typed skills. Plans are data, never code | Running LLM-generated code. This is prohibited |
| Three leagues, pinned benchmark, private seed injection, scientific study | Held-out scenarios and seeds |
| Logs, replay, scoring from files alone | Real sandbox, log signing, Codabench run, online service |
| Mission Control in a browser, with E2E tests | Tests by a person, or in Safari, or by touch |
| Bridge protocol v1, frame conversions, golden vectors, conformance checks, stand-in backend | C++ implementation of any of these |
| | `LICENSE` is unselected, and EULA texts are unread |

## Unreal and Python responsibilities

[unreal-contract.md](unreal-contract.md) is authoritative. In short:

| Area | Python | Unreal |
| --- | --- | --- |
| Mission rules, faults, science | Reference implementation | Reimplements from the same scenario files |
| Scoring | The only scorer, from files | Never scores |
| Agents | All of them, including the SDK | None. Human input enters through the same `Action` path |
| Terrain | Heightfield from parameters | Landscape, mapped from `terrain_id` |
| Physics | Kinematic | Its own, with its own `model_version` |
| Rendering, cameras | Debug 2D map only | Everything visual |
| Logs | Reads and checks them | Writes the same formats |

Results are never comparable across backends. The 2D preview is not an early version of the Unreal renderer.

## Main contracts

| Thing | Where | Note |
| --- | --- | --- |
| Agent API | [`agents/sdk.py`](../python/src/roverloom/agents/sdk.py), [tutorial](tutorials/custom-agent.md) | `Agent.reset(brief, seed)`, `Agent.act(observation) -> Action` |
| Messages | [`action`](../schemas/action.schema.json), [`observation`](../schemas/observation.schema.json), [`mission_brief`](../schemas/mission_brief.schema.json) | Agents never receive scenarios or `RoverState` |
| Logs | [`telemetry`](../schemas/telemetry.schema.json), [`event`](../schemas/event.schema.json), [`command_record`](../schemas/command_record.schema.json), [`decision`](../schemas/decision.schema.json), [`run_manifest`](../schemas/run_manifest.schema.json) | A run directory has `run.json`, `metrics.json`, inputs, and JSONL logs. `run.json` holds their hashes |
| Definitions | [`scenario`](../schemas/scenario.schema.json), [`mission`](../schemas/mission.schema.json), [`terrain`](../schemas/terrain.schema.json), [`rover`](../schemas/rover.schema.json), [`rover_design`](../schemas/rover_design.schema.json) | A design compiles to `rover` parameters, including wheel geometry |
| Bridge | [`bridge.py`](../python/src/roverloom/bridge.py), [transcript](../schemas/conformance/bridge_transcript.jsonl) | Loopback TCP, JSON Lines, `PROTOCOL_VERSION = 1`. The simulator listens |
| Frames | [`frames.py`](../python/src/roverloom/frames.py), [golden vectors](../schemas/conformance/frame_vectors.json) | Contract: SI, right-handed, ENU, `[x, y, z, w]`. Unreal: `(100x, -100y, 100z)` cm |
| Conformance | [`conformance.py`](../python/src/roverloom/conformance.py) | `check_run_contract(run_dir)` works on any backend's logs |
| Safety | [`command.py`](../python/src/roverloom/command.py) | The watchdog commands zero velocity after 2 s without an accepted command |
| Versions | [api-compatibility.md](api-compatibility.md) | `kinematic-0.3`, `score-0.3`, `builder-0.2`, benchmark 2.0.0, `schema_version` 0 |

## Design decisions

The records are in [decisions/](decisions/README.md). Add a new one rather than reversing one silently.

- **Contract first.** `schemas/` joins backends, and evaluation reads files, not simulators ([0002](decisions/0002-backend-neutral-contract.md)).
- **Single input path.** Keyboard, agents, and approvals produce the same `Action`, through `CommandRouter`.
- **MCP is an editor tool.** Runtime control is the TCP bridge, because MCP is experimental, serial on the game thread, and unauthenticated ([0005](decisions/0005-runtime-bridge.md)).
- **Skills are data** ([0008](decisions/0008-skills-are-data-not-code.md)). `eval`, `exec`, and generated code stay out of the agent path.
- **Hash-pinned benchmarks** ([0009](decisions/0009-pinned-benchmarks-and-leagues.md)). Changing core or agent source fails `league verify`.
- **Design classes, not cost points** ([0010](decisions/0010-design-budgets-instead-of-cost-points.md)). Cost is never converted into score.
- **The guard is a tripwire** ([0011](decisions/0011-tripwire-guard-for-local-evaluation.md)). It is an audit hook in the same process, with a documented bypass.
- **Replay is kinematic.** It plays poses from logs, and does not prove determinism.
- **Mac for Unreal** ([0012](decisions/0012-m4-mac-for-unreal.md)). UE 5.8 from the Launcher, no custom engine ([0003](decisions/0003-unreal-engine-5-8.md), still proposed).
- **Few moving parts.** No microservices, plugin framework, or frontend framework until something needs them.

## Verified commands

Run from `python/`. **"Verified" below means on Windows and Ubuntu only.**

| Command | How it was checked |
| --- | --- |
| `uv sync --locked`, `uv run pytest`, `ruff check`, `ruff format --check`, `mypy`, `check_repo.py` | CI, on every push |
| `uv run roverloom demo`, `score`, `replay`, `benchmark`, `league verify`, `competition examples/submission` | CI |
| `league run --league rover_design`, and a small `study` | CI |
| The 15 non-interactive commands in the README | Fresh clone of `2be6d9c` on Windows, all exit 0 |
| `league run --league full_mission`, `design-study --workers 2`, `study --workers 2` | Once each on Windows, exit 0 |
| `uv run roverloom play` | Only through browser E2E tests |

## Tests and CI

- Local Windows run at handoff: 706 passed. The count grew from 702 because new Markdown files add tests. Last measured CI, run `41395488270`: Windows 702 passed, Ubuntu 701 passed with 1 skipped. See the last CI run on `main` for later commits.
- CI runs Windows and Ubuntu, and not macOS, whose minutes on private repositories cost ten times as much.
- Use `--workers 2` on `study` and `design-study`. Their default of one worker per logical CPU less one coincided with a run being stopped for low memory.

## Competition safety and reproducibility

- **Never run code from people you do not trust.** No sandbox exists. See [evaluator-safety.md](evaluator-safety.md).
- Do not launch a Codabench competition, and never commit evaluation scenarios or private seeds.
- Agents must not receive the true map, future faults, or private evaluation data. `test_study.py` checks this by behavior.
- Same inputs give identical logs **on the same platform**. Golden vectors differ in the last bit between Windows and
  Ubuntu, so byte equality across platforms is not claimed. Do not expect Mac digests to match without checking.
- Real-time Unreal runs do not reproduce, and must not be used for rankings. Deterministic stepping in Chaos is unproven.
- Rates and severities are invented. Label events `mars_inspired` or `stress_test`, and never attribute them to NASA.

## Research results and limits

Data is in [results/phase3](results/phase3/README.md), and analysis in [scientific-benchmark.md](scientific-benchmark.md).
On these scenarios and seeds, on an unvalidated game model:

| Track | `adaptive` minus `mission`, achievement | 95% interval |
| --- | --- | --- |
| `standard` | 0.00, all ties | 0.00 to 0.00 |
| `stress` | -5.64 | -12.57 to +0.96 |
| `out_of_distribution` | -5.38 | -8.86 to -2.17 |
| `misestimated_uncertainty` | +46.08 | +37.96 to +53.36 |

Replanning carries the gain, and withdrawal causes the loss. **This is not a held-out evaluation:** every scenario and
seed was seen during development. It says nothing about real rovers. No novelty is claimed, and related work has not been reviewed.

## Known problems and technical debt

[project-status.md](project-status.md#known-problems) lists the behavior and benchmark problems. Others worth knowing:

- **Phase names collide.** "Phase 2" and "Phase 3" in conversation and in `results/phase3` mean completed Python work.
  The [roadmap](roadmap.md) uses Phases 1 to 5 for future Unreal work.
- **Older Unreal plans predate the contract.** Where they disagree, [unreal-contract.md](unreal-contract.md) wins. For example,
  [vertical-slice-plan.md](vertical-slice-plan.md) describes `actions.jsonl` at 20 Hz, while logs are in fact `commands.jsonl`.
- **Terrain is not shared yet.** Lightweight and Unreal terrain with one `terrain_id` differ. Replaying a Python log on a real
  Mars Landscape needs a shared heightmap, or it will show the rover floating or buried. See the plan.
- **Telemetry lacks wheel detail.** `failed_wheels` is the only per-wheel field, and 3D replay needs more.
- **Logs are large**, about 5.5 MB per run, and there is no compression or retention tool.
- **No time limit on in-process agents.** `act()` can hang unless the agent runs over the bridge.
- **Autonomy League result files** came from code with uncommitted changes, and have not been reconfirmed.

## Local data

Nothing below is needed to resume work, except optionally the archive. **Nothing was deleted from Windows.**

| Item | Size | Class | Decision |
| --- | --- | --- | --- |
| `runs/study`, `runs/design-study`, `runs/league/full_mission` | 11, 2.4, 1.4 GB | Final results | Summaries are in Git. Evidence archive below. Full logs stay on Windows |
| `runs/final` | Small | Exit codes, memory samples, logs | In the archive. Summarized in the results README |
| `runs/p3`, `runs/p3_*.txt` | 1.9 GB | Superseded, from commit `512f6de` with uncommitted changes | Do not move. Kept on Windows only |
| `runs/demo` | 91 MB | Reproducible | Do not move. `uv run roverloom demo` rewrites it |
| `python/.venv`, tool caches, `__pycache__` | 188 MB and small | Windows-specific | Do not move. `uv sync` recreates them |
| Assets outside Git | None | | No Unreal, Fab, or terrain data has been downloaded |
| Secrets | None found in the repository or archive | `check_repo.py`, and a pattern scan | GitHub and Claude logins stay in each machine's own store. Log in again on the Mac |
| Claude Code transcripts, `~/.claude` | 18 MB for the last session | May hold anything shown in a session | Do not move. See below |

**Audit of the final runs:** all 1830 have `run.json` with commit `2be6d9c`, `git_dirty: false`, versions, seed, and input hashes,
plus `metrics.json`, inputs, and logs. All log hashes were recomputed, with 0 mismatches. Committed result files match `runs/`.

**Evidence archive,** outside the repository and outside Git, on the Windows machine:

```text
C:\Users\sakii\Roverloom-migration\roverloom-phase3-evidence-2be6d9c.tar.gz         23 MB
C:\Users\sakii\Roverloom-migration\roverloom-phase3-evidence-2be6d9c.tar.gz.sha256
SHA-256 a1250d647de89d513b3738f46ff7b055f82312d045f4ce2472819207404808d0
```

It holds everything above except telemetry and command logs, which it keeps only for 24 runs, seed 1000 of `mission-planner` and
`adaptive-planner`. It also holds the memory monitor script. It passed extraction, and a check of all 12776 files. A few of its logs
contain the Windows user path, and nothing else of concern. Copy it by AirDrop or external drive. It is optional for development.
On the Mac, place it outside the repository:

```shell
shasum -a 256 -c roverloom-phase3-evidence-2be6d9c.tar.gz.sha256
tar xzf roverloom-phase3-evidence-2be6d9c.tar.gz
cd roverloom-phase3-evidence-2be6d9c && shasum -a 256 -c --quiet SHA256SUMS
```

**If the Windows machine will be erased,** the full logs are lost unless the owner copies `runs/` to a drive first. The archive's hashes
can still check a rerun on the same platform at commit `2be6d9c`.

## Claude Code sessions

Checked 2026-11-02 against [Manage sessions](https://code.claude.com/docs/en/sessions):

- Transcripts are local, at `~/.claude/projects/<project>/<session-id>.jsonl`, where `<project>` comes from the working directory path.
- **No official way to move sessions between machines was found.** [An open community request](https://github.com/anthropics/claude-code/issues/27473)
  describes the same gap. Third-party tools and hand edits exist. They are unverified, and not recommended here.
- The format is internal and changes between versions. `claude --resume <transcript-path>` is documented, but Windows to macOS is not.
- Transcripts age out after 30 days by default (`cleanupPeriodDays`). `/export` writes readable text, for the owner's own reference.

**Decision: do not migrate history.** Transcripts and `~/.claude` are not copied, so no credentials or stray output travel with them.
The decisions, plans, and constraints from those conversations are recorded here and in the linked documents.

## Standing rules from the owner

[CLAUDE.md](../CLAUDE.md) has the technical rules. These also apply until the owner changes them:

- Keep the repository **private**. Do not change visibility or delete it.
- No paid services or subscriptions, without explicit approval. This includes Git LFS data packs, the paid Apple Developer Program, and cloud GPUs.
- No large installs, without approval in the current conversation. Never force-push without explicit approval.
- Do not access or change any other organization or repository. Request no extra GitHub permissions.
- Never print tokens. Do not change global Git settings. Commit only with the noreply address.
- Never present unverified features as finished, unimplemented 3D physics as existing, or results as real-rover accuracy.
- The owner works in Japanese. Repository documents are in English.

## Mac priorities

Follow [mac-unreal-plan.md](mac-unreal-plan.md). The goal is an Unreal Engine 3D demo in which a six-wheeled rover drives across
realistic Martian terrain, operated by a person and by a Python agent.
