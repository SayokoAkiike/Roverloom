# Competition input and output draft

**A local mock works; nothing else exists.** `roverloom competition` runs ingestion and scoring on your
own machine. No online service, submission server, or Codabench competition exists, and this has
never been run on Codabench. Files in `competition/` are untested drafts. Check the current
[Codabench bundle documentation](https://docs.codabench.org/latest/Organizers/Benchmark_Creation/Competition-Bundle-Structure)
and [YAML reference](https://docs.codabench.org/dev/Organizers/Benchmark_Creation/Yaml-Structure/)
when implementing. Reviewed 2026-11-02.

## Why Codabench fits

A Codabench task consists of reference data, input data, a scoring program, and an ingestion program.
The official documentation says the scoring program writes `scores.json`, whose keys match leaderboard
columns. This maps well to file-based evaluation in [ADR 0002](decisions/0002-backend-neutral-contract.md).

## Planned flow

```text
Submission (agent code)      Hidden scenarios and seeds
        \                       /
    ingestion program, in an isolated container with no network
        | runs roverloom for each scenario and seed
        v
    run directories (logs and manifest)
        |
    scoring program, separate from submitted code
        | verifies, then re-scores from logs
        v
    scores.json -> leaderboard
```

## Submission format (draft)

```text
submission.zip
  agent.py          Defines the class named in metadata, with reset() and act()
  metadata.json     See schemas/submission_metadata.schema.json
  rover.json        Rover design, for Rover Design and Full Mission leagues
```

Dependencies would be limited to those in the published container image at first.

## Scoring program input

```text
input/ref/reference.json      Scenario names, seeds, and rover
input/ref/scenarios/*.json    Hidden evaluation scenarios, when present
input/res/<scenario>/seed-<n>/   Run directories from ingestion
```

Every run directory must load with `roverloom.runlog.load_run`, which rejects modified and malformed
logs. A missing or invalid run scores 0, and the error is shown to the participant without
revealing hidden data.

## Scoring program output

`scores.json`, one key per leaderboard column:

```json
{
  "mean_score": 68.03,
  "success_rate": 1.0,
  "mean_science_value": 7.35,
  "mean_time_s": 512.4,
  "mean_energy_wh": 78.7,
  "mean_collisions": 0.0,
  "runs_scored": 4,
  "runs_expected": 4
}
```

This is real output from the example submission. Leaderboard keys are in `competition/competition.yaml`.

## What the local mock does

- Validates metadata and zip contents, refusing traversal, links, compiled files, and oversized archives.
- Requires a real rover design, so that plain parameters cannot skip the budgets.
- Runs each scenario and seed with the agent in a separate process over the bridge, with a minimal
  environment, limits on time and memory, and a guard hook. A crash or hang ends that run as `agent_error`.
- Scores in a separate step, without running submitted code. Missing or modified runs score zero.

## Security requirements before running anyone else's code

**The mock is not a sandbox.** Its guard catches accidents, and [a few lines of Python defeat it](evaluator-safety.md).
Required before opening:

- Container with no network, limited CPU, memory, disk, and time, and no hidden data mounted where
  the agent runs. Simulator-signed logs would also be needed, since hashes in `run.json` detect
  accidents but do not prove who wrote the log.
- Confirm exactly what Codabench isolates, and what its compute workers provide.
- Decide on a process for rule violations, and for publishing winning code.

## Fairness

- Fix `model_version` and `scoring_version` per competition phase.
- Use the same scenarios and seeds for all participants.
- State the authoritative backend. Lightweight and Unreal results are not comparable.
- Decide how to handle ties and floating-point differences between workers, and rerun finalists.
- Check Unreal licensing before distributing any Unreal-based evaluation.
  See [licensing-review.md](licensing-review.md).
