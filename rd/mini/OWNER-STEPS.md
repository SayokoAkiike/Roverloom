# Owner steps on the Mac mini for Stage 1

Run in Terminal on the Mac mini, through Screen Sharing. Each step needs the owner's password for `sudo`. Claude checks
the result from the MacBook Air after each step and reports before the next. Nothing here is run by Claude.

## Step 1. Create the night user

Done 2026-11-07; results in [`docs/results/rd-stage1/README.md`](../../docs/results/rd-stage1/README.md).

The script and the two public keys are already in `/Users/Shared/rdnight-setup/` (no private key is there). Its
SHA-256 must start with `e502a8663ef7ad4b`.

```shell
cd /Users/Shared/rdnight-setup
shasum -a 256 create-night-user.sh
sudo bash create-night-user.sh id_ed25519_rdnight.pub id_ed25519_rdsetup.pub
```

It asks once for a password for `rdnight`: use a long random one, and keep it. It creates group and user 601
`rdnight`, not in `staff` or `admin`, hidden from the login window, with a 700 home, adds it to Remote Login, and installs
two keys: the night key (dispatcher only) and a setup key that expires at 23:59 tomorrow. It changes nothing in the
owner's account. Its last lines print the checks; tell Claude when it has finished.

Afterwards Claude, as `rdnight` with the setup key: checks groups, ACLs, and directory permissions; tries to read the
owner's home, `.ssh`, Keychains, Claude data, clone, research data, and backup, expecting refusals; builds the night
area with `install-night-area.sh`; and runs a build, the automation tests, and an offscreen game with no graphical
session.

## Step 2. Remove the night key from the owner's account

Only after step 1's checks pass. Restores `~/.ssh/authorized_keys` to its state before Stage 0:

```shell
diff ~/RoverloomNight/authorized_keys.before-rdnight ~/.ssh/authorized_keys   # shows only the night key's line
cp ~/RoverloomNight/authorized_keys.before-rdnight ~/.ssh/authorized_keys
```

No `sudo` is needed. The owner's own key is the first line and is unchanged.

## Step 3. Application Firewall, with an automatic revert

Do this only while Claude is ready to test, and with Screen Sharing open.

```shell
FW=/usr/libexec/ApplicationFirewall/socketfilterfw
sudo $FW --getglobalstate; sudo $FW --listapps          # record the starting state

# 1. Arm the revert: the firewall turns itself off again in 15 minutes unless cancelled
sudo sh -c 'nohup sh -c "sleep 900; /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off" > /tmp/fw-revert.log 2>&1 &'

# 2. Block incoming connections for Unreal and Zen, owner's and night's copies
for app in "$HOME/UnrealEngineInstall/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app" \
           "/Users/Shared/UE_5.8-night/Engine/Binaries/Mac/UnrealEditor.app" \
           "$HOME/Library/Application Support/Epic/UnrealEngine/Common/Zen/Install/zenserver"; do
  sudo $FW --add "$app"; sudo $FW --blockapp "$app"
done

# 3. Turn it on. Not "block all incoming", not stealth mode.
sudo $FW --setglobalstate on
```

Claude then checks from the Air: SSH as the owner and as `rdnight`; Tailscale ping; that Screen Sharing is still
connected; that MCP through the night tunnel still answers; and that port 1985 of a running Unreal process and 8558 of
Zen refuse a connection from the Air. If all pass, cancel the revert:

```shell
sudo pkill -f "sleep 900; /usr/libexec/ApplicationFirewall"
```

If anything fails, or remote access is lost, do nothing: the firewall turns off by itself within 15 minutes. To undo by
hand: `sudo $FW --setglobalstate off`.

The night user's own Zen server appears at `/Users/rdnight/Library/Application Support/Epic/UnrealEngine/Common/Zen/Install/zenserver`
after its first Unreal run; add and block it the same way then.
