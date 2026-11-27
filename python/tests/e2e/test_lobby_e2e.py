"""The race lobby exports a garage the race accepts and builds the matching start command."""

import shutil
from pathlib import Path

import pytest

from roverloom import race_cli
from roverloom.rally import load_garage


@pytest.fixture
def browser():
    api = pytest.importorskip("playwright.sync_api")
    executable = shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("no installed browser found")
    with api.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(executable_path=executable, headless=True)
        except api.Error as error:
            pytest.skip(f"installed browser cannot start: {error.message.splitlines()[0]}")
        yield instance
        instance.close()


@pytest.mark.e2e
def test_lobby_modes_command_and_mobile_layout(browser, tmp_path):
    board = tmp_path / "board.json"
    race_cli.main(["headless", "--agent", "pursuit", "--name", "Bot", "--board", str(board)])
    lobby = tmp_path / "lobby.html"
    assert race_cli.main(["lobby", "--board", str(board), "--out", str(lobby)]) == 0
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(lobby.resolve().as_uri())
    assert "Bot" in page.locator("#board").inner_text()
    page.locator("#tires").select_option("sand")
    page.locator("#paint").select_option("gold")
    page.locator("#course").select_option("dune_sprint")
    page.get_by_role("button", name="Time Attack").click()
    command = page.locator("#command").inner_text()
    assert (
        "--course dune_sprint" in command
        and "--ghosts 1" in command
        and "--npcs 0" in command
        and "--laps 3" in command
    )
    page.get_by_role("button", name="Advanced").click()
    page.locator("#agent").select_option("external")
    assert "--agent external" in page.locator("#command").inner_text()
    assert "race_agent_example" in page.locator("#agent-command").inner_text()
    with page.expect_download() as download:
        page.get_by_role("button", name="Save garage.json").click()
    config = tmp_path / "garage.json"
    download.value.save_as(config)
    assert load_garage(config)["paint"] == "gold"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors
    evidence = Path(__file__).parents[3] / "runs/verification"
    evidence.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence / "lobby-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.screenshot(path=str(evidence / "lobby-desktop.png"), full_page=True)
    page.close()
