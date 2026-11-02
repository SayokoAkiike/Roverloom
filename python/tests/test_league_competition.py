"""Benchmarks, leagues, leaderboards, and the local Codabench-style flow."""

import copy
import csv
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest

import roverloom
from roverloom.cli import main
from roverloom.competition import (
    MAX_SUBMISSION_FILES,
    extract_submission,
    ingest,
    load_submission,
    mock_submission,
    score,
)
from roverloom.contract import ContractError, dump_json, load_json_file, repo_root
from roverloom.evaluate import Metrics
from roverloom.league import (
    check_fair,
    compute_pins,
    load_benchmark,
    load_seeds_file,
    rank_board,
    run_league,
)
from roverloom.world import load_scenario

BENCH = "roverloom-bench-v2"
SMALL = {
    "autonomy": {
        "scenarios": ["science_sprint"],
        "rovers": ["pathfinder_6w"],
        "agents": ["stop", "mission-planner"],
    },
    "rover_design": {
        "scenarios": ["science_sprint"],
        "rovers": ["scout_4w", "pathfinder_6w"],
        "agents": ["mission-planner"],
    },
    "full_mission": {
        "scenarios": ["science_sprint"],
        "rovers": ["scout_4w", "pathfinder_6w"],
        "agents": ["stop", "mission-planner"],
    },
}


def small_benchmark() -> dict:
    benchmark = copy.deepcopy(load_benchmark(BENCH))
    benchmark["leagues"] = copy.deepcopy(SMALL)
    benchmark["seeds"] = [1, 2]
    return benchmark


def test_committed_benchmark_matches_code() -> None:
    assert load_benchmark(BENCH)["pins"]


