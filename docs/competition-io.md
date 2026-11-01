# Competition input and output draft

**Design only.** No online service, submission server, or Codabench competition exists, and this
has never been run on Codabench. Check the current
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
  agent.py          Defines class Agent with reset() and act()
  metadata.json     {"schema_version": 0, "name": "...", "authors": ["..."]}
```

Dependencies would be limited to those in the published container image at first.

## Scoring program input

```text
input/ref/scenarios/*.json    Hidden evaluation scenarios
input/ref/seeds.json          Hidden seeds
input/res/<scenario>/seed-<n>/   Run directories from ingestion
```

Every run directory must load with `roverloom.runlog.load_run`, which rejects modified and malformed
logs. A missing or invalid run scores 0, and the error is shown to the participant without
revealing hidden data.

## Scoring program output

`scores.json`, one key per leaderboard column:

```json
{
  "mean_score": 81.5,
  "success_rate": 0.9,
  "mean_success_time_s": 702.4,
  "mean_success_energy_wh": 145.1,
  "fault_recovery_rate": 1.0
}
```

These are the keys produced today by `roverloom.evaluate.aggregate`.

## Security requirements before running anyone else's code

The current in-process agent loading is **not safe for untrusted code**. Required before opening:

- Separate agent from simulator process, using the bridge protocol, so an agent cannot read simulator
  memory, hidden scenarios, or other participants' files. Simulator-signed logs would also be needed,
  since hashes in `run.json` detect accidents but do not prove who wrote the log.
- Container with no network, limited CPU, memory, disk, and time.
- Time limits per `act()` call, which do not exist today.
- Confirm exactly what Codabench isolates, and what its compute workers provide.
- Decide on a process for rule violations, and for publishing winning code.

## Fairness

- Fix `model_version` and `scoring_version` per competition phase.
- Use the same scenarios and seeds for all participants.
- State the authoritative backend. Lightweight and Unreal results are not comparable.
- Decide how to handle ties and floating-point differences between workers, and rerun finalists.
- Check Unreal licensing before distributing any Unreal-based evaluation.
  See [licensing-review.md](licensing-review.md).
