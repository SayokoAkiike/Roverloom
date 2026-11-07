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

# Retry only when the connection itself failed: then nothing ran on the Mac mini, so even build or game is safe to
# send again. A refusal or an error from the dispatcher, or a connection lost mid-command, is never retried.
DELAYS=(${RD_MINI_RETRY_DELAYS:-10 20 40 60 60})
NOT_CONNECTED='connect to host|Operation timed out|Connection refused|No route to host|Network is unreachable|Could not resolve hostname'
run() {
  local err rc attempt=0
  err=$(mktemp "${TMPDIR:-/tmp}/mini-sh.XXXXXX")
  while true; do
    if "$@" 2> "$err"; then rc=0; else rc=$?; fi
    if [ $rc -ne 0 ] && grep -Eq "$NOT_CONNECTED" "$err" && [ $attempt -lt ${#DELAYS[@]} ]; then
      echo "mini.sh: Mac mini not reachable; retry $((attempt + 1)) of ${#DELAYS[@]} in ${DELAYS[$attempt]} s" >&2
      sleep "${DELAYS[$attempt]}"; attempt=$((attempt + 1)); continue
    fi
    cat "$err" >&2; rm -f "$err"; return $rc
  done
}

if [ "$1" = push ]; then
  [[ $# -eq 2 && "$2" =~ ^rd/[a-z0-9][a-z0-9._-]{0,59}$ ]] || { echo "mini.sh: push <rd/branch>" >&2; exit 2; }
  # The Mac mini has no Git LFS and the dispatcher refuses its verbs: skip the LFS pre-push hook. The URL is fixed.
  export GIT_LFS_SKIP_PUSH=1 GIT_SSH_COMMAND="${SSH[*]}"
  run git push --no-verify "$USER_@$HOST:~/RoverloomNight/repo.git" "refs/heads/$2:refs/heads/$2"
  exit $?
fi
run "${SSH[@]}" "$USER_@$HOST" "$*"
exit $?