def write_benchmark(tmp_path: Path, change) -> str:
    document = load_json_file(repo_root() / "benchmarks" / f"{BENCH}.json")
    change(document)
    path = tmp_path / "bench.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(model_version="other"), "model version"),
        (lambda d: d.update(scoring_version="other"), "scoring version"),
        (lambda d: d.update(builder_version="other"), "builder version"),
        (
            lambda d: d["pins"].update({"scenario:science_sprint": "0" * 64}),
            "science_sprint has changed",
        ),
        (lambda d: d["pins"].pop("rover:scout_4w"), "scout_4w has changed"),
        (lambda d: d["pins"].update({"agent:ghost": "0" * 64}), "ghost has changed"),
    ],
)
def test_incompatible_change_is_detected(tmp_path: Path, change, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        load_benchmark(write_benchmark(tmp_path, change))


def test_pins_do_not_depend_on_line_endings(tmp_path: Path) -> None:
    document = load_json_file(repo_root() / "benchmarks" / f"{BENCH}.json")
    first = compute_pins(document)
    assert first == compute_pins(copy.deepcopy(document))
    assert all(len(v) == 64 for v in first.values())


def test_benchmark_refuses_non_builtin_agents() -> None:
    document = small_benchmark()
    document["leagues"]["autonomy"]["agents"] = ["evil.py:Agent"]
    with pytest.raises(ContractError, match="built-in"):
        compute_pins(document)


def row(agent: str, scenario: str = "s", seed: int = 1, rover: str = "r") -> dict:
    return {"agent": agent, "scenario": scenario, "seed": seed, "rover": rover}


def test_fairness_check_detects_problems() -> None:
    check_fair([row("a"), row("b")])
    with pytest.raises(ContractError, match="same scenarios"):
        check_fair([row("a"), row("b", seed=2)])
    with pytest.raises(ContractError, match="twice"):
        check_fair([row("a"), row("a")])


def metric(score_value: float, success: bool = True, energy: float = 1.0) -> Metrics:
    return Metrics(
        "success" if success else "time_limit",
        success,
        0,
        0,
        1,
        1,
        energy,
        0,
        0,
        0,
        None,
        score_value,
    )


def test_ranking_is_deterministic_on_ties() -> None:
    board = rank_board({"zed": [metric(50)], "abe": [metric(50)], "top": [metric(60)]})
    assert [r["entry"] for r in board] == ["top", "abe", "zed"]
    assert [r["rank"] for r in board] == [1, 2, 3]
    board = rank_board({"a": [metric(50, energy=9)], "b": [metric(50, energy=1)]})
    assert board[0]["entry"] == "b"


def test_autonomy_league_results_and_fair_inputs(tmp_path: Path) -> None:
    result = run_league(small_benchmark(), "autonomy", tmp_path)
    assert {r["agent"] for r in result.runs} == {"stop", "mission-planner"}
    assert {r["rover"] for r in result.runs} == {"pathfinder_6w"}
    assert result.board[0]["entry"] == "mission-planner"
    assert result.board[0]["mean_score"] > result.board[1]["mean_score"]
    with (tmp_path / "results.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert rows[0]["science_value"] != ""
    board = json.loads((tmp_path / "leaderboard.json").read_text(encoding="utf-8"))
    assert board["model_version"] == roverloom.MODEL_VERSION
    assert (tmp_path / "leaderboard.csv").is_file()


def test_rover_design_league_compares_rovers_with_one_agent(tmp_path: Path) -> None:
    result = run_league(small_benchmark(), "rover_design", tmp_path)
    assert {r["agent"] for r in result.runs} == {"mission-planner"}
    assert {r["entry"] for r in result.board} == {"scout_4w", "pathfinder_6w"}


def test_full_mission_league_is_implemented(tmp_path: Path) -> None:
    result = run_league(small_benchmark(), "full_mission", tmp_path)
    assert len(result.board) == 4
    assert all(" + " in r["entry"] for r in result.board)


def test_league_rules_are_enforced(tmp_path: Path) -> None:
    benchmark = small_benchmark()
    with pytest.raises(ContractError, match="exactly one rover"):
        run_league(benchmark, "autonomy", tmp_path, extra_rovers=["hauler_8w"])
    with pytest.raises(ContractError, match="exactly one agent"):
        run_league(benchmark, "rover_design", tmp_path, extra_agents=["stop"])
    with pytest.raises(ContractError, match="unknown league"):
        run_league(benchmark, "wizard", tmp_path)


def test_rerun_gives_identical_results(tmp_path: Path) -> None:
    first = run_league(small_benchmark(), "autonomy", tmp_path / "a")
    second = run_league(small_benchmark(), "autonomy", tmp_path / "b")
    assert first.board == second.board


def test_private_seeds_change_results_but_do_not_leak(tmp_path: Path) -> None:
    secret = [987654321, 123456789]
    public = run_league(small_benchmark(), "autonomy", tmp_path / "public")
    private = run_league(small_benchmark(), "autonomy", tmp_path / "private", seeds=secret)
    assert private.runs != public.runs
    for name in ("results.json", "results.csv", "leaderboard.json", "leaderboard.csv"):
        text = (tmp_path / "private" / name).read_text(encoding="utf-8")
        assert "987654321" not in text and "123456789" not in text, name
    board = json.loads((tmp_path / "private" / "leaderboard.json").read_text(encoding="utf-8"))
    assert board["seed_source"] == "private"
    assert board["seed_count"] == 2


def test_csv_cannot_inject_formulas(tmp_path: Path) -> None:
    from roverloom.league import _csv_safe

    assert _csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _csv_safe("safe") == "safe"
    assert _csv_safe(5) == 5


@pytest.mark.parametrize(
    "content",
    [
        '{"seeds": []}',
        '{"seeds": [-1]}',
        '{"seeds": [1, 1]}',
        '{"seeds": ["a"]}',
        '{"seeds": [true]}',
        "{}",
        "nope",
    ],
)
def test_bad_seed_file_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "seeds.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ContractError):
        load_seeds_file(path)


def test_league_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["league", "verify"]) == 0
    assert "matches" in capsys.readouterr().out


# Competition flow.
SUBMISSION = repo_root() / "python" / "examples" / "submission"
REFERENCE = repo_root() / "competition" / "reference_data"


def make_reference(tmp_path: Path, scenarios=("science_sprint",), seeds=(1,)) -> Path:
    reference = tmp_path / "ref"
    reference.mkdir(exist_ok=True)
    (reference / "reference.json").write_text(
        json.dumps({"scenarios": list(scenarios), "seeds": list(seeds), "rover": "pathfinder_6w"}),
        encoding="utf-8",
    )
    return reference


def test_mock_submission_end_to_end(tmp_path: Path) -> None:
    scores = mock_submission(SUBMISSION, make_reference(tmp_path), tmp_path / "out")
    assert scores["runs_scored"] == scores["runs_expected"] == 1
    assert scores["mean_score"] > 0
    saved = json.loads((tmp_path / "out" / "output" / "scores.json").read_text(encoding="utf-8"))
    assert saved == scores
    for key in ("mean_score", "success_rate", "mean_science_value"):
        assert key in saved


def make_zip(tmp_path: Path, files: dict[str, str]) -> Path:
    path = tmp_path / "submission.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        for name, text in files.items():
            bundle.writestr(name, text)
    return path


def test_zip_submission_runs(tmp_path: Path) -> None:
    archive = make_zip(
        tmp_path,
        {
            "agent.py": (SUBMISSION / "agent.py").read_text(encoding="utf-8"),
            "metadata.json": (SUBMISSION / "metadata.json").read_text(encoding="utf-8"),
        },
    )
    scores = mock_submission(archive, make_reference(tmp_path), tmp_path / "out")
    assert scores["runs_scored"] == 1


@pytest.mark.parametrize("name", ["../evil.py", "..\\evil.py", "a/../../evil.py", "/abs/evil.py"])
def test_zip_path_traversal_is_refused(tmp_path: Path, name: str) -> None:
    archive = make_zip(tmp_path, {name: "x"})
    (tmp_path / "out").mkdir()
    target = tmp_path / "out" / "inner"
    if os.name != "nt" and "\\" in name:
        pytest.skip("a backslash is an ordinary filename character on this platform")
    with pytest.raises(ContractError, match="unsafe"):
        extract_submission(archive, target)
    assert not (tmp_path / "evil.py").exists()


def test_zip_symlink_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "link.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        bundle.writestr(info, "/etc/passwd")
    with pytest.raises(ContractError, match="unsafe"):
        extract_submission(path, tmp_path / "out")


def test_zip_limits(tmp_path: Path) -> None:
    many = make_zip(tmp_path, {f"f{i}.txt": "x" for i in range(MAX_SUBMISSION_FILES + 1)})
    with pytest.raises(ContractError, match="too many"):
        extract_submission(many, tmp_path / "a")
    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("big.txt", "0" * (21 * 1024 * 1024))
    with pytest.raises(ContractError, match="too large"):
        extract_submission(bomb, tmp_path / "b")
    not_zip = tmp_path / "x.zip"
    not_zip.write_text("not a zip", encoding="utf-8")
    with pytest.raises(ContractError, match="valid zip"):
        extract_submission(not_zip, tmp_path / "c")


def submission_dir(tmp_path: Path, agent_code: str, metadata: dict | None = None) -> Path:
    directory = tmp_path / "submission"
    directory.mkdir(exist_ok=True)
    (directory / "agent.py").write_text(agent_code, encoding="utf-8")
    (directory / "metadata.json").write_text(
        json.dumps(
            metadata
            or {
                "schema_version": 0,
                "name": "t",
                "authors": ["t"],
                "agent_class": "Agent",
                "league": "autonomy",
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"schema_version": 0}, "submission_metadata"),
        (
            {
                "schema_version": 0,
                "name": "t",
                "authors": ["t"],
                "agent_class": "os.system",
                "league": "autonomy",
            },
            "agent_class",
        ),
        (
            {
                "schema_version": 0,
                "name": "t",
                "authors": ["t"],
                "agent_class": "A",
                "league": "full_mission",
            },
            "rover.json",
        ),
    ],
)
def test_bad_submission_metadata_is_refused(tmp_path: Path, metadata: dict, message: str) -> None:
    directory = submission_dir(tmp_path, "", metadata)
    with pytest.raises(ContractError, match=message):
        load_submission(directory)


