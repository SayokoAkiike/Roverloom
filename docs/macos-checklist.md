# macOS setup and checklist

**All sections have run on one Mac.** Measured results are at the bottom of this file. Steps not listed there come from
documentation and from checks on Windows. Target: Apple M4 with 16 GB or 32 GB.
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

Epic's page does not list macOS 26 or 27, though the Mac may ship with one of them. Reports conflict, and none is a guarantee. One
measured combination is in [Unreal results on this Mac](#unreal-results-on-this-mac):

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

- [x] `guard.py`: macOS rejects a 1 GiB `RLIMIT_AS` with `EINVAL`, which stopped every guarded agent at startup. The limit is now 1 GiB above the process's address space at startup, and `test_memory_limit_is_what_stops_the_bomb` passes.
- [x] Multiprocessing starts with `spawn`, as on Windows. `study --workers 2` exited 0, and matched a second run.
- [x] Paths: case-insensitive filesystems, and `/tmp` being a symbolic link to `/private/tmp`. The guard resolves paths, and its tests pass.
- [ ] Browser paths in `scripts/capture_preview.py`, and Playwright's `chrome` channel. Browser tests skip if no browser exists, so a skip is not a pass.
- [ ] Keyboard: `Cmd` shortcuts must stay with the browser. The page ignores `metaKey`, which has not been exercised on a real Mac.
- [ ] Port 8770 **is** in use on the measured Mac, by the system's `sharingd`, so `roverloom play` stops with `OSError: [Errno 48]` unless given `--port`. Port 8000 is the Unreal MCP default.
- [x] Results: rerun a small case, such as `study --tracks misestimated_uncertainty --agents mission-planner,adaptive-planner --seeds 2 --out ../runs/mac-check`. Identical bytes across CPUs are not claimed. Differences are recorded below.
- [ ] Drive with a real keyboard in Safari and Chrome. Safari is not covered by any test.

## 6. Unreal prerequisites

Do not install without the owner's approval in the current conversation. See [mac-unreal-plan.md](mac-unreal-plan.md).

- An Epic Games account, and the Epic Games Launcher. Accepting the EULA is the owner's act.
- Xcode, chosen as above. Open it once, and accept its license. Run `xcode-select -p` to check the active one.
- The Metal Toolchain, a separate download: `xcodebuild -downloadComponent MetalToolchain`. `xcrun --find metal` returns a path even when it is missing. Check with `xcrun -sdk macosx metal -v`, which is what the editor runs.
- Disk: read the sizes reported by the installers first. Epic's page states no figure, and shaders and caches add more. A 256 GB Mac may need an external SSD.
- Packaging and signing: Epic's [modern Xcode page](https://dev.epicgames.com/documentation/unreal-engine/using-modern-xcode-in-unreal-engine) describes automatic signing with an Apple Developer account. Whether a free account is enough for local builds is unverified. The paid program needs the owner's approval.

## Results on this Mac

| Item | Result | Date |
| --- | --- | --- |
| Model, chip, memory, free disk | `Mac16,10`, Apple M4, 10 CPU and 10 GPU cores, 16 GiB, 663 GiB free of 926 GiB | 2026-11-02 |
| macOS, Xcode | macOS 27.0.1 (26A434). Xcode 27.2 (27B52), Metal Toolchain 27B47 | 2026-11-03 |
| Python, uv, tests passed, failed, skipped | uv 0.13.6. Python 3.13.1 and 3.14.10 each: 706 passed, 0 failed, 1 skipped | 2026-11-02 |
| ruff, mypy, `check_repo`, `league verify` | All pass on both Python versions | 2026-11-02 |
| `demo` | Exit 0. `score` on its `replanner` run exit 0 | 2026-11-02 |
| Memory limit test | Passes. `bytearray` of 2 GiB and 8 GiB gives `MemoryError`, and 64 MiB is allowed | 2026-11-02 |
| Digest compared with Windows and Ubuntu | Digests not compared. See the study comparison below | 2026-11-02 |

The skipped test covers a backslash in a zip path, which is an ordinary filename character on this platform. Browser tests ran in
Chrome. No person has driven the rover on this Mac, and Safari has not been tried.

**Study comparison,** using the command in the list above, 12 runs:

- Two runs on Python 3.13.1, and one on 3.14.10, gave identical `study_runs.csv` rows.
- Against the Windows rows in [`study_runs.csv`](results/phase3/study_runs.csv), 1 of 12 is identical. Outcome, cause, achievement, and science value match in all 12.
  Score differs in 10 rows, by at most 0.145. Energy differs in 11, by at most 4.935 Wh. Mission time differs in 4, by at most 17.5 s.
- The cause of these differences has not been investigated. Do not mix Mac and Windows runs in one comparison.

## Unreal results on this Mac

Measured 2026-11-03 on the machine above, with UE 5.8.4 (CL 58902052) from the Launcher, in a disposable project outside this
repository. Evidence stays outside Git. **This is one machine, a minimal project, and short runs.** Epic does not list macOS 27 or
Xcode 27 as supported, and these results do not change that. `Apple_SDK.json` in this engine allows Xcode up to 27.9.

| Check | Result |
| --- | --- |
| Installed size | 43 GB for the Mac platform only. The Launcher had shown 15.6 GB |
| Editor without Xcode | Fails. The editor shows "Xcode Not Found" and exits, unless started with `-nullrhi` |
| Editor without the Metal Toolchain | Not run. Its check runs `xcrun -sdk macosx metal -v`, which failed here |
| Editor on Metal | Works. Startup 41 s the first time, then about 15 s |
| New material through MCP | Compiled and rendered on a cube |
| C++ editor build | Succeeded in 20 s, with Mac SDK 27.2 and Clang 21.1.6 |
| Mac packaging | `BuildCookRun` with `-package` succeeded in 87 s, 885 MB. The `.app` ran for 25 s on Metal and loaded the C++ module |
| Mac packaging without `-package` | Reports success, but the archived `.app` has no content, and exits at startup |
| Signing | Ad hoc only. Gatekeeper rejected the build that was checked. Distribution is unverified |
| Stability | One editor crash, SIGSEGV, stack without symbols. **Cause unknown.** It did not recur in later runs |

**Rendering, in the editor, not a packaged game.** Viewport about 1014 x 545, editor in front, 900 frames from `csvprofile`, except 529
for Lumen. Nine meshes of 999,698 triangles each, about 9 million in all, with one flat-colored test scene and no scalability changes.

| Profile | FPS | Frame ms, mean / p95 | GPU ms | Process memory peak |
| --- | --- | --- | --- | --- |
| No Nanite | 25.7 | 38.9 / 46.0 | 38.4 | 5.8 GB |
| Lumen, software | 19.8 | 50.4 / 64.9 | 49.7 | 7.0 GB |
| Nanite | 51.7 | 19.3 / 26.0 | 18.7 | 5.6 GB |
| Virtual Shadow Maps | 44.4 | 22.5 / 29.3 | 22.0 | 6.5 GB |
| Nanite, Lumen, Virtual Shadow Maps | 43.0 | 23.3 / 30.4 | 22.7 | 8.3 GB |

- These numbers compare profiles on this scene only. They do not predict a Mars level, 1440p, or `Capture` quality.
- Visual quality was not judged, because the scene has nothing to judge. Virtual Shadow Maps were confirmed by setting, not by a specific visual check.
- Swap grew from 3.9 GB to 5.4 GB over the session, with other applications open. Free memory never fell below 25%, so the 10% stop rule did not trigger.

**Log messages seen at startup:**

| Message | Finding |
| --- | --- |
| `LogAutomationTest: Condition failed`, 19 times | An engine smoke test expecting English text. 0 times with `-culture=en`. Not a Mac problem |
| `GameFeatureData` rule missing | Project setting. Matters only for game feature plugins, which this project does not use |
| `idevice_id`, `Bad CPU type`, every 10 s | An x86 iOS tool without Rosetta. Not needed for Mac work |

**Not tested:** a person driving the editor, long sessions, Movie Render Queue, hardware ray tracing, MegaLights, Lumen Lite, Mesh Terrain, Landscape, and a real terrain.

