# macOS setup and checklist

**Roverloom has never run on macOS, and every step here is unverified on a Mac.** The steps come from documentation
and from checks on Windows. Record real results at the bottom of this file. Target: Apple M4 with 16 GB or 32 GB.
Requirements were reviewed 2026-11-02, and may have changed.

## Compatibility

| Tool | Requirement | Source | Note for M4 |
| --- | --- | --- | --- |
| Claude Code | macOS 13+, 4 GB+, ARM64 supported | [Anthropic](https://code.claude.com/docs/en/setup) | Fine |
| Python packages | `uv.lock` has macOS arm64 wheels | Checked in the lock file | Install not yet run |
| UE 5.8 OS | Minimum Sonoma 14.5. Recommended latest Sequoia 15 | [Epic](https://dev.epicgames.com/documentation/unreal-engine/macos-development-requirements-for-unreal-engine?lang=en-US) | One line on that page says "Sequoia 14", which looks like a typo |
| UE 5.8 Xcode | Minimum 26.0, recommended 26.1.1. **26.4 listed as incompatible** | Epic, same page | Do not install whatever is newest without checking |
| UE 5.8 hardware | Minimum M1 or M2 by feature, 16 GB. Recommended M3, 32 GB or more | Epic, same page | 16 GB meets only the minimum |
| Lumen, software ray tracing; TSR | Apple silicon M1+ | Epic, same page | Listed as supported |
| Nanite, Virtual Shadow Maps | Apple silicon M2+, **beta** | Epic, same page | Expect problems, and measure |
| Lumen hardware ray tracing, MegaLights | Apple silicon M2+, **experimental** | Epic, same page | Do not depend on it |

### Newer macOS and Xcode

Epic's page does not list macOS 26 or 27, though the Mac may ship with one of them. Reports conflict, and none is a guarantee:

- [Forum, 5.8 on macOS 27 and Xcode 27](https://forums.unrealengine.com/t/ue5-8-unable-to-build-game-on-macos-27/2746676): Mac game builds failed at
  "Touch UBT generated tiles", and editor builds worked. Epic staff said building with **Xcode 26.6** works, which sits oddly with the 26.4
  warning, and that a fix was going into 5.8.4.
- [5.8.4 notes](https://forums.unrealengine.com/t/5-8-4-hotfix-released/2842775), October 2026: the visible item fixes the *iOS* `.app` finalize on macOS 27.
  A fix for Mac targets is not confirmed there. Test packaging early.
- [Forum, macOS 26](https://forums.unrealengine.com/t/unreal-engine-5-6-1-also-5-8-will-not-work-on-macos-26-0-xcode-26-0/2681509) and
  [Mac mini M4 report](https://forums.unrealengine.com/t/running-ue5-on-macos-26/2701073): Metal or version errors, solved for some by a newer `Apple_SDK.json` or a higher `MaxVersion`.
- Some Xcode versions can be installed side by side, and selected with `DEVELOPER_DIR`. Check which macOS each Xcode requires on Apple's site.

Before installing, record the macOS version. Then read Epic's page again, and report to the owner which Xcode you will install. Do not change the macOS version without the owner's decision.

## 1. Check the machine

Report these before installing anything:

```shell
sw_vers
uname -m
sysctl -n machdep.cpu.brand_string hw.memsize hw.ncpu
system_profiler SPDisplaysDataType | grep -E "Chipset|Metal|Total Number of Cores"
df -h ~
```

## 2. Base tools

Claude Code may need to be installed first, so that a session can guide the rest. It logs in through the browser on first run. Do not copy `~/.claude` from Windows.

```shell
curl -fsSL https://claude.ai/install.sh | bash
claude --version
```

Then install the others. Homebrew needs its own [install step](https://brew.sh) if it is missing, and may prompt for Xcode command line tools.

```shell
brew install git git-lfs gh uv
git lfs version
uv --version
```

Python is managed by `uv`. `uv run python --version` shows what was used. Final results used 3.14.7, and the project requires 3.12 or later.

## 3. Clone the private repository

Clone outside iCloud-synced folders such as Desktop and Documents, for example under `~/Developer`. Log in as the repository owner, and request no extra permissions. Never print the token.

```shell
gh auth login --git-protocol https --hostname github.com --web
gh repo view SayokoAkiike/Roverloom --json visibility,defaultBranchRef
mkdir -p ~/Developer && cd ~/Developer
gh repo clone SayokoAkiike/Roverloom
cd Roverloom
git lfs install --local
git lfs pull
git lfs ls-files | wc -l
```

Expect `"visibility":"PRIVATE"`. Check a PNG with `file docs/images/mission-control.png`: it must be image data, not an LFS pointer.

## 4. Commit identity

Local to this repository. Do not change global settings. Never commit with another address.

```shell
git config --local user.name "SayokoAkiike"
git config --local user.email "228487143+SayokoAkiike@users.noreply.github.com"
git config --local user.email
```

## 5. Python checks

```shell
cd python
uv sync --locked
uv run pytest
uv run ruff check . ../scripts
uv run ruff format --check . ../scripts
uv run mypy
uv run python ../scripts/check_repo.py
uv run roverloom league verify
uv run roverloom demo
uv run roverloom score ../runs/demo/demo_traverse/replanner/seed-1
open ../runs/demo/report.html
```

For comparison, the last Windows run had 706 passed, including one test per Markdown file. Report failures as they are. Fix code only with the owner's agreement, since core changes alter benchmark pins.

## Things likely to differ

- [ ] `guard.py`: `RLIMIT_AS` on macOS is known to be unreliable. Check `test_memory_limit_is_what_stops_the_bomb` first. If it fails, record that memory is not limited.
- [ ] Multiprocessing starts with `spawn`, as on Windows. `study --workers 2` should behave the same.
- [ ] Paths: case-insensitive filesystems, and `/tmp` being a symbolic link to `/private/tmp`. The guard resolves paths, so its tests are the check.
- [ ] Browser paths in `scripts/capture_preview.py`, and Playwright's `chrome` channel. Browser tests skip if no browser exists, so a skip is not a pass.
- [ ] Keyboard: `Cmd` shortcuts must stay with the browser. The page ignores `metaKey`, which has not been exercised on a real Mac.
- [ ] Port 8770 may already be in use. Use `--port`. Port 8000 is the Unreal MCP default.
- [ ] Results: rerun a small case, such as `study --tracks misestimated_uncertainty --agents mission-planner,adaptive-planner --seeds 2 --out ../runs/mac-check`. Identical bytes across CPUs are not claimed. Record whether digests match.
- [ ] Drive with a real keyboard in Safari and Chrome. Safari is not covered by any test.

## 6. Unreal prerequisites

Do not install without the owner's approval in the current conversation. See [mac-unreal-plan.md](mac-unreal-plan.md).

- An Epic Games account, and the Epic Games Launcher. Accepting the EULA is the owner's act.
- Xcode, chosen as above. Open it once, and accept its license. Run `xcode-select -p` to check the active one.
- Disk: read the sizes reported by the installers first. Epic's page states no figure, and shaders and caches add more. A 256 GB Mac may need an external SSD.
- Packaging and signing: Epic's [modern Xcode page](https://dev.epicgames.com/documentation/unreal-engine/using-modern-xcode-in-unreal-engine) describes automatic signing with an Apple Developer account. Whether a free account is enough for local builds is unverified. The paid program needs the owner's approval.

## Results on this Mac

Fill this in, and commit it. Nothing has been recorded yet.

| Item | Result | Date |
| --- | --- | --- |
| Model, chip, memory, free disk | | |
| macOS, Xcode | | |
| Python, uv, tests passed, failed, skipped | | |
| ruff, mypy, `check_repo`, `league verify` | | |
| `demo` | | |
| Memory limit test | | |
| Digest compared with Windows and Ubuntu | | |