def test_submission_without_code_is_refused(tmp_path: Path) -> None:
    directory = submission_dir(tmp_path, "")
    (directory / "agent.py").unlink()
    with pytest.raises(ContractError, match="agent.py"):
        load_submission(directory)


def test_crashing_agent_process_scores_zero_without_crashing_evaluation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("roverloom.competition.REPLY_TIMEOUT_S", 3.0)
    directory = submission_dir(tmp_path, "raise RuntimeError('boom')\n")
    scores = mock_submission(directory, make_reference(tmp_path), tmp_path / "out")
    assert scores["mean_score"] == 0
    assert scores["success_rate"] == 0


HANGING_AGENT = """
import time
from roverloom.api import STOP
class Agent:
    def reset(self, brief, seed):
        pass
    def act(self, observation):
        time.sleep(600)
        return STOP
"""


def test_hanging_agent_is_stopped_by_the_reply_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("roverloom.competition.REPLY_TIMEOUT_S", 2.0)
    directory = submission_dir(tmp_path, HANGING_AGENT)
    reference = make_reference(tmp_path)
    summary = ingest(directory.resolve(), reference, tmp_path / "res")
    assert summary[0]["outcome"] == "agent_error"


ENV_AGENT = """
import os
from roverloom.api import STOP
if "ROVERLOOM_TEST_SECRET" in os.environ:
    raise RuntimeError("secret was visible")
class Agent:
    def reset(self, brief, seed):
        pass
    def act(self, observation):
        return STOP
"""


