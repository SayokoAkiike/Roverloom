"""Documentation promises: required guides exist, links work, and claims stay honest."""

import re
from pathlib import Path

import pytest

from roverloom.contract import repo_root

ROOT = repo_root()
REQUIRED = [
    "docs/tutorials/custom-rover.md",
    "docs/tutorials/custom-agent.md",
    "docs/tutorials/custom-mission.md",
    "docs/tutorials/custom-failure-model.md",
    "docs/benchmark-reproduction.md",
    "docs/competition-rules.md",
    "docs/api-compatibility.md",
    "docs/decisions/README.md",
    "docs/security.md",
]
DOCS = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").rglob("*.md"))]


@pytest.mark.parametrize("name", REQUIRED)
def test_required_document_exists(name: str) -> None:
    assert (ROOT / name).stat().st_size > 200


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\((?!https?:|#)([^)#\s]+)", text):
        assert (path.parent / target).exists(), f"{path.name} links to missing {target}"


def test_every_decision_is_listed() -> None:
    index = (ROOT / "docs" / "decisions" / "README.md").read_text(encoding="utf-8")
    for path in (ROOT / "docs" / "decisions").glob("0*.md"):
        assert path.name in index


def test_readme_does_not_claim_unbuilt_things() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Not started**" in readme
    assert "Not validated" in readme or "not been validated" in readme
