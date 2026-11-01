"""Fails if tracked files include secrets, generated output, or large non-LFS files."""

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

MAX_NON_LFS_BYTES = 5 * 1024 * 1024
GENERATED_DIRS = {"Binaries", "Intermediate", "Saved", "DerivedDataCache", ".venv"}
FORBIDDEN_NAMES = re.compile(r"(^\.env(\..+)?$)|(\.(pem|key|pfx|p12)$)")
ALLOWED_NAMES = {".env.example"}
SECRET_PATTERNS = {
    "GitHub token": re.compile(rb"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "Anthropic key": re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "OpenAI-style key": re.compile(rb"\bsk-[A-Za-z0-9]{32,}\b"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "Private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
EXPECTED_LFS_PATHS = ["unreal/Content/a.uasset", "unreal/Content/a.umap", "a.fbx", "a.png", "a.wav"]
EXPECTED_TEXT_PATHS = ["unreal/Roverloom.uproject", "README.md", "schemas/a.schema.json"]


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, encoding="utf-8"
    ).stdout


def lfs_paths(root: Path, paths: list[str]) -> set[str]:
    output = git(root, "check-attr", "filter", "--", *paths)
    return {
        line.split(": ")[0]
        for line in output.splitlines()
        if line.endswith(": filter: lfs")
    }


def find_problems(root: Path) -> list[str]:
    tracked = git(root, "ls-files").splitlines()
    tracked_lfs = lfs_paths(root, tracked) if tracked else set()
    problems = []

    for name in tracked:
        pure = PurePosixPath(name)
        if GENERATED_DIRS.intersection(pure.parts):
            problems.append(f"generated output is tracked: {name}")
        if FORBIDDEN_NAMES.search(pure.name) and pure.name not in ALLOWED_NAMES:
            problems.append(f"credential-like file is tracked: {name}")

        path = root / name
        if name in tracked_lfs or not path.is_file():
            continue
        if path.stat().st_size > MAX_NON_LFS_BYTES:
            problems.append(f"large file is not in LFS: {name}")
        data = path.read_bytes()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                problems.append(f"possible {label}: {name}")

    missing = set(EXPECTED_LFS_PATHS) - lfs_paths(root, EXPECTED_LFS_PATHS)
    problems += [f"expected LFS tracking: {name}" for name in sorted(missing)]
    wrong = lfs_paths(root, EXPECTED_TEXT_PATHS)
    problems += [f"must not use LFS: {name}" for name in sorted(wrong)]
    return problems


def main() -> int:
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    problems = find_problems(root)
    for problem in problems:
        print(f"FAIL: {problem}")
    if not problems:
        print("OK: repository hygiene checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