def test_environment_secrets_are_not_passed_to_the_agent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ROVERLOOM_TEST_SECRET", "hunter2")
    directory = submission_dir(tmp_path, ENV_AGENT)
    summary = ingest(directory.resolve(), make_reference(tmp_path), tmp_path / "res")
    assert summary[0]["outcome"] != "agent_error"


def test_scoring_missing_or_tampered_results_counts_zero(tmp_path: Path) -> None:
    reference = make_reference(tmp_path, seeds=(1, 2))
    ingest(SUBMISSION.resolve(), reference, tmp_path / "res")
    good = score(reference, tmp_path / "res", tmp_path / "out1")
    assert good["runs_scored"] == 2
    path = tmp_path / "res" / "science_sprint" / "seed-2" / "telemetry.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    tampered = score(reference, tmp_path / "res", tmp_path / "out2")
    assert tampered["runs_scored"] == 1
    assert tampered["mean_score"] < good["mean_score"]
    shutil.rmtree(tmp_path / "res" / "science_sprint" / "seed-1")
    gone = score(reference, tmp_path / "res", tmp_path / "out3")
    assert gone["runs_scored"] == 0 and gone["mean_score"] == 0


def test_scoring_rejects_run_from_the_wrong_seed(tmp_path: Path) -> None:
    reference = make_reference(tmp_path, seeds=(1,))
    ingest(SUBMISSION.resolve(), reference, tmp_path / "res")
    other = make_reference(tmp_path, seeds=(1,))
    run = tmp_path / "res" / "science_sprint" / "seed-1"
    shutil.copytree(run, tmp_path / "res" / "science_sprint" / "seed-7")
    (other / "reference.json").write_text(
        dump_json({"scenarios": ["science_sprint"], "seeds": [7], "rover": "pathfinder_6w"}),
        encoding="utf-8",
    )
    assert score(other, tmp_path / "res", tmp_path / "out")["runs_scored"] == 0


def test_errors_do_not_reveal_hidden_details(tmp_path: Path) -> None:
    reference = make_reference(tmp_path, seeds=(424242,))
    score(reference, tmp_path / "empty", tmp_path / "out")
    assert "424242" not in (tmp_path / "out" / "errors.json").read_text(encoding="utf-8")


def test_competition_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "competition",
            str(SUBMISSION),
            "--reference",
            str(make_reference(tmp_path)),
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 0
    assert "NOT A SANDBOX" in capsys.readouterr().out


def test_hidden_scenario_in_reference_shadows_public_one(tmp_path: Path) -> None:
    reference = make_reference(tmp_path, scenarios=("private_one",))
    hidden = reference / "scenarios"
    hidden.mkdir()
    document = load_scenario("science_sprint").document
    document = {**document, "scenario_id": "private_one"}
    (hidden / "private_one.json").write_text(json.dumps(document), encoding="utf-8")
    scores = mock_submission(SUBMISSION, reference, tmp_path / "out")
    assert scores["runs_scored"] == 1
