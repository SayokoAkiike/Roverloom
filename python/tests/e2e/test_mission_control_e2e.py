"""Drives Mission Control in a real browser, using trusted keyboard and mouse input.

Uses a browser already on the machine, and skips if there is none. To keep the evidence:
ROVERLOOM_E2E_OUT=../docs/e2e uv run pytest tests/e2e
"""

import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from roverloom.preview.server import LiveMission, make_server
from roverloom.world import load_scenario

sync_api = pytest.importorskip("playwright.sync_api")
Page = sync_api.Page
expect = sync_api.expect

OUT = Path(os.environ["ROVERLOOM_E2E_OUT"]) if os.environ.get("ROVERLOOM_E2E_OUT") else None
pytestmark = pytest.mark.e2e


def _launch(playwright):
    for channel in ("msedge", "chrome", "chromium"):
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except sync_api.Error:
            continue
    pytest.skip("no installed browser found")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        instance = _launch(playwright)
        yield instance
        instance.close()


class Harness:
    """One live mission and one browser page, recording everything the page complains about."""

    def __init__(self, browser, tmp_path: Path, request) -> None:
        self.browser, self.tmp_path = browser, tmp_path
        self.name = request.node.name
        self.problems: list[str] = []
        self.steps: list[dict] = []
        self.servers: list = []
        self.page: Page | None = None
        self.mission: LiveMission | None = None

    def open(
        self,
        scenario: str = "demo_traverse",
        agent: str = "replanner",
        speed: float = 4.0,
        width: int = 1400,
        height: int = 900,
    ) -> Page:
        mission = LiveMission(load_scenario(scenario), agent, 1, self.tmp_path / "runs", speed)
        server = make_server(mission, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        mission.start()
        self.mission, self.server = mission, server
        self.servers.append((server, mission))
        self.url = f"http://127.0.0.1:{server.server_address[1]}/"
        context = self.browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.on(
            "console",
            lambda m: self.problems.append(f"console: {m.text}") if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: self.problems.append(f"pageerror: {e}"))
        page.goto(self.url)
        expect(page.locator("#modeButton")).not_to_be_empty()
        self.page = page
        self.log("opened", scenario=scenario, agent=agent)
        return page

    def state(self) -> dict:
        assert self.page is not None
        return self.page.evaluate("fetch('/api/state').then((r) => r.json())")["control"]

    def wait(self, condition: Callable[[dict], bool], seconds: float = 20.0) -> dict:
        deadline = time.monotonic() + seconds
        current = self.state()
        while time.monotonic() < deadline:
            current = self.state()
            if condition(current):
                return current
            time.sleep(0.05)
        raise AssertionError(f"condition not met: {json.dumps(current)[:800]}")

    def log(self, step: str, **data: object) -> None:
        self.steps.append({"test": self.name, "step": step, **data})

    def shot(self, name: str) -> None:
        assert self.page is not None
        if OUT is not None:
            (OUT / "screenshots").mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=OUT / "screenshots" / f"{name}.png")
            self.log("screenshot", file=f"screenshots/{name}.png")

    def close(self) -> None:
        for server, mission in self.servers:
            server.shutdown()
            server.server_close()
            mission.stop()
        if OUT is not None:
            OUT.mkdir(parents=True, exist_ok=True)
            with (OUT / "e2e-log.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
                for step in self.steps:
                    handle.write(json.dumps(step) + "\n")
                handle.write(json.dumps({"test": self.name, "problems": self.problems}) + "\n")


@pytest.fixture
def ui(browser, tmp_path: Path, request) -> Iterator[Harness]:
    harness = Harness(browser, tmp_path, request)
    yield harness
    harness.close()


def no_problems(ui: Harness) -> None:
    assert ui.problems == []


def test_keyboard_drives_and_stops_the_rover(ui: Harness) -> None:
    page = ui.open()
    before = ui.state()["rover"]
    page.keyboard.down("KeyW")
    moving = ui.wait(lambda c: c["rover"]["x_m"] > before["x_m"] + 1.0)
    assert moving["rover"]["speed_mps"] > 0
    ui.log("forward", x=moving["rover"]["x_m"], commands=moving["comms"]["commands_received"])
    ui.shot("keyboard-driving")
    page.keyboard.up("KeyW")
    stopped = ui.wait(lambda c: abs(c["rover"]["speed_mps"]) < 0.01)
    ui.log("released", speed=stopped["rover"]["speed_mps"])

    yaw = stopped["rover"]["yaw_rad"]
    page.keyboard.down("KeyA")
    turned = ui.wait(lambda c: c["rover"]["yaw_rad"] > yaw + 0.2)
    page.keyboard.up("KeyA")
    ui.log("turned left is positive yaw", yaw=turned["rover"]["yaw_rad"])
    # Arrow keys are the same path, and Space stops everything at once.
    page.keyboard.down("ArrowUp")
    ui.wait(lambda c: c["rover"]["speed_mps"] > 0.05)
    page.keyboard.press("Space")
    ui.wait(lambda c: abs(c["rover"]["speed_mps"]) < 0.01)
    page.keyboard.up("ArrowUp")
    no_problems(ui)


def test_manual_to_agent_handover_by_key_and_by_button(ui: Harness) -> None:
    page = ui.open(scenario="science_sprint", agent="mission-planner")
    assert ui.state()["driver"] == "manual"
    expect(page.locator("#stDriver")).to_have_text("you")
    page.keyboard.press("KeyM")
    state = ui.wait(lambda c: c["driver"] == "agent" and c["decisions"])
    expect(page.locator("#stDriver")).to_have_text("mission-planner")
    ui.log("agent drives", decisions=len(state["decisions"]))
    expect(page.locator("#decisions")).to_contain_text("navigate_to")
    ui.shot("agent-driving")
    page.locator("#modeButton").click()
    ui.wait(lambda c: c["driver"] == "manual")
    # Back in manual, with no key pressed, the rover must come to rest.
    ui.wait(lambda c: abs(c["rover"]["speed_mps"]) < 0.01)
    expect(page.locator("[data-task=inspect]")).to_be_enabled()
    no_problems(ui)


def test_start_stop_restart_buttons(ui: Harness) -> None:
    page = ui.open(scenario="science_sprint", agent="mission-planner", speed=16.0)
    page.locator("#scenarioSelect").select_option("science_campaign")
    page.locator("#roverSelect").select_option("hauler_8w")
    page.locator("#agentSelect").select_option("adaptive-planner")
    page.locator("#speedSelect").select_option("8")
    page.locator("#startButton").click()
    state = ui.wait(lambda c: c["mission"]["scenario_id"] == "science_campaign")
    assert state["rover"]["rover_id"] == "hauler_8w"
    assert state["agent"] == "adaptive-planner"
    ui.log("configured", state=state["mission"]["scenario_id"])

    time.sleep(0.5)
    earlier = ui.state()["time_s"]
    assert earlier > 0
    page.locator("#resetButton").click()
    ui.wait(lambda c: c["time_s"] < earlier)

    page.locator("#stopButton").click()
    ended = ui.wait(lambda c: c["mission"]["outcome"] == "aborted" and c["saved_to"])
    assert Path(ended["saved_to"]).is_dir()
    expect(page.locator("#metricsPanel")).to_be_visible()
    expect(page.locator("#stMission")).to_have_text("aborted")
    expect(page.locator("#stopButton")).to_be_disabled()
    expect(page.locator("#modeButton")).to_be_disabled()
    expect(page.locator("[data-task=inspect]")).to_be_disabled()
    expect(page.locator("#replayLink")).to_be_visible()
    ui.shot("mission-ended")

    page.locator("#resetButton").click()
    ui.wait(lambda c: c["mission"]["outcome"] == "running")
    expect(page.locator("#stopButton")).to_be_enabled()
    no_problems(ui)


def test_keys_after_the_mission_ended_do_not_break_the_log(ui: Harness) -> None:
    from roverloom.runlog import load_run

    page = ui.open()
    page.locator("#stopButton").click()
    ended = ui.wait(lambda c: c["saved_to"])
    page.keyboard.press("KeyM")
    page.keyboard.press("KeyW")
    time.sleep(0.4)
    state = ui.state()
    assert state["driver"] == "manual" or state["mission"]["outcome"] == "aborted"
    run = load_run(Path(ended["saved_to"]))
    assert run.events[-1]["type"] == "mission_ended"
    no_problems(ui)


def test_faults_are_shown_when_they_happen(ui: Harness) -> None:
    page = ui.open(scenario="stress_blackout", agent="mission-planner", speed=8.0)
    page.keyboard.press("KeyM")
    ui.wait(lambda c: "immobilized" in c["active_faults"], seconds=30)
    expect(page.locator("#faultBanner")).to_contain_text("immobilized")
    expect(page.locator("#events")).to_contain_text("FAULT: immobilized")
    ui.log("immobilized shown")
    ui.shot("fault-immobilized")
    ui.wait(lambda c: not c["comms"]["command_link_up"], seconds=30)
    expect(page.locator("#stLink")).to_have_text("DOWN")
    expect(page.locator("#faultBanner")).to_contain_text("wheel front_left")
    ui.shot("fault-blackout-and-wheel")
    ui.log("link down shown")
    ui.wait(lambda c: c["comms"]["command_link_up"], seconds=30)
    expect(page.locator("#stLink")).to_have_text("up")
    expect(page.locator("#events")).to_contain_text("recovered: comm_blackout")
    no_problems(ui)


def test_replay_plays_and_changes_speed(ui: Harness) -> None:
    page = ui.open(scenario="science_sprint", agent="mission-planner", speed=32.0)
    page.keyboard.press("KeyM")
    ui.wait(lambda c: c["saved_to"], seconds=60)
    with page.context.expect_page() as popup:
        page.locator("#replayLink button").click()
    replay = popup.value
    replay.on("pageerror", lambda e: ui.problems.append(f"replay: {e}"))
    expect(replay.locator("#runSelect")).to_be_visible()
    slider = replay.locator("#time")
    maximum = float(slider.get_attribute("max"))
    assert maximum > 0

    def elapsed(speed: str) -> float:
        replay.locator("#replaySpeed").select_option(speed)
        slider.fill("0")
        replay.locator("#play").click()
        replay.wait_for_timeout(1000)
        replay.locator("#play").click()
        return float(slider.input_value())

    slow, fast = elapsed("1"), elapsed("32")
    ui.log("replay", slow=slow, fast=fast, maximum=maximum)
    assert slow > 0.2
    assert fast > slow * 5

    slider.fill(str(maximum))
    replay.locator("#time").dispatch_event("input")
    expect(replay.locator("#stMission")).to_have_text("success")
    expect(replay.locator("#metricsPanel")).to_be_visible()
    if OUT is not None:
        (OUT / "screenshots").mkdir(parents=True, exist_ok=True)
        replay.screenshot(path=OUT / "screenshots" / "replay-end.png")
    # Scrubbing back removes what has not happened yet.
    slider.fill("0")
    replay.locator("#time").dispatch_event("input")
    expect(replay.locator("#stMission")).to_have_text("running")
    no_problems(ui)


def test_server_loss_is_reported_and_recovers_in_the_page(ui: Harness) -> None:
    page = ui.open()
    routed = {"fail": True}

    def fail(route) -> None:
        if routed["fail"]:
            route.abort()
        else:
            route.continue_()

    page.route("**/api/state", fail)
    expect(page.locator("#errorBanner")).to_contain_text("not responding", timeout=5000)
    ui.shot("server-lost")
    routed["fail"] = False
    expect(page.locator("#errorBanner")).to_be_hidden(timeout=5000)
    # Failed fetches are logged by the browser, as expected in this test.
    ui.problems = [p for p in ui.problems if "ERR_FAILED" not in p]
    no_problems(ui)


def test_a_refused_request_is_shown_not_swallowed(ui: Harness) -> None:
    page = ui.open()
    page.route(
        "**/api/configure",
        lambda route: route.fulfill(
            status=400, content_type="application/json", body='{"error": "unknown scenario: x"}'
        ),
    )
    page.locator("#startButton").click()
    expect(page.locator("#errorBanner")).to_contain_text("unknown scenario")
    expect(page.locator("#startButton")).to_be_enabled()
    expect(page.locator("#startButton")).to_have_text("Start mission")
    ui.problems = [p for p in ui.problems if "400" not in p]
    no_problems(ui)


def test_simulation_failure_is_shown(ui: Harness) -> None:
    page = ui.open()
    assert ui.mission is not None

    def boom() -> None:
        raise RuntimeError("model exploded")

    ui.mission.session.step = boom  # type: ignore[method-assign]
    expect(page.locator("#errorBanner")).to_contain_text("model exploded", timeout=5000)
    no_problems(ui)


@pytest.mark.parametrize(
    ("width", "height"),
    [(1920, 1080), (1400, 900), (1024, 700), (768, 900), (390, 800), (320, 568)],
)
def test_layout_fits_every_window_size(ui: Harness, width: int, height: int) -> None:
    page = ui.open(width=width, height=height)
    expect(page.locator("#map")).to_be_visible()
    fits = page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    assert fits, f"sideways scrolling at {width}x{height}"
    box = page.locator("#map").bounding_box()
    assert box["width"] > 200 and box["height"] > 100
    for control in ("#modeButton", "#stopButton", "#resetButton", "#startButton"):
        page.locator(control).scroll_into_view_if_needed()
        expect(page.locator(control)).to_be_visible()
    ui.shot(f"layout-{width}x{height}")
    no_problems(ui)


def test_resizing_a_running_page_keeps_it_working(ui: Harness) -> None:
    page = ui.open()
    for size in ((1400, 900), (500, 700), (1600, 500), (1000, 800)):
        page.set_viewport_size({"width": size[0], "height": size[1]})
        page.wait_for_timeout(200)
    page.keyboard.down("KeyW")
    ui.wait(lambda c: c["rover"]["speed_mps"] > 0.05)
    page.keyboard.up("KeyW")
    no_problems(ui)


def test_focus_rules_for_keys(ui: Harness) -> None:
    page = ui.open()
    select = page.locator("#scenarioSelect")
    select.focus()
    value = select.input_value()
    page.keyboard.press("KeyR")  # Typing in a list must not restart the mission.
    time.sleep(0.3)
    assert ui.state()["time_s"] > 0
    # Choosing an option gives the keyboard back, so driving works straight away.
    select.select_option(value)
    select.dispatch_event("change")
    page.keyboard.down("KeyW")
    ui.wait(lambda c: c["rover"]["speed_mps"] > 0.05)
    page.keyboard.up("KeyW")

    # A browser shortcut is not a mission command.
    earlier = ui.wait(lambda c: c["time_s"] > 1.0)["time_s"]
    page.keyboard.press("Alt+KeyR")
    time.sleep(0.3)
    assert ui.state()["time_s"] >= earlier

    # Keys held while the window loses focus must not keep the rover driving.
    page.keyboard.down("KeyW")
    ui.wait(lambda c: c["rover"]["speed_mps"] > 0.05)
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    ui.wait(lambda c: abs(c["rover"]["speed_mps"]) < 0.01)
    page.keyboard.up("KeyW")
    no_problems(ui)


def test_mashing_keys_and_buttons_is_harmless(ui: Harness) -> None:
    page = ui.open(scenario="science_sprint", agent="mission-planner", speed=8.0)
    for _ in range(21):
        page.keyboard.press("KeyM")
    for _ in range(15):
        page.keyboard.press("KeyR")
    page.locator("#startButton").dblclick()
    for _ in range(10):
        page.locator("#modeButton").click()
    for _ in range(8):
        page.locator("#resetButton").click()
    for key in ("KeyW", "KeyA", "KeyS", "KeyD", "Space") * 6:
        page.keyboard.press(key)
    state = ui.wait(lambda c: c["mission"]["outcome"] == "running")
    assert state["driver"] in ("manual", "agent")
    assert ui.mission is not None and ui.mission.fatal_error is None
    # After all that, the controls still do what they say.
    page.locator("#stopButton").click()
    ui.wait(lambda c: c["saved_to"])
    no_problems(ui)


def test_event_history_keeps_the_readers_scroll_position(ui: Harness) -> None:
    page = ui.open(scenario="stress_blackout", agent="mission-planner", speed=32.0)
    page.keyboard.press("KeyM")
    ui.wait(lambda c: len(c["events"]) >= 25, seconds=40)
    box = page.locator("#events")
    box.evaluate("(el) => { el.scrollTop = 0; }")
    page.wait_for_timeout(600)  # Several refreshes, some with new events.
    assert box.evaluate("(el) => el.scrollTop") == 0
    box.evaluate("(el) => { el.scrollTop = el.scrollHeight; }")
    page.wait_for_timeout(300)
    at_end = box.evaluate("(el) => el.scrollHeight - el.scrollTop - el.clientHeight")
    assert at_end < 24
    no_problems(ui)


def test_status_bar_reports_the_mission_at_a_glance(ui: Harness) -> None:
    page = ui.open(scenario="science_sprint", agent="mission-planner")
    expect(page.locator("#stMission")).to_have_text("running")
    expect(page.locator("#stTime")).to_contain_text("/ 700 s")
    expect(page.locator("#stBattery")).to_contain_text("%")
    expect(page.locator("#stLink")).to_have_text("up")
    expect(page.locator("#stScience")).to_contain_text("0.0 /")
    ui.shot("mission-control")
    no_problems(ui)
