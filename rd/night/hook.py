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


STANDARD_BIN_DIRS = {"/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"}
SEPARATORS = ("&&", "||", ";", "|")
MAX_SLEEP_S = 600


def tokenize(command):
    """Split a shell command into simple commands, each a list of ("word", text) and ("op", text).

    Separators are unquoted &&, ||, ;, and |. Unquoted >, >>, <, &>, 2>, 2>>, >&1, and 2>&1 become
    "op" tokens; the same characters inside quotes stay part of a word. Refuses what could run code
    or text the hook cannot see: $ and backquotes outside single quotes, background &, subshells,
    braces, here-documents, and newlines.
    """
    segments, tokens, word, in_word, quote, i = [], [], "", False, None, 0
    n = len(command)

    def end_word():
        nonlocal word, in_word
        if in_word:
            tokens.append(("word", word))
        word, in_word = "", False

    while i < n:
        ch = command[i]
        if quote == "'":
            if ch == "'":
                quote = None
            else:
                word += ch
            i += 1
            continue
        if quote == '"':
            if ch in "$`":
                deny("$ and backquotes are refused, even inside double quotes; use single quotes")
            if ch == "\\" and i + 1 < n and command[i + 1] in '"\\':
                word += command[i + 1]
                i += 2
                continue
            if ch == '"':
                quote = None
            else:
                word += ch
            i += 1
            continue
        if ch in "'\"":
            quote, in_word = ch, True
            i += 1
            continue
        if ch == "\\":
            if i + 1 >= n or command[i + 1] == "\n":
                deny("one line only")
            word += command[i + 1]
            in_word = True
            i += 2
            continue
        if ch in "$`":
            deny("$ and backquotes are refused: no expansion or substitution")
        if ch in "(){}":
            deny("subshells and braces are refused")
        if ch in "\n\r":
            deny("one line only")
        if ch in " \t":
            end_word()
            i += 1
            continue
        if command.startswith("<<", i):
            deny("here-documents are refused; write the file with the Write tool")
        sep = next((t for t in ("&&", "||", ";", "|") if command.startswith(t, i)), None)
        if sep:
            end_word()
            if not tokens:
                deny("empty command between operators")
            segments.append(tokens)
            tokens = []
            i += len(sep)
            continue
        m = re.match(r"(>>?&[12]|>>?|&>|<)", command[i:])
        if m:  # unquoted > and < redirect even in the middle of a word, as in the shell
            op = m.group(0)
            if in_word and word.isdigit():  # 2>file: the digits name a file descriptor
                op, word, in_word = word + op, "", False
            end_word()
            tokens.append(("op", op))
            i += len(m.group(0))
            continue
        if ch == "&":
            deny("background & is refused")
        word += ch
        in_word = True
        i += 1
    if quote:
        deny("unbalanced quotes")
    end_word()
    if not tokens:
        deny("empty command")
    segments.append(tokens)
    return segments


def words_after_redirections(tokens, root, protected):
    """Check and drop redirections; output may go only into the worktree or /dev/null."""
    words, i = [], 0
    while i < len(tokens):
        kind, text = tokens[i]
        if kind == "word":
            words.append(text)
            i += 1
            continue
        if text.endswith("&1") or text.endswith("&2"):
            i += 1
            continue
        if i + 1 >= len(tokens) or tokens[i + 1][0] != "word":
            deny("redirection without a target")
        target = tokens[i + 1][1]
        if text != "<" and target != "/dev/null":
            check_write(target, root, protected)
        i += 2
    return words


def check_simple(tokens, root, protected):
    words = words_after_redirections(tokens, root, protected)
    if not words:
        deny("empty command")
    prog = words[0]
    args = words[1:]
    mini = os.environ.get("RD_MINI")
    if mini and prog == mini:
        return  # the owner's copy; its own argument checks apply
    if os.path.dirname(prog) in STANDARD_BIN_DIRS:
        prog = os.path.basename(prog)
    if prog == "cd":
        if len(args) != 1:
            deny("cd takes one directory")
        inside_ok, real = inside(args[0], root)
        if not inside_ok:
            deny(f"cd only within the night worktree, not {real}")
        return
    if prog == "sleep":
        if len(args) != 1 or not re.fullmatch(r"\d+(\.\d+)?", args[0]):
            deny("sleep <seconds>")
        if float(args[0]) > MAX_SLEEP_S:
            deny(f"sleep at most {MAX_SLEEP_S} s")
        return
    if prog not in ALLOWED_PROGRAMS:
        deny(f"program '{words[0]}' is not allowed at night")
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


def check_bash(command, root, protected):
    for tokens in tokenize(command):
        check_simple(tokens, root, protected)


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
