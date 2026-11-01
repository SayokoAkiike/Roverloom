"""Checks the preview end to end in a real headless browser, and saves screenshots.

Requires Microsoft Edge or Google Chrome. The live check presses real key events in the page,
confirms that the server received them, and confirms that the rover moved.

Run from python/: uv run python ../scripts/capture_preview.py --out ../docs/images
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from roverloom.contract import repo_root
from roverloom.preview.server import LiveMission, make_server
from roverloom.runner import compare_agents
from roverloom.world import load_scenario

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google-chrome",
    "chromium",
    "microsoft-edge",
)


def find_browser() -> str:
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    sys.exit("No headless browser was found.")


def screenshot(browser: str, url: str, path: Path, wait_ms: int) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                f"--user-data-dir={profile}", "--window-size=1400,1020",
                f"--virtual-time-budget={wait_ms}", f"--screenshot={path}", url,
            ],
            check=False, capture_output=True, timeout=wait_ms / 1000 + 60,
        )  # fmt: skip
    if not path.is_file() or path.stat().st_size < 10_000:
        sys.exit(f"Screenshot failed: {path}")


def capture_report(browser: str, out: Path, work: Path) -> None:
    from roverloom.preview.report import write_report
    from roverloom.runlog import load_run

    comparison = compare_agents(
        ["demo_traverse", "boulder_gap"], ["waypoint", "reactive", "replanner"], [1, 2, 3], work
    )
    runs = [
        (key, load_run(result.directory, trusted=True))
        for key, result in comparison.results.items()
    ]
    report = write_report(comparison.rows, runs, work / "report.html")
    url = report.as_uri() + "?find=demo_traverse/replanner&at=0.72"
    screenshot(browser, url, out / "replay-demo-traverse.png", 4000)
    url = report.as_uri() + "?find=boulder_gap/replanner&at=1"
    screenshot(browser, url, out / "replay-boulder-gap.png", 4000)


def capture_live(browser: str, out: Path, work: Path) -> None:
    mission = LiveMission(load_scenario("demo_traverse"), "replanner", 1, work / "live", speed=50.0)
    server = make_server(mission, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mission.start()
    port = server.server_address[1]
    # Headless virtual time passes faster than wall time, hence the high simulation speed.
    keys = "KeyW:12000,KeyA:2500,KeyW:12000"
    try:
        screenshot(
            browser,
            f"http://127.0.0.1:{port}/?keys={keys}",
            out / "manual-driving.png",
            30000,
        )
        state = mission.snapshot()
    finally:
        server.shutdown()
        server.server_close()
        mission.stop()
    print(f"Live page: commands={state['commands']} x={state['x']} y={state['y']} t={state['t']}")
    if state["source"] != "manual" or state["commands"] < 5 or abs(state["x"]) < 2:
        sys.exit("Key presses in the page did not drive the rover.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(repo_root() / "docs" / "images"))
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    browser = find_browser()
    with tempfile.TemporaryDirectory() as work_dir:
        work = Path(work_dir)
        capture_report(browser, out, work / "report")
        capture_live(browser, out, work)
    print(f"Saved screenshots to {out}")


if __name__ == "__main__":
    main()
