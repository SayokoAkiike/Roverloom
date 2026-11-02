# macOS checklist

**Roverloom has never run on macOS.** CI runs Windows and Ubuntu only, because macOS minutes cost ten
times as much on a private repository. Do these on the Mac, in order, and record the results.

## Setup

- [ ] Install `uv` and Git LFS. Clone, then `git lfs install --local` and `git lfs pull`.
- [ ] Set a repository-local `user.email` to the GitHub noreply address. Never commit with another.
- [ ] `cd python && uv sync --locked`. Check whether a universal lock resolves on Apple silicon.

## Python

- [ ] `uv run pytest`, including the E2E tests. Record the count, and any failure.
- [ ] `uv run ruff check . ../scripts`, `uv run ruff format --check . ../scripts`, `uv run mypy`.
- [ ] `uv run roverloom league verify`. Pins normalize line endings, so this should match.
- [ ] Compare `docs/results/phase3` with a rerun, using `--workers 2`. Then compare a run digest with Windows and Ubuntu. Floating point may differ across CPUs and libraries,
      so identical bytes are not claimed. Record whether they match.

## Things likely to differ

- [ ] `guard.py`: `RLIMIT_AS` on macOS is known to be unreliable. Check
      `test_memory_limit_is_what_stops_the_bomb` first. If it fails, record that memory is not limited.
- [ ] Multiprocessing starts with `spawn`, as on Windows. `study --workers` should behave the same.
- [ ] Paths: case-insensitive filesystems, and `/tmp` being a symbolic link to `/private/tmp`. The guard
      resolves paths, so its tests are the check.
- [ ] Browser paths in `scripts/capture_preview.py`, and Playwright's `chrome` channel.
- [ ] Keyboard: `Cmd` shortcuts must stay with the browser. The page ignores `metaKey`, which has not been
      exercised on a real Mac.
- [ ] Port 8770 may already be in use. Use `--port`.

## By hand

- [ ] Drive with a real keyboard in Safari and Chrome. Safari is not covered by any test.
- [ ] Unreal Engine is a separate step, with its own plan. See
      [unreal-production-plan.md](unreal-production-plan.md).
