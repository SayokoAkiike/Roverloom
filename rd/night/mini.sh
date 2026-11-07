#!/bin/bash
# The night's only way to the Mac mini: one dispatcher verb, over the night key, which the Mac mini restricts to the
# dispatcher. Host and user come from ~/.roverloom-rd/local.json, which is not in Git.
#   rd/night/mini.sh status | sync <rd/branch> | build <run> | test <run> | game <run> <s> | editor-start <run>
#                    | editor-stop-own | fetch-evidence <run>     (fetch-evidence writes a .tar.gz to stdout)
#                    | push <rd/branch>   (from the current repository to the night repository on the Mac mini, only)
set -euo pipefail
case "${1:-}" in
  status|sync|build|test|game|editor-start|editor-stop-own|fetch-evidence|push) ;;
  *) echo "mini.sh: unknown verb '${1:-}'" >&2; exit 2 ;;
esac
for a in "$@"; do
  [[ "$a" =~ ^[A-Za-z0-9/._-]+$ ]] || { echo "mini.sh: bad argument" >&2; exit 2; }
done
LOCAL="$HOME/.roverloom-rd/local.json"
read -r HOST USER_ KEY < <(/usr/bin/python3 -c 'import json,os,sys; c=json.load(open(sys.argv[1])); print(c["mini_host"], c["mini_user"], os.path.expanduser(c["night_key"]))' "$LOCAL")
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$KEY")
if [ "$1" = push ]; then
  [[ $# -eq 2 && "$2" =~ ^rd/[a-z0-9][a-z0-9._-]{0,59}$ ]] || { echo "mini.sh: push <rd/branch>" >&2; exit 2; }
  # The Mac mini has no Git LFS and the dispatcher refuses its verbs: skip the LFS pre-push hook. The URL is fixed.
  GIT_LFS_SKIP_PUSH=1 GIT_SSH_COMMAND="${SSH[*]}" exec git push --no-verify \
    "$USER_@$HOST:~/RoverloomNight/repo.git" "refs/heads/$2:refs/heads/$2"
fi
exec ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$KEY" "$USER_@$HOST" "$*"
