#!/bin/bash
# Create the night user on the Mac mini. Run by the owner, in Terminal through Screen Sharing:
#   sudo bash create-night-user.sh <night-key.pub> <setup-key.pub>
# It refuses to run if the user or group exists, changes nothing in the owner's account, and prints checks at the end.
# The setup key may open a shell as rdnight until SETUP_EXPIRY, for installing files and running access tests; the night
# key may run only the dispatcher, and forward only to the night MCP port. See docs/rd-stage1-isolation-plan.md.
set -euo pipefail

NAME=rdnight
ID=601
MCP_PORT=8100
SETUP_EXPIRY=$(date -v+1d +%Y%m%d2359)   # The setup key stops working at 23:59 tomorrow
NIGHT_PUB=${1:?night key .pub file}
SETUP_PUB=${2:?setup key .pub file}

[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
for f in "$NIGHT_PUB" "$SETUP_PUB"; do
  grep -q '^ssh-ed25519 ' "$f" || { echo "$f is not an ed25519 public key"; exit 1; }
done
if dscl . -read "/Users/$NAME" >/dev/null 2>&1 || dscl . -read "/Groups/$NAME" >/dev/null 2>&1; then
  echo "user or group $NAME exists; nothing changed"; exit 1
fi
if dscl . -search /Users UniqueID "$ID" | grep -q . || dscl . -search /Groups PrimaryGroupID "$ID" | grep -q .; then
  echo "id $ID is taken; nothing changed"; exit 1
fi

echo "== group"
dscl . -create "/Groups/$NAME"
dscl . -create "/Groups/$NAME" PrimaryGroupID "$ID"
dscl . -create "/Groups/$NAME" RealName "Roverloom night"

echo "== user: you will be asked for a password for $NAME; use a long random one and keep it"
sysadminctl -addUser "$NAME" -fullName "Roverloom Night" -UID "$ID" -home "/Users/$NAME" -shell /bin/zsh -password -
dscl . -create "/Users/$NAME" PrimaryGroupID "$ID"
dscl . -create "/Users/$NAME" IsHidden 1                      # Not listed in the login window
dseditgroup -o edit -d "$NAME" -t user staff 2>/dev/null || true
dseditgroup -o edit -d "$NAME" -t user admin 2>/dev/null || true
[ -d "/Users/$NAME" ] || createhomedir -c -u "$NAME" >/dev/null
chown -R "$NAME:$NAME" "/Users/$NAME"
chmod 700 "/Users/$NAME"

echo "== remote login for $NAME only (adds to com.apple.access_ssh; the owner stays allowed through admin)"
dseditgroup -o edit -a "$NAME" -t user com.apple.access_ssh

echo "== keys"
install -d -m 700 -o "$NAME" -g "$NAME" "/Users/$NAME/.ssh"
{
  printf 'restrict,port-forwarding,permitopen="127.0.0.1:%s",command="/usr/bin/python3 /Users/%s/RoverloomNight/bin/dispatch.py" %s\n' \
    "$MCP_PORT" "$NAME" "$(cat "$NIGHT_PUB")"
  printf 'expiry-time="%s",no-agent-forwarding,no-X11-forwarding,no-port-forwarding %s\n' "$SETUP_EXPIRY" "$(cat "$SETUP_PUB")"
} > "/Users/$NAME/.ssh/authorized_keys"
chown "$NAME:$NAME" "/Users/$NAME/.ssh/authorized_keys"
chmod 600 "/Users/$NAME/.ssh/authorized_keys"

echo "== checks"
id "$NAME"
for g in staff admin com.apple.access_ssh; do printf '%-22s ' "$g:"; dseditgroup -o checkmember -m "$NAME" "$g" | head -1; done
ls -led "/Users/$NAME" "/Users/$NAME/.ssh" "/Users/$NAME/.ssh/authorized_keys"
dscl . -read "/Users/$NAME" UniqueID PrimaryGroupID IsHidden UserShell NFSHomeDirectory
echo "setup key expires: $SETUP_EXPIRY"
echo "done; nothing in the owner's account was changed"
