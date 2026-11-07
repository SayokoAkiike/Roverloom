#!/usr/bin/python3
"""PreToolUse hook for night runs: allow a tool call only inside the night's worktree and policy.

Claude Code passes the call as JSON on stdin. Exit 0 allows it; exit 2 blocks it, and stderr tells
the model why. The policy is code, not settings wildcards, so a pattern cannot widen it.
Python 3.9 compatible.

Environment, set by night.py: RD_WORKTREE (the only tree that may be written) and RD_CHARTER
(the charter's path).
"""

import json
import os
import re
import shlex
import sys

READ_ONLY_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "WebSearch",
    "WebFetch",
    "TodoWrite",
    "Task",
    "Agent",
    "ToolSearch",
    "StructuredOutput",  # how a cycle returns its answer (--json-schema); writes nothing
}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# Programs a night may run through Bash. Everything else is refused, whatever its arguments.
ALLOWED_PROGRAMS = {
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "rg",
    "find",
    "sort",
    "uniq",
    "diff",
    "cmp",
    "shasum",
    "file",
    "stat",
    "echo",
    "printf",
    "pwd",
    "date",
    "true",
    "test",
    "mkdir",
    "cp",
    "mv",
    "touch",
    "sed",
    "awk",
    "tr",
    "cut",
    "xargs",
    "python3",
    "uv",
    "git",
    "sips",
}
GIT_ALLOWED = {
    "status",
    "diff",
    "log",
    "show",
    "add",
    "commit",
    "switch",
    "branch",
    "rev-parse",
    "ls-files",
    "restore",
}
GIT_FORBIDDEN_ARGS = {
    "--force",
    "-f",
    "-D",
    "--hard",
    "--global",
    "--system",
    "-c",
    "--exec-path",
    "--upload-pack",
}
UV_ALLOWED = {"run"}
SHELL_META = re.compile(r"[;&|`$<>(){}\\\n]")


def deny(reason):
    sys.stderr.write("night policy: " + reason + "\n")
    sys.exit(2)


def inside(path, root):
    real = os.path.realpath(os.path.join(root, path) if not os.path.isabs(path) else path)
    return real == root or real.startswith(root + os.sep), real


def check_write(path, root, protected):
    ok, real = inside(path, root)
    if not ok:
        deny(f"writes are allowed only inside the night worktree, not {real}")
    rel = os.path.relpath(real, root)
    for p in protected:
        if rel == p.rstrip("/") or rel.startswith(p if p.endswith("/") else p + "/") or rel == p:
            deny(f"{rel} is protected by the charter")


def check_bash(command, root, protected):
    if SHELL_META.search(command):
        deny("shell operators, substitution, and redirection are refused; run one program per call")
    try:
        words = shlex.split(command)
    except ValueError:
        deny("unparsable command")
    if not words:
        deny("empty command")
    prog = words[0]
    mini = os.environ.get("RD_MINI")
    if mini and prog == mini:
        return  # the owner's copy; its own argument checks apply
    if prog not in ALLOWED_PROGRAMS:
        deny(f"program '{prog}' is not allowed at night")
    args = words[1:]
    if prog == "git":
        if not args or args[0] not in GIT_ALLOWED:
            deny("git subcommand refused: push, merge, reset, rebase, clean, stash, config")
        if any(a in GIT_FORBIDDEN_ARGS or a.startswith("--force") for a in args):
            deny("forbidden git option")
        if args[0] == "commit" and "--no-verify" in args:
            deny("commits keep their hooks")
    if prog == "uv" and (not args or args[0] not in UV_ALLOWED):
        deny("only 'uv run' is allowed; installing packages is refused")
    if prog in ("cp", "mv", "mkdir", "touch", "sed"):
        targets = [a for a in args if not a.startswith("-")]
        if prog == "sed" and "-i" not in args:
            targets = []
        for t in targets[-1:] if prog in ("cp", "mv") else targets:
            check_write(t, root, protected)
    # Reads outside the worktree are left to the sandbox, which denies the owner's credentials.
    # Programs such as python3 can write anywhere the sandbox allows; the hook does not stop that.


def main():
    call = json.load(sys.stdin)
    tool = call.get("tool_name", "")
    data = call.get("tool_input", {}) or {}
    root = os.path.realpath(os.environ.get("RD_WORKTREE", ""))
    if not root or root == "/":
        deny("RD_WORKTREE is not set")
    with open(os.environ["RD_CHARTER"]) as f:
        protected = json.load(f)["protected_repo_paths"]
    if tool in READ_ONLY_TOOLS or tool.startswith("mcp__unreal-night__"):
        sys.exit(0)
    if tool in WRITE_TOOLS:
        check_write(data.get("file_path") or data.get("notebook_path") or "", root, protected)
        sys.exit(0)
    if tool == "Bash":
        check_bash(data.get("command", ""), root, protected)
        sys.exit(0)
    deny(f"tool {tool} is not allowed at night")


if __name__ == "__main__":
    main()
