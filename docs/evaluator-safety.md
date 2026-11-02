# Evaluator safety

**The local evaluator is not an isolation boundary.** Never use it on code from someone you do not
trust, and do not build a public service on it. It exists to test the submission format and the
scoring flow. Reviewed 2026-11-02. No external security review has been done.

## Why the guard is not a sandbox

Submissions run in a separate process with [`roverloom.guard`](../python/src/roverloom/guard.py). The
guard is a Python audit hook, and
[Python's documentation](https://docs.python.org/3/library/sys.html#sys.addaudithook) states that such
hooks are not suitable for containing malicious code. They run in the same process as the code they
watch. `test_guard_is_not_a_sandbox_a_few_lines_of_python_defeat_it` shows a three-line bypass that
reads a file outside the submission. That test exists so nobody can mistake the guard for isolation.

## What is tested

From [test_evaluator_safety.py](../python/tests/test_evaluator_safety.py). Refusal tests have a positive
control: the mission must run normally, and the agent itself must observe the guard's own exception.
Without this control, an agent that failed to start would have looked like a successful refusal, and
that is what happened in the first version of these tests.

| Case | Behavior | Enforced by |
| --- | --- | --- |
| Crash, hard exit, or `SystemExit` in `act()` | `agent_error` | Bridge |
| Invalid Python, or a missing class | `agent_error` | Bridge |
| A slow reply | `agent_error` | Time limit per reply |
| Many replies, each within the limit | `agent_error` | Total thinking budget, 300 s |
| Trickling a reply a byte at a time | `agent_error` | The limit covers the whole message |
| Non-JSON, wrong types, NaN, infinity, extra fields | `agent_error` | Schema and strict parser |
| A reply larger than 1 MiB | `agent_error` | Line limit |
| Speed beyond the rover's limit | Clamped and logged | Command router |
| Traversal, links, or compiled files in a zip | Refused before running | Extraction |
| Missing or malformed metadata | Refused before running | Schema |
| Plain rover parameters, or a design over budget | Refused before running | Builder |
| Memory over 1 GiB (on macOS, 1 GiB more address space than at startup) | `MemoryError` in the agent | Job object or `RLIMIT_AS` |
| CPU over 600 s, or files over 16 MiB (POSIX only) | Process ends | `rlimit` |
| Reading reference data, scenarios, terrain, or results | Refused | Guard |
| Writing outside the submission | Refused | Guard |
| Connecting anywhere but the simulator | Refused | Guard |
| Spawning a process, `os.system`, `ctypes` | Refused | Guard, and the job's process limit on Windows |
| Hidden seed, scenario ID, values, or fault times | Not in any message received | Differential and canary tests |
| The same submission, twice | Identical logs and scores | Hash comparison |

A failed run scores what it had sent before failing. A run that crashed at the start scores zero.

## Known gaps

- **Isolation:** agents can defeat the guard, as shown above. No container, no user separation.
- **Limits differ by platform:** the CPU and file size limits apply on POSIX only, and the process limit
  on Windows only. Only the Windows and Linux paths run in CI, and macOS results are recorded by hand in
  the [checklist](macos-checklist.md). macOS rejects a 1 GiB `RLIMIT_AS`, because each process already
  maps hundreds of GiB, so its limit is measured from startup and counts address space, not physical memory.
- **Log integrity:** hashes detect accidents and simple edits. Anyone can recompute them, so logs do
  not prove what produced them. In the real design, the agent must have no write access to them.
- **Derived seed:** an agent receives a hash of the run's seed. Hashing a small seed can be reversed by
  guessing, so use large random seeds.
- **Timing:** thinking time depends on machine load, so a borderline agent may pass or fail.
- **Codabench:** never run there. `competition/competition.yaml` is an untested draft.

## Required before running anyone else's code

1. A container or virtual machine per submission: no network, limited CPU, memory, disk, and time.
2. Hidden data not mounted where the submission runs. The simulator runs outside it.
3. Scoring in a separate container, with logs written only by the simulator, and signed.
4. A confirmed understanding of what Codabench compute workers isolate.
5. An external security review.
