"""Offline garage exports a loadout the rally actually accepts."""

import shutil
from pathlib import Path

import pytest

from roverloom.rally import load_garage, stats


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
def test_garage_select_export_and_mobile_layout(browser, tmp_path):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    source = Path(__file__).parents[2] / "src/roverloom/preview/garage.html"
    page.goto(source.resolve().as_uri())
    page.locator("#tires").select_option("sand")
    page.locator("#power").select_option("endurance")
    page.locator("#sensor").select_option("scout")
    page.locator("#paint").select_option("cyan")
    with page.expect_download() as download:
        page.get_by_role("button", name="Export garage.json").click()
    config = tmp_path / "garage.json"
    download.value.save_as(config)
    design = load_garage(config)
    assert design["paint"] == "cyan" and stats(design)["capacity"] == 120
    assert "81%" in page.locator("#stats").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors
    evidence = Path(__file__).parents[3] / "runs/verification"
    evidence.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence / "garage-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.screenshot(path=str(evidence / "garage-desktop.png"), full_page=True)
    page.close()
