# Autonomous R&D Director and night visual factory: design

**Status: a design, 2026-11-07. Nothing here is built, scheduled, or running.** No night clone, launch agent, key, or hook
exists yet. It adds an unattended night mode beside the present workflow, where the owner approves each step. It replaces
nothing, and every decision marked "owner" stays with the owner.

## Purpose and priorities

Two uses, in one system:

1. **A night visual factory.** In an environment separated from the owner's, it builds and changes scenes in Unreal,
   renders them, and compares screenshots and measurements, keeping what improves and discarding what does not.
2. **A Director** that, across nights, keeps physics accuracy, verification and reproducibility, visual quality, and
   gameplay moving, and proposes changes of direction with evidence.

**Current priority, set by the owner on 2026-11-07:** finish G2 formally. Run logs in the shared formats, scored by the
Python Mission Core through `check_run_contract`, come first. Model K and method D are not resumed automatically; the
Director may only propose them, with evidence.

## Why: the case it learns from

From 2026-11-03 to 2026-11-07, six research cycles on the six-wheel contact solver produced real findings and never moved
the registered gate: phase C stayed at 2 of 9, and the Unreal rig was not changed. The owner then held that research and
made the playable milestone first; a greybox G2 rover drove about three hours later. The Director should be able to
notice such a pattern, set it beside what the research was still learning, and put the choice to the owner.

## How the Director judges

**No signal stops or redirects work by itself.** The earlier draft used fixed triggers, three cycles of stagnation or
more than 40% of effort, as rules. They are now evidence inputs to a written review.

### Evidence it collects for each active theme

| Evidence | Measured as |
| --- | --- |
| Gate progress | The registered acceptance metric, before and after each cycle |
| Knowledge gained | Registered findings added; hypotheses ruled out; uncertainty that changed a pending decision; questions closed against questions opened |
| Shipped change | Whether the product, the Unreal project or the Mission Core, changed and passed its checks |
| Cost | Effort per cycle; compute cost of the thing built against its gate's limit, for example a solver's time per step |
| Dependencies | Which gates or domains wait on this theme, and whether a reversible fallback exists for them |
| Deadline | Owner-set dates in the charter, such as "G2 formally done" |
| Repetition | Whether the next proposed step resembles a recorded experiment, and what differs |

### The theme review

Each cycle, for each active theme, the Director writes a short case with three parts: what the evidence says, what
continuing would buy (the value of the next finding: would it change a decision someone must make?), and the
alternatives. It then picks one of:

| Choice | Who decides |
| --- | --- |
| Continue | Director |
| Continue with a changed method or a timebox | Director, recorded with its reason |
| Set the theme aside for the rest of the night | Director |
| Hold the theme beyond tonight, change the project's direction, resume a held theme, change architecture | **Owner**, from a written proposal with evidence and at least one reversible alternative |

**Research that learns without moving a gate can continue.** If recorded findings keep narrowing a cause, and the next
step has a named decision depending on it, continuing scores as continuing; the stagnation of the gate metric is reported,
not acted on.

### Allocation

