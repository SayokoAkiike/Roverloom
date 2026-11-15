#!/bin/bash
# Build the night area in the night user's home. Run as rdnight, from a folder holding dispatch.py, charter.json, and
# night.sb (the template); it refuses if ~/RoverloomNight exists. The night clone is filled later by a push from the
# Air to repo.git and `dispatch.py sync`.
set -euo pipefail
SRC=${1:?folder with dispatch.py, charter.json, night.sb}
MODE=${2:-new}   # "update-bin": replace bin/ in an existing night area, nothing else
ROOT="$HOME/RoverloomNight"
[ "$(id -un)" = rdnight ] || { echo "run as rdnight"; exit 1; }
if [ "$MODE" = update-bin ]; then
  [ -d "$ROOT/bin" ] || { echo "no night area"; exit 1; }
  chmod 755 "$ROOT/bin"; chmod 644 "$ROOT"/bin/*
else
  [ ! -e "$ROOT" ] || { echo "$ROOT exists; nothing changed"; exit 1; }
  mkdir -p "$ROOT"/{bin,evidence,run,logs}
  git init -q --bare "$ROOT/repo.git"
  # A new user has no Application Support until a GUI login; without it .NET resolves UBT's data folder to a relative
  # path, and UBT tries to write into the engine (measured 2026-11-07).
  mkdir -p -m 700 "$HOME/Library/Application Support"
fi
cp "$SRC/dispatch.py" "$SRC/charter.json" "$ROOT/bin/"
/usr/bin/python3 - "$SRC/night.sb" "$SRC/charter.json" "$ROOT/bin/night.sb" <<'EOF'
import json, os, sys
template, charter, out = sys.argv[1:]
mini = json.load(open(charter))["mini"]
expand = lambda p: os.path.expanduser(p)
lines = lambda key, kind="subpath": "\n".join('  (%s "%s")' % (kind, expand(p)) for p in mini[key])
text = open(template).read()
text = text.replace("@DENY_WRITE_FILES@", lines("write_protected_files", "literal"))
text = text.replace("@DENY_WRITE@", lines("write_protected")).replace("@DENY_READ@", lines("read_protected"))
assert "@" not in text.replace("@HOME@", ""), "unfilled placeholder"
open(out, "w").write(text)
EOF
chmod 444 "$ROOT"/bin/*
chmod 555 "$ROOT/bin"
chmod 700 "$ROOT"
ls -la "$ROOT" "$ROOT/bin"
shasum -a 256 "$ROOT"/bin/*