No fixed shares. Work is ordered by:
1. owner-set deadlines (G2 now);
2. the dependency graph of the gates (a domain blocking another's gate ranks higher);
3. research need: open questions whose answer a near decision depends on;
4. a starvation check: any domain with an open gate and no progress for five nights is raised in the report, with a
   proposal.

### Ranking candidate tasks

Each specialist proposes up to three tasks with: the acceptance item served, expected effect, knowledge expected,
effort as a share of a night, risk, the machine check that will verify it, and effects on other domains. The Director
ranks with registered weights, after deadline and dependency ordering. Tasks needing a person go to the human queue.
Tasks on held themes are blocked.

### What it never does

- Edit scoring, `MODEL_VERSION`, `SCORING_VERSION`, gate thresholds, registered criteria, phase C records, finished
  experiment records, or raw research data. These paths are listed with SHA-256 hashes in the charter, checked at
  start and end of every night, and blocked by hook.
- Present a check as run when it did not run, or a person's judgment as received when it was not.

### Registration and validation of the rules

- **The present dry run is retrospective. It shows the rules can reproduce one past decision; it does not show they
  predict.** The thresholds were chosen knowing the outcome.
- Before the first night, rules, weights, and limits are written in `rd/charter.yaml` and committed by the owner. The
  Director reads the charter's commit hash into every decision record.
- **Validation on cases it has not seen:** before the charter is frozen, the owner writes three to five short case files
  from projects or periods the rules were not tuned on, including at least one where persisting paid off. A separate
  agent with no access to the charter's rationale runs the review on them. The charter is changed only by the owner,
  as a new version, never during a night.
- **Prospective check:** for each choice, the Director records what it expects and how confident it is. A later night
  scores those expectations against what happened; the calibration is reported weekly.

## The night cycle

1. **Observe:** project status, release gates, open G2 items, last metrics, ledgers, human queue, Git log since the last
   night, the last night's report.
2. **Review themes** as above.
3. **Propose:** Visual, Gameplay, Physics, Verification, and Research each propose up to three small tasks.
4. **Choose** one task; **register** its intended change, the shots and measurements that will judge it, and its
   pass criteria, in the cycle's notes, before touching anything.
5. **Implement** in the night worktree: C++, Python, render settings, a C++-spawned scene, or an editor scene through MCP.
6. **Build, launch, capture:** fixed shots and an uncapped measurement, on the Mac mini's night clone.
7. **Evaluate** against the baseline and up to three variants.
8. **Keep or discard:** if the registered criteria pass, commit to the night branch; otherwise the cycle branch is kept
   for the record and the night worktree goes back to the night branch's tip.
9. **Decide the next step:** the same theme, another domain, or stop.
10. **Morning report** on every exit path.

## Specialists

| Agent | Owns these measures | Night work allowed | Must not |
| --- | --- | --- | --- |
| Visual | GPU ms and frame p95 per profile; fixed shot set; image metrics; defect list | Greybox materials, rocks, lighting, sky, fog, cameras, render settings; MCP scene edits in the night clone | Adopt a render profile; use assets of unconfirmed license |
| Gameplay | G2 acceptance checklist; HUD; input and camera tests | HUD and camera changes; scripted drive scenarios for the game mode | Record a human play test as done |
| Verification | Tests, automation tests, golden vectors, `check_run_contract`, determinism | Run logs (G2 priority), contracts, test additions | Weaken a test to pass it |
| Physics | Phase G results; stall rate; solver time p99; penetration; NaN | Measurements of P in the night clone; phase G registration drafts | Change the drive model P, resume K or method D without the owner, re-run finished experiments |
| Research | Source log entries | Web search and reading: official documentation, engine source, papers, OSS, benchmarks; dated citations with applicability | Edit code or data; cite unread pages; upload anything |

## Environment separation

```text
MacBook Air                                            Mac mini (owner's account)
~/Roverloom                (owner's, untouched)         ~/Roverloom                 (owner's clone, Saved/, research data: untouched)
~/Roverloom-night          git worktree,                ~/RoverloomNight/
                           branch rd/night-<date>         repo.git                  bare repository, receives the night branch
rd/bin/night.sh            wrapper, limits, report        work/                     night worktree; its own unreal/Saved, Intermediate
~/.roverloom-rd/           counters, STOP, raw logs       evidence/<date>/c<n>/     shots, logs, bench output, per cycle
                                                          bin/dispatch              the only command the night key may run
                                                          unreal.lock               exclusive lock for build, game, editor
```

- **Separate clone, separate saves.** The night project lives in `~/RoverloomNight/work/unreal`, so its `Saved/`,
  `Intermediate/`, and per-project user settings are its own. The owner's `~/Roverloom` is never opened by night
  processes.
- **Shared per-user state, handled explicitly.** Both projects are named `Roverloom`, so default logs go to the same
  `~/Library/Logs/Unreal Engine/RoverloomEditor/`, where a new run rotates the owner's log. Night runs always pass
  `-abslog=` into `evidence/`. The derived data cache is shared, which is safe: it only caches.
- **MCP on another port.** The night editor starts with `-ModelContextProtocolStartServer -ModelContextProtocolPort=8100`,
  so a night client can never reach an owner's editor on 8000. The night SSH key forwards only `127.0.0.1:8100`.
- **One night key with a forced command.** A new key, used only at night, is installed in the Mac mini's
  `authorized_keys` with `command="~/RoverloomNight/bin/dispatch",permitopen="127.0.0.1:8100",no-agent-forwarding,no-X11-forwarding,no-pty`.
  `dispatch` accepts a fixed set of verbs: `status`, `lock`, `unlock`, `sync`, `build`, `test`, `game`, `bench`,
  `editor-start`, `editor-stop-own`, `shots`, `fetch-evidence`, `memory`, and `git-receive-pack` for `repo.git` only.
  Everything else is refused and logged.
- **Moving code.** The Air commits to `rd/night-<date>` and pushes to `repo.git` on the Mac mini, not to GitHub. The night
  worktree fetches from there.
- **Isolation of assets.** Maps and assets made at night go under `/Game/Night/` in the night clone only. They are LFS
  files, committed locally, never pushed until the owner decides.

## Mutual exclusion with the owner

Before every Unreal step, `dispatch` checks, in this order, and skips the step if any holds:
1. any `UnrealEditor` or `UnrealEditor-Cmd` process not started by the night (by PID file) is running;
2. `unreal.lock` is held by another night step;
3. the owner is at the Mac mini: HID idle time under 15 minutes, read from `ioreg` without administrator rights;
4. free memory below 20%, or swap grew by more than 2 GB since the night started.

**The night never stops, kills, or signals a process it did not start.** It stops only its own, by PID, and only
gracefully, as the benchmark did.

## How Unreal is driven

| Method | Used for | Why |
| --- | --- | --- |
| **C++ game modes and command-line modes** (`-RoverBench`, `-RoverShotDir`, and a planned `-RoverShotSet`) | All evaluation runs | Reproducible from source; no asset; already measured |
| **Unreal MCP** on port 8100 | Exploring a scene: placing actors, setting properties, capturing the viewport | Fast to try; results must then be written as C++, a script, or a saved night map to count |
| **Editor Python** with `-ExecutePythonScript` | Batch edits a night repeats | Versioned, reviewable |
| **`Build.sh`** for `RoverloomEditor` | Builds | The editor must be closed: the night closes only its own |

Known open questions for stage 0: whether Metal renders at full rate with the display asleep or the screen locked (an
occluded window ran at about 1.5 fps on 2026-11-07), and whether `-RenderOffscreen` works on macOS.

## Evaluation

Each cycle compares a baseline, from the night branch's tip, and up to three variants, under the same conditions.

| Kind | What | Pass rule, registered per task |
| --- | --- | --- |
| Fixed shots | Chase, mast, hazard on the greybox; later the three shots of [site-and-look-references.md](site-and-look-references.md). Fixed seed, time of day, exposure | Shots exist, same size, no black or invalid frame |
| Image metrics | Mean color per region, luminance histogram and clipped share, local contrast, a high-frequency check for grid and aliasing patterns, a difference map against the baseline with the share of changed pixels inside and outside the intended region | The intended region changed in the intended direction; the rest did not change beyond a set share |
| Performance | Exclusive fullscreen, uncapped, 1600 × 900, the `Play` candidate: GPU mean, frame mean and p95, game thread, process memory peak; one `ProfileGPU` frame | GPU no more than 0.5 ms worse unless the task declared a budget |
| Tests | `pytest` and the other repository checks; Unreal automation tests | All pass |
| Model review | A fixed rubric, applied to unlabeled, shuffled baseline and variant shots: Mars plausibility against reference notes, legibility of the rover, artifacts | Recorded as a model's judgment, never as a person's |

Capped, windowed numbers are not used: on macOS a windowed game is synchronized to the display, which hides cost (see the
[render benchmark](results/g2-greybox/render-benchmark.md)). Image metrics start with Python's standard library; adding an
image library is an owner decision.

**Kept** changes are committed to the night branch with their evidence path. **Discarded** changes stay on their cycle
branch, with their shots, so the morning report can show them, and nothing is deleted.

## Stop conditions

Checked by the wrapper before each step and by a watcher every 30 seconds, not only at the end of a cycle.

| Limit | Stage 1 value |
| --- | --- |
| Cycles | 3 |
| Wall time | 2 hours, with a hard deadline at which the night's own processes are stopped gracefully |
| Same failure | 2 occurrences of one failure signature, such as one compiler error at one place or one kind of bad frame |
| Unreal | Crash of a night process; 4 builds; 8 launches |
| Memory | Free memory under 20%, or swap growth over 2 GB |
| Spending | A per-cycle cap passed as `--max-budget-usd`, and a nightly cap, both set by the owner |
| Owner | Owner present at the Mac mini, or the owner's editor running: Unreal steps are skipped; three skips end the night |
| Manual | `~/.roverloom-rd/STOP` exists |
| Integrity | A protected file's hash changed, or a hook was bypassed |

## Settings to be written

| File | Content |
| --- | --- |
| `rd/charter.yaml` | Owner-approved rules, weights, limits, deadlines, protected paths with hashes |
| `rd/settings.json`, passed with `--settings` | Permissions: allow edits under the night worktree; deny edits to protected paths; allow `ssh rd-mini <verb>`, `git` add, commit, switch, and push to `night-mini`; deny other `git` writes, `curl`, `wget`, `scp`, `rsync`, `kill`, `sudo`, `launchctl`, package installs. `PreToolUse` hook running the same policy as code, so a wildcard cannot widen it |
| `rd/agents.json`, passed with `--agents` | The five specialists, with their tool lists |
| `rd/mcp-night.json`, passed with `--mcp-config --strict-mcp-config` | `http://127.0.0.1:8100/mcp` only |
| `rd/cycle.schema.json`, passed with `--json-schema` | The structured output each cycle must produce; a schema failure ends the night |
| `rd/bin/night.sh` | The wrapper: limits, watcher, STOP, report on every exit path |
| `~/RoverloomNight/bin/dispatch` on the Mac mini | The allowlisted verbs and the exclusion checks |

All of this is set per run. Nothing changes the global Claude Code settings, the owner's shell profile, or the owner's
clone.

## State and ledgers

| File | Content | Changed by |
| --- | --- | --- |
| `rd/charter.yaml` | Rules, limits, protected paths | Owner only |
| `rd/metrics.jsonl` | Each measurement: domain, metric, value, unit, commit, machine, engine, method, evidence path | Specialists, append only |
| `rd/ledger/experiments.jsonl` | Hypothesis, registered method, result, verdict (kept, held, rejected, inconclusive), cost, conditions to revisit | Append only; verdicts never edited |
| `rd/ledger/research.jsonl` | Question, sources with URL, date read, claim, location in the page, applicability, expiry | Research, append only |
| `rd/ledger/decisions.jsonl` | Theme reviews, the evidence, the choice, expectations with confidence, the charter hash | Director; the owner's answers recorded from the owner |
| `rd/queue/human.md` | Play tests, visual reviews, approvals | Director adds; only the owner closes |
| `rd/sessions/<date>.md` | The morning report | Director |

Rejected and held results count as results. Before proposing, a specialist searches the ledgers, and a proposal that
resembles a recorded experiment states what differs.

## Morning report

What changed and where it is; baseline and variant shots side by side; image metrics and measurements against the
baseline; tests; what was kept, discarded, and why; failures with their causes; technical findings; research entries;
theme reviews and any proposal to change direction; the human queue; what was not verified; spending and limits used;
the next three priorities.

## Dry runs

### 1. The physics research, replayed (retrospective)

A script replayed the six physics cycles through the earlier, mechanical triggers. They fired from 2026-11-04 06:33, three
calendar days and about 2.7 hours of work before the owner's actual decision. **This is not evidence of predictive
value:** the thresholds were set after the outcome was known, the replay held only physics cycles, and it did not count
what the last two cycles learned. Under the revised rules the same evidence would produce a written review, not a stop:
the gate unchanged for three cycles, no shipped change, compute cost over its limit (the 1 ms budget fully used on
stalled steps), G2 waiting on a drive model that P already provided, and a reversible fallback. Against that, the stall
analysis still had a named decision depending on it, the G1 residual proposal. The likely result is a proposal to the
owner to timebox the stall work and start G2 in parallel, which is close to, but not the same as, what was decided.

### 2. Guard policy and stop rules (Stage 1)

A second script, with no model, Unreal, SSH, or Git, applied the guard policy to 19 command and edit cases and ran the
controller against 8 scripted nights.

| Check | Result |
| --- | --- |
| Guard: protected edits, Git writes, raw SSH, kill, package installs, `launchctl` denied; own builds, commits, and pushes to `night-mini` allowed | 19 of 19 as expected, **after a fix**: the first version allowed `curl -F file=@shot.png`, an upload, because its pattern could not match an option after a word boundary. Network copy tools are now denied outright, and web research uses the web tools, which cannot upload |
| Stop rules: normal night, repeated build error, two different failures, crash, memory, time cap, owner present, four planned cycles | 8 of 8 stopped for the expected reason |
| Found by the dry run | The time cap was checked only after a cycle and overran by 5 minutes, and memory only at cycle end; both are now checked before each step and by the watcher |

### 3. A first Stage 1 night, planned but not run

| Cycle | Domain | Task | Verified by |
| --- | --- | --- | --- |
| 1 | Verification, G2 priority | A first slice of run logs: `run.json` with hashes and `telemetry.jsonl` from the pawn, checked by `check_run_contract` on the night clone | Python contract check; Unreal build; one game run |
| 2 | Visual | `Dev` profile at Scalability High, which the benchmark proposed but did not measure | Uncapped measurement; shadow presence in the three shots |
| 3 | Visual | Ground and rock material variation on the greybox, two variants against the baseline | Image metrics inside the ground region; GPU within 0.5 ms; model review |

## Rollout

| Stage | What runs | Before it starts |
| --- | --- | --- |
| 0. Setup checks, with the owner present | Create the night clone and key; test `dispatch`, the lock, the exclusion checks, `-abslog`, MCP on 8100, rendering with the display asleep and with the screen locked | **Owner approves** creating the clone, the key, and the files on the Mac mini |
| 1. Night factory, limited | 3 cycles, 2 hours, local commits on the night branch, Unreal in the night clone; started by the owner by hand, not scheduled | Charter v1 committed by the owner; blind-case validation done |
| 2. Scheduled nights | A launch agent on the Air at a fixed hour | **Owner approves** the launch agent and caffeinate settings |
| 3. Wider limits | More cycles, longer windows, more domains | Owner review of at least five Stage 1 nights |

## Decisions for the owner

- Approve the charter: rules, weights, limits, deadlines, protected paths.
- Spending caps per cycle and per night.
- Stage 0: the night clone, the forced-command key, and the dispatcher on the Mac mini.
- Whether the Mac mini's display may stay awake, and the screen unlocked, at night, if Stage 0 shows rendering needs it.
- Whether an image library may be added for SSIM and similar metrics.
- Two to five blind validation cases.
